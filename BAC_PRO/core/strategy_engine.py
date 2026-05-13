"""
BAC_PRO — StrategyEngine v3
四阶段状态控制器：SLEEP / ACTIVE / B-LOCK

修复清单（相对 v2）
---------------------------------------
FIX-1  _terminate() 拆分为三个职责单一的方法，消除"一次 terminate 同时污染
       sequence state + streak state + runtime state"的根因。
         _finalize_sequence()   — 仅清理序列运行时（step、side、key、flag）
         _finalize_streak_lock() — 仅写 STREAK 方向锁
         _reset_runtime()       — 完整重置（_finalize_sequence + 清锁），换靴用

FIX-2  active_side 不再实时跟随 current_side。
       start() 时冻结 active_side = side，生命周期内永不改变。
       消除 L2.5：动态 active_side 污染 → _terminate() 锁错方向。

FIX-3  _terminate() 现在只是 _finalize_sequence() + _finalize_streak_lock()
       的组合，不接受外部直接调用锁参数，锁方向始终来自 _active_streak_side，
       防止"二次 terminate 清锁"（L3）。

FIX-4  TIE_KILL 路径：_terminate(lock_streak=False) 支持。
       TIE 不属于任何 STREAK，TIE_KILL 只结束 S1 生命周期，不得修改 STREAK 锁。

FIX-5  unlock_streak() 调用时机：仅当 _locked_streak_side != new_side 且
       _locked_streak_side is not None 时解锁，逻辑不变，但增加防御性注释
       说明与 _finalize_streak_lock() 的顺序依赖。

接口契约（与 v2 完全兼容，即插即用）
---------------------------------------
公开属性
  .state          str   当前状态
  .step_index     int   当前序列步数（0-based）

公开方法
  .start(strategy_key, side, streak_side)  → dict
  .on_event(context)                       → dict
  .unlock_streak(new_side)
  ._terminate(lock_streak=True)            内部重置；外部调用须传 lock_streak=False（TIE_KILL）

返回指令（action 字段）
  BET    → 本手下注
  HOLD   → TIE 冻结
  SLEEP  → 熔断/完成
  NO_OP  → 引擎空闲
"""


class StrategyEngine:

    # =====================================================
    # 投注矩阵库
    # =====================================================
    S1_STRATEGY_LIB = {
        "000": [0,   0,   0  ],
        "100": [100, 0,   0  ],
        "110": [100, 100, 0  ],
        "120": [100, 200, 0  ],
        "111": [100, 100, 100],
        "121": [100, 200, 100],
        "147": [100, 400, 700],
        "AUTO": [-1, -1, -1 ],
    }

    _S1_LEN = 3

    def __init__(self):
        # ── 主状态 ──────────────────────────────────────────
        self.state          = "SLEEP"
        self.step_index     = 0
        self.strategy_key   = None
        self.active_side    = None          # FIX-2: start()时冻结，生命周期内不变

        # ── 唯一性锁 ─────────────────────────────────────────
        self._streak_executed = False

        # ── STREAK 级别方向锁 ────────────────────────────────
        self._active_streak_side = None     # start()时记录本次S1所属STREAK方向
        self._locked_streak_side = None     # terminate后锁住，unlock_streak()在反转时解除

    # =====================================================
    # 私有：金额计算
    # =====================================================
    def _auto_amount(self, edge: float) -> int:
        if edge >= 0.05: return 700
        if edge >= 0.04: return 400
        if edge >= 0.03: return 300
        if edge >= 0.02: return 200
        if edge >= 0.01: return 100
        return 0

    def _get_amount(self, edge: float) -> int:
        if self.strategy_key == "AUTO":
            return self._auto_amount(edge)
        matrix = self.S1_STRATEGY_LIB.get(self.strategy_key, [0, 0, 0])
        if self.step_index >= len(matrix):
            return 0
        return matrix[self.step_index]

    # =====================================================
    # FIX-1: 拆分 _terminate() 为三个职责单一的方法
    # =====================================================

    def _finalize_sequence(self):
        """
        仅清理序列运行时状态。
        不触碰 _locked_streak_side。
        """
        self.state               = "SLEEP"
        self.step_index          = 0
        self.strategy_key        = None
        self.active_side         = None
        self._streak_executed    = False
        self._active_streak_side = None

    def _finalize_streak_lock(self):
        """
        将 _active_streak_side 写入 _locked_streak_side。
        必须在 _finalize_sequence() 之前调用（因为前者会清除 _active_streak_side）。
        """
        self._locked_streak_side = self._active_streak_side

    def _reset_runtime(self):
        """
        完整重置：清理序列状态 + 清除 STREAK 锁。
        仅在换靴（SHOE END）场景使用。
        """
        self._active_streak_side = None
        self._locked_streak_side = None
        self._finalize_sequence()

    def _terminate(self, lock_streak: bool = True):
        """
        标准终止：结束当前 S1 生命周期。

        lock_streak=True  （默认）: 同时锁定本次 STREAK 方向，防止同向重复开仓。
        lock_streak=False （TIE_KILL 专用）: 仅结束 S1 生命周期，不影响 STREAK 锁。
            — TIE 不属于任何 STREAK，不应修改 STREAK 锁（L4 修复）。

        注意：_finalize_streak_lock() 必须先于 _finalize_sequence() 调用，
        因为后者会清除 _active_streak_side，而前者依赖该值。
        """
        if lock_streak:
            self._finalize_streak_lock()   # 先写锁（使用仍然有效的 _active_streak_side）
        self._finalize_sequence()          # 再清理运行时

    # =====================================================
    # 公开：启动序列
    # =====================================================
    def start(self, strategy_key: str, side: str, streak_side: str) -> dict:
        """
        Orchestrator 在检测到 EXECUTE 信号且引擎不处于 ACTIVE/B-LOCK 时调用。
        将状态从 SLEEP 推进到 ACTIVE，准备接受第一个 on_event()。

        参数
          strategy_key : 投注矩阵键（如 "100"）
          side         : 物理下注方向（B/P），由 _resolve_side 转换后传入
          streak_side  : 本次S1所属的STREAK方向（B/P），_terminate()时用于锁定方向
                         注意：CUT策略下 side != streak_side
        """
        self.state               = "ACTIVE"
        self.step_index          = 0
        self.strategy_key        = strategy_key
        self.active_side         = side
        self._streak_executed    = False
        self._active_streak_side = streak_side
        self._locked_streak_side = None          # 新STREAK开始，清除旧锁
        return {"action": "START", "state": self.state}

    # =====================================================
    # 公开：STREAK反转解锁
    # =====================================================
    def unlock_streak(self, new_side: str) -> None:
        """
        每帧 on_event() 之前由 Orchestrator 调用。
        当新 STREAK 方向与锁定方向不同时，解除方向锁。

        FIX-5 顺序说明：
        Orchestrator 必须按以下顺序调用：
          1. unlock_streak(cur_side)   ← 解锁（若发生反转）
          2. start(...)                ← 可能开仓（此时锁已正确）
          3. on_event(...)             ← 驱动状态机
        若 terminate() 和 unlock_streak() 在同帧发生，
        terminate() 先写锁再清序列，unlock_streak() 随后判断，
        只要 new_side != locked_side 就会解锁，逻辑正确。
        """
        if (self._locked_streak_side is not None
                and self._locked_streak_side != new_side):
            self._locked_streak_side = None

    # =====================================================
    # 公开：事件驱动入口
    # =====================================================
    def on_event(self, context: dict) -> dict:
        """
        每手结果产出后由 Orchestrator 调用一次。
        context 必须包含：
          last_result   str   本手结果 B / P / T
          is_match      bool  Orchestrator 的比对结论
          edge          float 当前优势值
          action_side   str   AI 建议方向（B/P）— FIX-2: 此字段不再用于更新 active_side
          is_reversal   bool  保留字段，当前未使用
        """

        # ── 阶段一：SLEEP ────────────────────────────────
        if self.state == "SLEEP":
            return {"action": "NO_OP"}

        # ── 提取上下文 ────────────────────────────────────
        result   = context.get("last_result")
        edge     = context.get("edge", 0)
        is_match = context.get("is_match", False)
        # FIX-2: 删除以下实时同步代码（原 v2 的"实时跟随，非死锁）
        # if current_side:
        #     self.active_side = current_side

        # ── 金额计算 ─────────────────────────────────────
        if result == "T":
            self.state = "B-LOCK"
            return {"action": "HOLD"}

        # ── 从 B-LOCK 恢复 ───────────────────────────────
        if self.state == "B-LOCK":
            self.state = "ACTIVE"

        # ── 此时 state 必然是 ACTIVE ─────────────────────

        # ── 阶段四：EXECUTION 熔断检查 ──────────────────
        # 规则一：序列中途 is_match 变 False → 立即终止（锁 STREAK）
        if not is_match:
            self._terminate(lock_streak=True)
            return {"action": "SLEEP"}

        # 规则二：唯一性锁 — 同一 streak_id 不打第二次
        if self._streak_executed:
            self._terminate(lock_streak=True)
            return {"action": "SLEEP"}

        # FIX-2: 删除以下实时同步代码（原 v2 的"实时跟随，非死锁"）
        # if current_side:
        #     self.active_side = current_side

        # ── 金额计算 ─────────────────────────────────────
        amount = self._get_amount(edge)

        # 规则三：金额为 0 → 立即终止（锁 STREAK）
        if amount == 0:
            self._terminate(lock_streak=True)
            return {"action": "SLEEP"}

        # ── 步进 ─────────────────────────────────────────
        step = self.step_index
        self.step_index += 1

        # ── 阶段四：序列完成（3 手打满）────────────────
        if self.step_index >= self._S1_LEN:
            self._streak_executed = True
            result_dict = {
                "action":     "BET",
                "amount":     amount,
                "side":       self.active_side,
                "step":       step,
                "next_state": "SLEEP",
            }
            self._terminate(lock_streak=True)
            return result_dict

        # ── 常规下注指令 ─────────────────────────────────
        return {
            "action": "BET",
            "amount": amount,
            "side":   self.active_side,
            "step":   step,
        }
