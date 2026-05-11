# core/execution_center.py


class ExecutionCenter:
    def __init__(self, session_state, redis_adapter=None):
        self.ss = session_state
        self.redis = redis_adapter

    def execute(self, action: dict):
        act = action.get("action")

        if act in ["NO_OP", "HOLD"]:
            return

        if act == "BET":
            side   = action["side"]
            amount = action["amount"]
            step   = action.get("step", 0)

            # UI 下注框同步
            if side == "B":
                self.ss["bet_input_blue"] = amount
                self.ss["bet_input_red"]  = 0
            elif side == "P":
                self.ss["bet_input_red"]  = amount
                self.ss["bet_input_blue"] = 0

            self.ss["streak_bet_locked"] = True

            # ── 物理快照 ────────────────────────────────────────
            # 锁定下注瞬间的所有参数，结算时从此快照读取，
            # 不受后续 UI 滑块变动影响。
            #
            # side         = 物理投注方向（B/P），由 _resolve_side 转换后传入
            # streak_side  = 当前连庄方向（B/P），由 Orchestrator 在
            #                get_components() 后写入 session_state["current_streak_side"]
            # 两者的区别：CUT 策略下 side != streak_side（如庄连但下注闲）
            #             CONTINUE 策略下 side == streak_side
            self.ss["active_bet_record"] = {
                "side":         side,
                "streak_side":  self.ss.get("current_streak_side", "N/A"),
                "amount":       amount,
                "step":         step,
                "strategy_key": self.ss.get("current_strategy_key", "S1"),
                "h_len":        self.ss.get("hist_min_slider", 3),
                "b_len":        self.ss.get("current_cur_len",
                                self.ss.get("bet_len_slider_input", 3)),
            }

            if self.redis:
                self.redis.log_bet({
                    "side":        side,
                    "streak_side": self.ss.get("current_streak_side", "N/A"),
                    "amount":      amount,
                    "step":        step,
                    "h_len":       self.ss.get("hist_min_slider", 3),
                    "b_len":       self.ss.get("current_cur_len",
                                   self.ss.get("bet_len_slider_input", 3)),
                    "strategy":    self.ss.get("current_strategy_key", "S1"),
                })

        elif act in ["SLEEP", "RESET"]:
            self._clear_bet()

    def _clear_bet(self):
        self.ss["bet_input_red"]     = 0
        self.ss["bet_input_blue"]    = 0
        self.ss["streak_bet_locked"] = False
        if "active_bet_record" in self.ss:
            self.ss["active_bet_record"] = None
