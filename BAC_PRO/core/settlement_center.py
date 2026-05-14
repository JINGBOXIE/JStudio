# core/settlement_center.py
from core.execution_center import ExecutionCenter


class SettlementCenter:
    """
    原子化结算中心：负责损益计算、佣金处理及数据库同步

    生命周期说明
    ------------
    SettlementCenter 只负责"账"，不干预引擎状态。
    StrategyEngine v2 自管理生命周期：
      - 3 手完成 → 引擎内部 _terminate()
      - is_match=False / amount=0 熔断 → 引擎内部 _terminate()
      - TIE → Orchestrator 层短路，引擎 B-LOCK 冻结
    结算中心不应在任何情况下主动调用 strategy_engine._terminate()。
    """

    def __init__(self, strategy_engine, redis_record=None):
        self.strategy_engine = strategy_engine
        self.redis_record = redis_record

    def process(self, last_result, last_side, session_state):
        """执行完整结算流程"""
        # 1. 凭证校验
        record    = session_state.get("active_bet_record")
        is_locked = session_state.get("streak_bet_locked")
        if not record or not is_locked:
            return None

        #print(f"🏦结算清单: Result={last_result}, Locked={is_locked}, Record={record}")

        # 2. 计算盈亏 (P/L)
        p_l = self._calculate_pl(
            last_result=last_result,
            bet_side=record["side"],
            amount=record["amount"]
        )

        # 3. 策略反馈（仅诊断，不干预引擎生命周期）
        self._update_strategy_state(last_result, record["side"])

        # 4. 同步数据库（只有非和局才写入流水）
        if p_l != 0:
            self._sync_to_redis(p_l, record, last_side, session_state)

        return p_l

    def _calculate_pl(self, last_result, bet_side, amount):
        """核心赔率与佣金算法"""
        if last_result == "T":
            return 0
        if last_result == bet_side:
            return amount * 0.95 if bet_side == "B" else amount
        return -amount


    def _update_strategy_state(self, last_result, bet_side):
        """
        不干预引擎生命周期，仅做只读诊断日志。
        引擎状态由 StrategyEngine v2 自管理。
        """
        if last_result == "T":

            print(
                f"🏦 Confirmed: 🟢TIE detected "
                f"(bet={bet_side}, result={last_result})"
            )

        elif last_result == bet_side:

            print(
                f"🏦 Confirmed: 🥇WIN detected "
                f"(bet={bet_side}, result={last_result})"
            )

        else:

            print(
                f"🏦 Confirmed: ❌LOSS detected "
                f"(bet={bet_side}, result={last_result})"
            )

        
        

    def _sync_to_redis(self, p_l, record, last_side, session_state):
        """持久化流水 — 写入 monitor_user_live 所需的全部字段"""
        if not self.redis_record:
            return
        try:
            uid       = session_state.get("auth_user", "J")
            # action 由下注方向与连庄方向比对得出
            act_label = "CONTINUE" if record["side"] == last_side else "CUT"

            self.redis_record.sync_transaction(
                uid=uid,
                username=session_state.get("username", f"User_{uid}"),
                amount=p_l,
                tx_type="AUTORUN",
                strategy=record.get("strategy_key") or session_state.get("current_strategy_key", "S1"),
                h_len=record.get("h_len", session_state.get("hist_min_slider", 3)),
                b_len=record.get("b_len", session_state.get("bet_len_slider_input", 3)),
                action=act_label,
                # ── 新增：monitor 报表所需字段 ──────────────────
                side=record.get("side", "N/A"),               # 物理下注方向 B/P
                streak_side=record.get("streak_side", "N/A"), # 连庄方向 B/P
            )
        except Exception as e:
            print(f"❌ [SettlementCenter Error]: {e}")
