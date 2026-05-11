# core/decision_center.py
class DecisionCenter:
    """
    DECISION CENTER
    只负责策略决策输出（3态系统）
    """

    def __init__(self, redis_adapter):
        self.adapter = redis_adapter

    def execute_step(self, state_hash: str):
        """
        return:
        {
            state: WAIT | EXECUTE | SLEEP
            action: B | P | None
            edge: float
        }
        """

        if not self.adapter:
            return {
                "state": "WAIT",
                "action": None,
                "edge": 0.0
            }

        decision = self.adapter.get_state_decision(state_hash)

        if not decision:
            return {
                "state": "WAIT",
                "action": None,
                "edge": 0.0
            }

        return {
            "state": "EXECUTE",
            "action": decision.get("action"),
            "edge": float(decision.get("edge", 0))
        }
