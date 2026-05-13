from core.data_center import DataCenter
from core.decision_center import DecisionCenter
from core.strategy_engine import StrategyEngine
from core.db_adapter import RedisAdapter
from core.execution_center import ExecutionCenter
from core.settlement_center import SettlementCenter

# =========================================================
# ⚙️ 全局配置控制
# =========================================================
TIE_KILL = "TIE_KILL"  # 遇到TIE，KILL，结束S1下注，终止下注结果并终止当前帧
TIE_SKIP = "TIE_SKIP"  # 遇到TIE，SKIP，继续S1下注，维持下注结果并继续后续策略逻辑
TIE_STRATEGY_MODE = TIE_SKIP


class Orchestrator:
    def __init__(self, data_center, decision_center, strategy_engine, redis_record):
        self.data_center = data_center
        self.decision_center = decision_center
        self.strategy_engine = strategy_engine
        self.redis_record = redis_record
        self.settlement_center = SettlementCenter(strategy_engine, redis_record)

    def run(self, context: dict, session_state: dict):

        # =========================================================
        # 🎰 【出生纸】物理事实诞生
        # =========================================================
        last_result = context.get("last_result")
        if not last_result:
            return None

        import sys
        _SEP = "=" * 48
        sys.stdout.write(f"\n{_SEP}\n")
        sys.stdout.write(f"🎰 [出生纸] 物理结果落地 : {last_result}\n")
        sys.stdout.flush()

        # =========================================================
        # 🪪 【身份证】序列登记 - update_seq 必须最先执行
        # clean_seq[-1] = 当前结果，clean_seq[-2] = 上一手
        # =========================================================
        clean_seq = self.data_center.update_seq(last_result)

        sys.stdout.write(
            f"🪪 [身份证] 序列入籍完成 : len={len(clean_seq)}"
            f"  tail={clean_seq[-4:]}\n"
        )
        sys.stdout.flush()

        # =========================================================
        # TIE 短路 — 身份证登记后立即判断
        # 规范：TIE 时不重新计算 HASH，不步进，维持上一手建议不变
        # =========================================================
        if last_result == "T":
            last_side = clean_seq[-2] if len(clean_seq) > 1 else ""
            executor = ExecutionCenter(session_state, self.redis_record)

            # 1. 执行结算处理（无论什么模式都要记录物理事实）
            self.settlement_center.process(last_result, last_side, session_state)

            # 2. 核心控制分支
            if TIE_STRATEGY_MODE == TIE_KILL:
                # --- 模式 1：TIE KILL (彻底熔断) ---
                # A. 清除物理下注记录与 UI 缓存
                executor._clear_bet()

                # B. FIX-4: 显式重置策略引擎内部状态，使其回到 SLEEP。
                #    传入 lock_streak=False：TIE 不属于任何 STREAK，
                #    只结束 S1 生命周期，不得修改 STREAK 锁（防止 L4 架构污染）。
                self.strategy_engine._terminate(lock_streak=False)

                sys.stdout.write(
                    f"🛑 [TIE 熔断] 模式: KILL | 引擎重置 (_terminate, lock_streak=False)"
                    f" | 物理记录清理\n"
                )
            else:
                # --- 模式 2：TIE SKIP (维持现状) ---
                sys.stdout.write(
                    f"⏭️  [TIE 跳过] 模式: SKIP | 引擎与记录均保持 ACTIVE，等待下一手\n"
                )

            # 3. 更新建议渲染状态
            existing_advice = session_state.get("last_fp_advice", {})
            session_state.last_fp_advice = {**existing_advice, "tie_hold": True}

            sys.stdout.write(f"{_SEP}\n")
            sys.stdout.flush()

            # 4. 统一阻断：TIE 帧不进入后续 HASH 匹配逻辑
            return {"decision": None, "engine": {"action": "HOLD"}}

        # =========================================================
        # Step 2: 旧账结算 - 先结算再释放 UI 锁定
        # =========================================================
        last_side = clean_seq[-2] if len(clean_seq) > 1 else ""
        executor = ExecutionCenter(session_state, self.redis_record)
        self.settlement_center.process(last_result, last_side, session_state)
        executor._clear_bet()

        # =========================================================
        # 🎓 【学生证】HASH 比对
        # =========================================================
        h_min             = session_state.get("hist_min_slider", 3)
        bet_len_threshold = session_state.get("bet_len_slider_input", 3)
        current_strat_key = session_state.get("current_strategy_key", "000")

        components = self.data_center.get_components(clean_seq, h_min)
        cur_side, cur_len = components[0], components[1]

        # 报表字段写入
        session_state["current_cur_len"]     = cur_len
        session_state["current_streak_side"] = cur_side

        should_match = (cur_len >= bet_len_threshold)
        state_hash = ""
        decision = {"state": "WAIT", "action": None, "edge": 0, "ev_cut": 0, "ev_cont": 0}

        if should_match:
            state_hash = self.data_center.build_hash_from_components(components)
            decision   = self.decision_center.execute_step(state_hash)
        else:
            state_hash = f"DEPTH：{cur_side}{cur_len}"

        # ── 方向合成 ────────────────────────────────────────────
        def _resolve_side(action: str, side: str) -> str:
            opposite = "P" if side == "B" else "B"
            if action == "CUT":
                return opposite
            if action in ("CONTINUE", "S"):
                return side
            return action if action in ("B", "P") else side

        physical_side = _resolve_side(decision.get("action", ""), cur_side)

        sys.stdout.write(
            f"🎓 [学生证] HASH 比对完成\n"
            f"           hash      : {state_hash}\n"
            f"           cur       : {cur_side}{cur_len}"
            f"  should_match={should_match}\n"
            f"           decision  : state={decision['state']}"
            f"  action={decision.get('action')}"
            f"  edge={decision.get('edge', 0):+.4f}\n"
            f"           →物理方向 : {decision.get('action')} + {cur_side}"
            f" = {physical_side}\n"
        )
        sys.stdout.flush()

        # =========================================================
        # 💼 【工作证】策略引擎指令
        # =========================================================
        is_match     = (decision["state"] == "EXECUTE")
        current_edge = decision.get("edge", 0)

        # ── STREAK反转检测（必须在start()之前执行）──────────────
        # FIX-5 顺序保证：unlock_streak() 先于 start() 执行。
        # terminate() 在上一帧已写好 _locked_streak_side（使用的是那一帧的
        # _active_streak_side），本帧 unlock_streak() 读取该锁并判断是否反转，
        # 逻辑不会因同帧顺序问题而错乱。
        self.strategy_engine.unlock_streak(cur_side)

        # ── 引擎启动判断 ─────────────────────────────────────────
        if is_match and self.strategy_engine.state not in ("ACTIVE", "B-LOCK"):
            if current_edge > 0:
                if self.strategy_engine._locked_streak_side == cur_side:
                    pass
                else:
                    self.strategy_engine.start(
                        strategy_key=current_strat_key,
                        side=physical_side,   # 物理下注方向（CUT策略下与cur_side相反）
                        streak_side=cur_side  # STREAK方向，_terminate()时用于锁定
                    )

        engine_output = self.strategy_engine.on_event({
            "last_result": last_result,
            "is_match":    is_match,
            "edge":        current_edge,
            "action_side": physical_side,  # FIX-2: on_event内部不再使用此字段更新side
            "is_reversal": False,
        })

        executor.execute(engine_output)

        sys.stdout.write(
            f"💼 [工作证] 引擎指令下发\n"
            f"           engine   : action={engine_output.get('action')}"
            f"  amount={engine_output.get('amount', '—')}"
            f"  side={engine_output.get('side', '—')}"
            f"  step={engine_output.get('step', '—')}\n"
            f"           eng.state: {self.strategy_engine.state}"
            f"  step_index={self.strategy_engine.step_index}\n"
            f"           streak_lock: {self.strategy_engine._locked_streak_side}\n"
            f"{_SEP}\n"
        )
        sys.stdout.flush()

        # =========================================================
        # Step 5: 建议渲染 - 写入 UI 所需完整字段
        # =========================================================
        session_state.last_fp_advice = {
            "match":    is_match,
            "fp_id":    state_hash if state_hash else "READY",
            "action":   decision.get("action", "?"),
            "edge":     current_edge,
            "ev_cut":   decision.get("ev_cut", 0),
            "ev_cont":  decision.get("ev_cont", 0),
            "status":   "MATCHED" if is_match else (
                        "SCANNING" if should_match else "DEPTH_INSUFFICIENT"),
            "tie_hold": False,
        }

        return {"decision": decision, "engine": engine_output}
