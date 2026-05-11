#core/replay_manager.py
import streamlit as st
class ReplayManager:

    KEY = "hand_history"

    @staticmethod
    def _init():
        if ReplayManager.KEY not in st.session_state:
            st.session_state[ReplayManager.KEY] = []

    # =============================
    # 记录一局（核心）
    # =============================
    @staticmethod
    def record(res, current_bets, net_profit, oc):
        ReplayManager._init()

        trace = {
            "results": list(st.session_state.get("results", [])),
            "styled_results": list(st.session_state.get("styled_results", [])),
            "clean_results": list(st.session_state.get("clean_results", [])),

            "res": res,
            "bets": current_bets,
            "net_profit": net_profit,
            "balance": st.session_state.get("balance"),

            "ai": st.session_state.get("shared_ai_data"),

            "streak_counter": st.session_state.get("streak_counter"),
            "streak_locked": st.session_state.get("streak_bet_locked"),

            # 可选（更完整）
            "rank_counts": dict(st.session_state.get("rank_counts", {})),
            "stats": dict(st.session_state.get("stats", {})),
        }

        st.session_state[ReplayManager.KEY].append(trace)

    # =============================
    # 加载某一局（核心）
    # =============================
    @staticmethod
    def load(index):
        ReplayManager._init()

        history = st.session_state[ReplayManager.KEY]
        if not history or index >= len(history):
            return

        hand = history[index]

        st.session_state.results = list(hand["results"])
        st.session_state.styled_results = list(hand["styled_results"])
        st.session_state.clean_results = list(hand["clean_results"])

        st.session_state.streak_counter = hand["streak_counter"]
        st.session_state.streak_bet_locked = hand["streak_locked"]

        st.session_state.shared_ai_data = hand.get("ai")

        if "balance" in hand:
            st.session_state.balance = hand["balance"]

        if "rank_counts" in hand:
            st.session_state.rank_counts = dict(hand["rank_counts"])

        if "stats" in hand:
            st.session_state.stats = dict(hand["stats"])

        st.rerun()

    # =============================
    # UI（侧边栏）
    # =============================
    @staticmethod
    def render_sidebar():
        ReplayManager._init()

        history = st.session_state[ReplayManager.KEY]

        st.sidebar.subheader("Replay")

        if not history:
            st.sidebar.write("No history")
            return

        history_len = len(history)

        if history_len == 0:
            st.sidebar.info("No replay data yet")
            return

        if history_len == 1:
            idx = 1
            st.sidebar.write("Only 1 hand available")
        else:
            idx = st.sidebar.slider(
                "Select Hand",
                1,
                history_len,
                value=history_len
            )

        if st.sidebar.button("Load Replay"):
            ReplayManager.load(idx - 1)

        # 可选：显示当前局简要信息
        hand = history[idx - 1]
        st.sidebar.write(f"Result: {hand['res']}")
        st.sidebar.write(f"Profit: {hand['net_profit']}")
