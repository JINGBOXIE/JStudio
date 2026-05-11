from core.data_center import DataCenter
from core.decision_center import DecisionCenter
from core.strategy_engine import StrategyEngine
from core.db_adapter import RedisAdapter
from core.execution_center import ExecutionCenter
from core.settlement_center import SettlementCenter


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
        # 规范：TIE 时不重新计算 HASH，不步进，维持上一手建议不变。
        # =========================================================
        if last_result == "T":
            last_side = clean_seq[-2] if len(clean_seq) > 1 else ""
            executor = ExecutionCenter(session_state, self.redis_record)
            self.settlement_center.process(last_result, last_side, session_state)
            executor._clear_bet()
            existing_advice = session_state.get("last_fp_advice", {})
            session_state.last_fp_advice = {**existing_advice, "tie_hold": True}

            sys.stdout.write(
                f"⏸️  [TIE 短路] B-LOCK 激活，维持上一手建议，本帧终止\n"
                f"{_SEP}\n"
            )
            sys.stdout.flush()
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

        # CASE III 修复：写入实际连庄长度，供 ExecutionCenter 快照到 active_bet_record
        session_state["current_cur_len"]    = cur_len
        # 报表字段：写入连庄方向，供 ExecutionCenter 快照到 active_bet_record["streak_side"]
        # CUT 策略下 streak_side != side（如庄连下注闲），CONTINUE 时两者相同
        session_state["current_streak_side"] = cur_side

        # CASE V 修复：去掉硬编码的 and (cur_len >= 3)，唯一门槛由 UI 的 bet_len_threshold 控制
        should_match = (cur_len >= bet_len_threshold)
        state_hash = ""
        decision = {"state": "WAIT", "action": None, "edge": 0, "ev_cut": 0, "ev_cont": 0}

        if should_match:
            state_hash = self.data_center.build_hash_from_components(components)
            decision   = self.decision_center.execute_step(state_hash)
        else:
            state_hash = f"DEPTH：{cur_side}{cur_len}"

        # ── 方向合成 ────────────────────────────────────────────
        # decision["action"] 是逻辑指令（CUT/CONTINUE），不是物理方向（B/P）。
        # 必须结合当前连庄方向 cur_side 转换后再传给引擎。
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
        # unlock_streak() 检查当前帧的cur_side是否与锁定方向不同。
        # 不同 → 说明STREAK已反转 → 解锁，允许新STREAK开仓。
        # 相同 → 保持锁定，同方向STREAK不重复开仓。
        # 注意：必须在start()判断之前调用，否则新STREAK的第一帧
        # 会因为锁未解除而被跳过。
        self.strategy_engine.unlock_streak(cur_side)

        # ── 引擎启动判断 ─────────────────────────────────────────
        # 条件：
        #   1. 本帧有EXECUTE信号（is_match=True）
        #   2. 引擎当前不在ACTIVE（避免重复start）
        #   3. edge > 0（有正向优势才开仓）
        #   4. _locked_streak_side != cur_side（本STREAK未用过机会）
        #      — 这是STREAK级别锁，防止同一STREAK内因多次EXECUTE重复开仓
        #      — unlock_streak()已在上方处理反转解锁，此处只需判断是否锁定
        if is_match and self.strategy_engine.state != "ACTIVE":
            if current_edge > 0:
                if self.strategy_engine._locked_streak_side == cur_side:
                    # 本STREAK已用完机会，跳过，不调用start()
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
            "action_side": physical_side,
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
