"""
BAC_PRO — StrategyEngine v2
四阶段状态控制器：SLEEP / WAIT / B-LOCK / EXECUTION

接口契约（与 v1 完全兼容，即插即用）
---------------------------------------
公开属性
  .state          str   当前状态，外部只读。Orchestrator 用它判断是否调用 start()
  .step_index     int   当前序列步数（0-based）

公开方法
  .start(strategy_key, side, streak_side)  → dict   启动一条新 STREAK
  .on_event(context)                       → dict   驱动状态机，返回操作指令
  .unlock_streak(new_side)                          STREAK反转时由Orchestrator调用，解除方向锁
  ._terminate(lock_streak=True)                     内部重置，外部不应调用但保留
                                                    lock_streak=False：只清序列状态，不写STREAK锁
                                                    用于TIE_KILL路径——TIE不属于任何STREAK，
                                                    不应通过_terminate()修改方向锁

返回指令（action 字段）
  BET    → 本手下注  {"action":"BET", "amount":int, "side":str, "step":int, "next_state"?:str}
  HOLD   → TIE 冻结  {"action":"HOLD"}
  SLEEP  → 熔断/完成 {"action":"SLEEP"}
  NO_OP  → 引擎空闲  {"action":"NO_OP"}

STREAK 级别锁说明
---------------------------------------
_active_streak_side : start() 时记录本次S1所属的STREAK方向（如 "B"）
_locked_streak_side : _terminate(lock_streak=True) 后锁住该方向，阻止同方向STREAK重复开仓
unlock_streak()     : 仅当新STREAK方向与锁定方向不同时解锁，由Orchestrator在
                      每帧on_event()之前调用

lock_streak 参数规则
---------------------------------------
True  （默认）：正常终止路径，用_active_streak_side写锁
               适用：is_match=False熔断 / amount=0熔断 / 3注打满 / 换靴reset
False         ：TIE_KILL路径，只归零序列状态，不改动_locked_streak_side
               原因：TIE不参与clean_seq，不属于任何STREAK，
                     若此时_active_streak_side=None（引擎本就是SLEEP），
                     lock_streak=True会把_locked_streak_side写成None，
                     等价于清掉了之前正确设置的锁，造成锁丢失
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
        # XYZ：三注金额均为 100 × (1 + edge)，edge 由每帧实时传入
        # 矩阵值 -2 为占位标记，实际金额在 _get_amount() 中动态计算
        "XYZ": [-2, -2, -2 ],
    }

    # S1 序列固定为 3 手
    _S1_LEN = 3

    def __init__(self):
        # ── 主状态 ──────────────────────────────────────────
        # SLEEP     : 空闲，等待外部 start() 唤醒
        # ACTIVE    : 序列执行中（对外等同于旧版 "ACTIVE"，Orchestrator 用此判断）
        # B-LOCK    : 和局冻结，挂起直到下一手有胜负
        self.state          = "SLEEP"
        self.step_index     = 0
        self.strategy_key   = None
        self.active_side    = None

        # ── 唯一性锁 ─────────────────────────────────────────
        # 同一条龙（streak_id）只允许打一次
        self._streak_executed = False

        # ── STREAK 级别方向锁 ────────────────────────────────
        # _active_streak_side : 本次S1启动时所属的STREAK方向，_terminate()用来决定锁哪个方向
        # _locked_streak_side : 已用完机会的STREAK方向，阻止Orchestrator在同方向重复start()
        self._active_streak_side = None
        self._locked_streak_side = None

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

    def _xyz_amount(self, edge: float) -> int:
        """
        XYZ 策略：每注金额 = 100 × (1 + edge)，三注相同。
        edge 为当前帧实时优势值，每次 on_event() 调用时重新计算。
        若 edge <= 0 则返回 0，触发熔断（与 AUTO edge<0.01 逻辑一致）。
        """
        if edge <= 0:
            return 0
        return int(100 * (1 + edge))

    def _get_amount(self, edge: float) -> int:
        if self.strategy_key == "AUTO":
            return self._auto_amount(edge)
        if self.strategy_key == "XYZ":
            return self._xyz_amount(edge)
        matrix = self.S1_STRATEGY_LIB.get(self.strategy_key, [0, 0, 0])
        if self.step_index >= len(matrix):
            return 0
        return matrix[self.step_index]

    # =====================================================
    # 公开：启动序列
    # =====================================================
    def start(self, strategy_key: str, side: str, streak_side: str) -> dict:
        """
        Orchestrator 在检测到 EXECUTE 信号且引擎不处于 ACTIVE 时调用。
        将状态从 SLEEP 推进到 ACTIVE，准备接受第一个 on_event()。

        参数
          strategy_key : 投注矩阵键（如 "100"）
          side         : 物理下注方向（B/P），由 _resolve_side 转换后传入
          streak_side  : 本次S1所属的STREAK方向（B/P），_terminate()时用于锁定方向
                         注意：CUT策略下 side != streak_side

        返回值供调用方记录，不强制使用。
        """
        self.state               = "ACTIVE"
        self.step_index          = 0
        self.strategy_key        = strategy_key
        self.active_side         = side
        self._streak_executed    = False
        self._active_streak_side = streak_side   # 记录本次S1所属的STREAK方向
        self._locked_streak_side = None          # 新STREAK开始，清除旧锁
        return {"action": "START", "state": self.state}

    # =====================================================
    # 公开：STREAK反转解锁
    # =====================================================
    def unlock_streak(self, new_side: str) -> None:
        """
        每帧 on_event() 之前由 Orchestrator 调用。
        当新STREAK方向与锁定方向不同时，说明已发生反转，解除方向锁。
        方向相同时不操作（同方向STREAK继续保持锁定）。
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
          action_side   str   AI 建议方向（B/P）
          is_reversal   bool  保留字段，当前未使用
        """

        # ── 阶段一：SLEEP ────────────────────────────────
        # 引擎空闲，外部未调用 start()，直接忽略
        if self.state == "SLEEP":
            return {"action": "NO_OP"}

        # ── 提取上下文 ────────────────────────────────────
        result         = context.get("last_result")
        edge           = context.get("edge", 0)
        current_side   = context.get("action_side")
        is_match       = context.get("is_match", False)

        # ── 阶段三：B-LOCK（和局冻结）───────────────────
        # 进入 B-LOCK 的唯一入口：本手结果为 T
        # 效果：
        #   - step_index 不自增（下一手仍从当前步数继续）
        #   - active_side 不更新（方向锁定到冻结前的最后一次 AI 建议）
        #   - 不执行结算比对（由 Orchestrator 的 TIE 短路保证，此处双重防护）
        if result == "T":
            self.state = "B-LOCK"
            return {"action": "HOLD"}

        # ── 从 B-LOCK 恢复 ───────────────────────────────
        # 非 T 结果出现，B-LOCK 解除，回到 ACTIVE 继续当前步
        if self.state == "B-LOCK":
            self.state = "ACTIVE"

        # ── 此时 state 必然是 ACTIVE ─────────────────────

        # ── 阶段四：EXECUTION 熔断检查 ──────────────────
        # 规则一：序列中途 is_match 变 False → 立即终止
        # 规则说明：NO MATCH代表无ACTION无下注方向，S1终止，本STREAK锁死
        if not is_match:
            self._terminate()          # lock_streak=True（默认），正常锁住当前STREAK
            return {"action": "SLEEP"}

        # 规则二：唯一性锁 — 同一 streak_id 不打第二次
        # （streak_executed 在 start() 里重置为 False，
        #   序列完成 3 手后置 True，防止 Orchestrator 重复 start）
        if self._streak_executed:
            self._terminate()
            return {"action": "SLEEP"}

        # ── 方向同步 ─────────────────────────────────────
        # 每手下注前实时跟随 AI 最新建议，不在 start() 时锁死
        if current_side:
            self.active_side = current_side

        # ── 金额计算 ─────────────────────────────────────
        amount = self._get_amount(edge)

        # 规则三：金额为 0（如 110 策略第 3 手）→ 立即终止，本STREAK锁死
        if amount == 0:
            self._terminate()
            return {"action": "SLEEP"}

        # ── 步进 ─────────────────────────────────────────
        # 记录当前步数，然后推进索引
        # 注意：B-LOCK 期间 result=="T" 已在上方提前返回，
        # 所以此处只有真实胜负手才会触发自增，符合设计规范
        step = self.step_index
        self.step_index += 1

        # ── 阶段四：序列完成（3 手打满）────────────────
        if self.step_index >= self._S1_LEN:
            self._streak_executed = True   # 唯一性锁定
            result_dict = {
                "action":     "BET",
                "amount":     amount,
                "side":       self.active_side,
                "step":       step,
                "next_state": "SLEEP",
            }
            self._terminate()
            return result_dict

        # ── 常规下注指令 ─────────────────────────────────
        return {
            "action": "BET",
            "amount": amount,
            "side":   self.active_side,
            "step":   step,
        }

    # =====================================================
    # 内部重置
    # =====================================================
    def _terminate(self, lock_streak: bool = True):
        """
        将状态机归零。

        lock_streak=True（默认，正常终止路径）：
          用 _active_streak_side 写入 _locked_streak_side，锁定本次S1所属STREAK方向。
          确保锁住的是"本次S1执行时的STREAK方向"，而不是终止帧的cur_side。

        lock_streak=False（TIE_KILL路径）：
          只清序列运行状态，不修改 _locked_streak_side。
          原因：TIE不属于任何STREAK，不应通过terminate修改方向锁。
          若此时引擎是SLEEP（_active_streak_side=None），
          lock_streak=True会把锁写成None，清掉之前正确设置的锁，造成锁丢失。
        """
        streak_to_lock           = self._active_streak_side if lock_streak else None
        self.state               = "SLEEP"
        self.step_index          = 0
        self.strategy_key        = None
        self.active_side         = None
        self._streak_executed    = False
        self._active_streak_side = None

        # lock_streak=True：写入锁（可能是None，表示无需锁定）
        # lock_streak=False：保持_locked_streak_side不变，不覆盖已有的锁
        if lock_streak:
            self._locked_streak_side = streak_to_lock
        # else: _locked_streak_side 保持原值不动
