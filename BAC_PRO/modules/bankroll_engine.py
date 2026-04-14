import streamlit as st

def initialize_bankroll(initial_balance=10000.0):
    if 'balance' not in st.session_state:
        st.session_state.balance = float(initial_balance)
    if 'bet_history' not in st.session_state:
        st.session_state.bet_history = []

def settle_hand(winner, bets, current_balance):
    """
    核心结算逻辑
    bets: dict {'B': int, 'P': int, 'T': int}
    """
    total_bet = sum(bets.values())
    if total_bet == 0:
        return current_balance, 0, "No Bet"

    payout = 0
    # 1. 庄赢结算: 1 赔 0.95 (抽水 5%)
    if winner == 'B':
        payout = bets['B'] * 1.95
    
    # 2. 闲赢结算: 1 赔 1
    elif winner == 'P':
        payout = bets['P'] * 2.0
        
    # 3. 和局结算: 1 赔 8，且退回庄闲本金
    elif winner == 'T':
        payout = (bets['T'] * 9.0) + bets['B'] + bets['P']

    net_profit = payout - total_bet
    new_balance = current_balance + net_profit
    
    return round(new_balance, 2), round(net_profit, 2), f"Winner: {winner}"

def log_transaction(hand_no, winner, bets, profit, balance):
    entry = {
        "Hand #": hand_no,
        "Outcome": winner,
        "Bets (B/P/T)": f"{bets['B']}/{bets['P']}/{bets['T']}",
        "Profit": profit,
        "Balance": f"{balance:,.2f}"
    }
    st.session_state.bet_history.insert(0, entry)