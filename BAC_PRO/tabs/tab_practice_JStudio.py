# ---------------------------------------------------------
# tab_practice_JStudio——V6.py
#完全测试后的S1_STRATEGY_LIB下注策略， Bet最小注的起点开始下注和比对，否则忽略 V3
#这里增加同一个DEAL共享一次查询结果 V4
#增加AUTO STRATEGY V5
#增加真实的余额查询供练习，不再使用1M虚拟值 V6
# ---------------------------------------------------------
import streamlit as st
import os
import sys
import pandas as pd
import random
import redis
import time 
import json
import streamlit.components.v1 as components
# 1. 路径注入
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from modules.i18n import TRANSLATIONS
from modules.road_renderer import render_big_road
from modules.stats_manager import update_shoe_stats
from modules.bankroll_engine import initialize_bankroll, settle_hand
from dealer.baccarat_dealer import BaccaratDealer, ShoeFactory
from modules.ui_components import render_casino_table, render_bias_panel, render_snapshot_ai
from core.sbi_full_model import compute_sbi_ev_from_counts
from core.snapshot_engine import get_fp_components
from core.db_adapter import RedisAdapter, generate_fp_hash 
# --- 在文件顶部定义全局常量 ---
S1_STRATEGY_LIB = {
    "100": [100, 0, 0],
    "110": [100, 100, 0],
    "111": [100, 100, 100],
    "121": [100, 200, 100],
    "137": [100, 300, 700]
}
# --- 1. 弹窗定义区 (从 Redis 实时提取) ---


@st.dialog("📊 最近 20 手下注" if st.session_state.get('lang') == "CN" else "📊 Recent 20 Bets")
def show_recent_bets_dialog():
    record_adapter = st.session_state.get('record_adapter')
    uid = st.session_state.get('auth_user', "J")
    is_cn = st.session_state.get('lang') == "CN"
    
    if not record_adapter:
        st.error("Redis Error")
        return

    try:
        r = record_adapter.client
        # 1. 按照 check_redis.py 逻辑，先从 List 拿 ID
        tx_ids = r.lrange(f"u:tx_list:{uid}", 0, 19)
        if not tx_ids:
            st.info("暂无记录" if is_cn else "No records.")
            return

        # 2. 遍历 ID 拿 Hash 详情
        all_records = []
        for tid in tx_ids:
            data = r.hgetall(f"tx:{tid}")
            if data:
                all_records.append(data)
        
        df = pd.DataFrame(all_records)
        
        # 中英文列名映射
        col_map = {
            'datetime': '时间' if is_cn else 'Time',
            'type': '类型' if is_cn else 'Type',
            'amount': '盈亏' if is_cn else 'Net',
            'action': '动作' if is_cn else 'Action',
            'bet_len': '下注点' if is_cn else 'BetPoint',
            'strategy': '策略' if is_cn else 'Strategy'
        }
        
        # 过滤并重命名列
        df = df[[c for c in col_map.keys() if c in df.columns]]
        df.rename(columns=col_map, inplace=True)
        
        st.dataframe(df, width="stretch")
    except Exception as e:
        st.error(f"Error: {e}")



@st.dialog("📈 综合报表" if st.session_state.get('lang') == "CN" else "📈 Analytics")
def show_summary_report_dialog():
    record_adapter = st.session_state.get('record_adapter')
    uid = st.session_state.get('auth_user', "J")
    is_cn = st.session_state.get('lang') == "CN"
    
    if not record_adapter:
        st.error("Redis Error: Adapter not found.")
        return

    try:
        r = record_adapter.client
        tx_ids = r.lrange(f"u:tx_list:{uid}", 0, -1)
        
        if not tx_ids:
            st.info("暂无记录" if is_cn else "No records found.")
            return

        # 1. 数据映射与标准化 (根据你的 Redis 结构)
        all_records = []
        for tid in tx_ids:
            data = r.hgetall(f"tx:{tid}")
            if data:
                all_records.append({
                    'exec_mode': str(data.get('type', 'N/A')).upper(),
                    'bet_logic': str(data.get('strategy', 'N/A')).upper(),
                    'action': str(data.get('action', 'N/A')).upper(),
                    'hist_len': f"LEN-{data.get('hist_len', '0')}",
                    'bet_len': f"STREAK-{data.get('bet_len', '0')}",
                    'amount': float(data.get('amount', 0))
                })
        
        df = pd.DataFrame(all_records)

        # 2. 核心计算
        def get_metrics(filter_col=None, filter_val=None):
            subset = df if filter_col is None else df[df[filter_col] == filter_val]
            count = len(subset)
            vol = subset['amount'].abs().sum() if count > 0 else 0.0
            pl = subset['amount'].sum() if count > 0 else 0.0
            avg = pl / count if count > 0 else 0.0
            return count, vol, pl, avg

        # 3. 动态生成表格行
        def build_rows(cat_label, col):
            rows = ""
            unique_vals = sorted(df[col].unique())
            for i, val in enumerate(unique_vals):
                cnt, vol, pl, avg = get_metrics(col, val)
                color = "#00FFAA" if pl >= 0 else "#FF4B4B"
                rows += f"""
                <tr style="border-bottom: 1px solid #222;">
                    <td style="padding:10px; color:#BBB; font-weight:bold;">{cat_label if i==0 else ""}</td>
                    <td style="color:#888;">{val}</td>
                    <td style="text-align:center;">{cnt}</td>
                    <td style="text-align:right;">${vol:,.2f}</td>
                    <td style="text-align:right; color:{color}; font-weight:bold;">${pl:,.2f}</td>
                    <td style="text-align:right;">${avg:,.2f}</td>
                </tr>"""
            return rows

        # 4. 构建完整的 HTML 页面代码
        # 强制使用独立 CSS，避免 Streamlit 干扰
        html_content = f"""
        <div style="background:#111; padding:15px; border-radius:10px; color:#EEE; font-family: monospace; font-size: 13px;">
            <table style="width:100%; border-collapse: collapse;">
                <thead>
                    <tr style="border-bottom: 2px solid #444; color: #777; text-align: left;">
                        <th style="padding:10px;">Category</th>
                        <th>Grouping</th>
                        <th style="text-align:center;">Count</th>
                        <th style="text-align:right;">Total Vol.</th>
                        <th style="text-align:right;">Net P/L</th>
                        <th style="text-align:right;">Avg. P/L</th>
                    </tr>
                </thead>
                <tbody>
                    {build_rows("Exec Mode", "exec_mode")}
                    {build_rows("Bet Logic", "bet_logic")}
                    {build_rows("Action", "action")}
                    {build_rows("Snapshot Depth", "hist_len")}
                    {build_rows("Betting Point", "bet_len")}
                </tbody>
                <tfoot>
                    <tr style="background: rgba(255,255,255,0.1); font-weight: bold;">
                        <td colspan="2" style="padding:12px; color:#FFF;">SUMMARY OVERALL</td>
                        <td style="text-align:center;">{get_metrics()[0]}</td>
                        <td style="text-align:right;">${get_metrics()[1]:,.2f}</td>
                        <td style="text-align:right; color:#00FFAA;">${get_metrics()[2]:,.2f}</td>
                        <td style="text-align:right;">${get_metrics()[3]:,.2f}</td>
                    </tr>
                </tfoot>
            </table>
        </div>
        """

        # 5. 唯一渲染出口：使用 HTML 组件锁定显示效果
        # 设置足够的高度以避免滚动条
        components.html(html_content, height=600, scrolling=True)

    except Exception as e:
        st.error(f"Render Error: {e}")

    # 6. 交互按钮
    if st.button("CLOSE", width="stretch"):
        st.session_state.menu_choice = "GAMING LOGIC"
        st.rerun()


def process_betting_logic():
    """
    核心下注大脑：
    1. 检查路单是否存在。
    2. 检查 3 注序列计数器是否已满。
    3. 从共享仓库获取指纹比对结果 (代替原有的实时 Redis 请求)。
    4. 只有 MATCH (存在 action) 且符合方向，才执行下注。
    """
    
    # 1. 基础数据准备
    clean_seq = st.session_state.get('clean_results', []) 
    if not clean_seq:
        return

    # 获取用户在侧边栏设定的参数 (b_len 已在共享数据生成时拦截，此处保留用于打印)
    cur_side = clean_seq[-1]
    cur_len = 0
    for x in reversed(clean_seq):
        if x == cur_side:
            cur_len += 1
        else:
            break
        
    # 2. 序列上限拦截：如果 S1 矩阵的 3 注已完成，则停止下注
    if st.session_state.get('streak_counter', 0) >= 3:
        return

    # --- 【唯一必须修改的逻辑点：从共享仓库获取比对结果】 ---
    shared_payload = st.session_state.get('shared_ai_data')
        
    # 如果没有共享数据，或者数据中没有 decision (说明路长不达标或 Redis 无匹配)，则直接退出
    if not shared_payload or shared_payload.get('decision') is None:
        return

    # 提取原有逻辑需要的变量 (保持变量名与原程序一致)
    decision = shared_payload['decision']
    state_hash = shared_payload['hash'] 
        # ---------------------------------------------------

    # 5. 下注执行判定 (完全保留原有的判定与打印逻辑)
    if decision and decision.get('action'):
        raw_act = str(decision['action']).upper()

        # 打印策略匹配成功信息—GEGIN (完全保留原有格式)
        edge = decision.get('edge', 0)
        print(f"\n[AI INSTRUCTION NOW] 🎯 MATCH FOUND!")
        print(f"  └─ Hash: {state_hash}")
        print(f"  └─ Action: {raw_act} | Edge: {edge:+.2%}")
        print(f"  └─ Current Side: {cur_side} (Len: {cur_len})")
        # 打印策略匹配成功信息-END
            
        # 根据 AI 给出的 ACTION 实时确定下注方向 (S=顺势/STAY, C=反势/CUT)
        if "S" in raw_act:
            target_side = cur_side
        elif "C" in raw_act:
            target_side = 'P' if cur_side == 'B' else 'B'
        else:
            return 

        # 6. 调用执行器，从 S1_STRATEGY_LIB 矩阵中根据 counter 提取注码
        execute_strategy_bet(target_side, decision.get('edge', 0))
        
def execute_strategy_bet(side, edge=0):
    # 1. 获取用户在 UI 界面选择的原始策略 Key
    current_strat = st.session_state.get('current_strategy_key', "100")

    # --- 【S2 必须修改点】：仅当选择 AUTO 时，才根据 Edge 动态覆盖 strat_key ---
    if current_strat == "AUTO":
        if edge >= 0.05:
            strat_key = "137"
        elif edge >= 0.04:
            strat_key = "121"
        elif edge >= 0.03:
            strat_key = "111"
        elif edge >= 0.02:
            strat_key = "110"
        elif edge >= 0.01:
            strat_key = "100"
        else:
            # Edge 低于 1% 时，不执行任何下注动作
            print(f"[BET FOR NEXT] ⏩ S2 SKIP: Edge {edge:.2%} too low.")
            return
    else:
        # 如果不是 AUTO，则直接使用用户选择的固定策略 (原有逻辑)
        strat_key = current_strat

    # --- 以下完全保留原有逻辑和变量 ---
    amounts = S1_STRATEGY_LIB.get(strat_key, [100, 100, 100])
    counter = st.session_state.get('streak_counter', 0)
            
    # 安全检查：防止索引越界
    if counter < len(amounts):
        current_amt = amounts[counter]
                
        if current_amt > 0:
            if side == 'B':
                st.session_state.bet_input_red = current_amt
                st.session_state.bet_input_blue = 0
            else:
                st.session_state.bet_input_blue = current_amt
                st.session_state.bet_input_red = 0
                    
            # 获取上一手的 P/L 用于输出 (直接从 session 提取)
            res_val = st.session_state.get('last_win_loss', 0)
                    
            # 增强后台下注打印 (增加 S2 标识和 Prev_P/L)
            print(f"[BET FOR NEXT] 💰 S2 EXECUTION: Side={side} | Amount={current_amt} | S1_Step={counter+1}/3 | Strat={strat_key}")
        else:
            print(f"[BET FOR NEXT] ⏩ SKIP: Amount is 0 for S1 Step {counter+1}")
            
def render_practice_tab(lang):
    # --- 1. 全量变量保底初始化 (防止 AttributeError) ---
    # 在 initial_keys 或变量初始化区域添加
    if 'streak_counter' not in st.session_state: st.session_state.streak_counter = 0  # 0, 1, 2, 3
    if 'current_strategy_key' not in st.session_state: st.session_state.current_strategy_key = "111" # 默认使用111
    if 'active_streak_side' not in st.session_state: st.session_state.active_streak_side = None # 锁定下注时的方向
    initial_keys = {
        'results': [], 'clean_results': [], 'styled_results': [],
        'shoe': [], 'cut_card_at': 14, 'shoe_count': 0, 'balance': 0.0,
        'stats': {"B": 0, "P": 0, "T": 0}, 'end_shoe': False,
        'auto_run_active': False, 'strategy_mode': "Single Bet"
    }
    for key, val in initial_keys.items():
        if key not in st.session_state:
            st.session_state[key] = val

    # 定义常量约束
    MAX_SHOES = 10000
    is_cn = lang == "CN"

    # --- 1. 初始化变量 ---
    if 'bet_input_red' not in st.session_state: st.session_state.bet_input_red = 0
    if 'bet_input_blue' not in st.session_state: st.session_state.bet_input_blue = 0
    if 'auto_run_active' not in st.session_state: st.session_state.auto_run_active = False
    if 'marker_mode' not in st.session_state: st.session_state.marker_mode = False
    if 'styled_results' not in st.session_state: st.session_state.styled_results = []
    if 'clean_results' not in st.session_state: st.session_state.clean_results = []
    # 🎯 就在这里添加：
    if 'shoe_count' not in st.session_state: st.session_state.shoe_count = 0
    if 'max_shoes' not in st.session_state: st.session_state.max_shoes = 1000  # 修改这里来设定运行多少靴
    # 确保在同一个 Streak (连庄或连闲) 中只下一注
    if 'streak_bet_locked' not in st.session_state: st.session_state.streak_bet_locked = False
    # 在 render_practice_tab 函数内的变量初始化区域添加：
    if 'bet_len_slider' not in st.session_state: st.session_state.bet_len_slider = 1
    if 'strategy_mode' not in st.session_state: st.session_state.strategy_mode = "单注 (Streak-1)"
    # --- 约第 35 行附近 ---
    if 'ai_zone_container' not in st.session_state: st.session_state.ai_zone_container = st.empty()

    # --- 2. 语言与样式初始化 (核心修复：提前定义 lt) ---
    lt = TRANSLATIONS.get(st.session_state.lang, {})
    def t(key): return TRANSLATIONS.get(st.session_state.lang, {}).get(key, key)
    
    container_style = "padding:18px;border:2px solid #1E90FF;border-radius:15px;background-color:#0a141e;box-shadow:0 4px 15px rgba(0,0,0,0.5);min-height:320px;color:#FFFFFF;display:flex;flex-direction:column;box-sizing:border-box;"
    header_style = "font-weight:bold;color:#1E90FF;font-size:1.1rem;letter-spacing:1px;margin-bottom:12px;border-bottom:1px solid #1E90FF44;padding-bottom:8px;display:flex;justify-content:space-between;align-items:center;"


    def run_auto_engine():
        # --- A. 自动续靴逻辑 (保持不变) ---
        if st.session_state.get('end_shoe', False):
            if st.session_state.auto_run_active:
                # 在重置前，确保打印最后一次结算日志，或手动强制一次同步检查
                print(f"[SYSTEM] Shoe Ended. Final Balance: {st.session_state.balance}")
                st.session_state.shoe_count += 1 
                if st.session_state.shoe_count >= st.session_state.get('max_shoes', 10):
                    st.session_state.auto_run_active = False
                    return 
                time.sleep(0.2)
                reset_logic()
                time.sleep(0.5)

        # --- B. 基础运行条件 ---
        if st.session_state.balance < 100:
            st.session_state.auto_run_active = False
            return

        # --- C. 只有在自动运行且未锁定时，才由“大脑”统一决策 ---
        # 这样可以确保自动运行时，决策只发生在这里，不重复放气球
        if not st.session_state.get('streak_bet_locked', False):
            process_betting_logic() # 使用之前重构的“大脑”函数

        # --- D. 执行物理发牌 ---
        handle_deal_click()
    
    def reset_logic():
        # A. 检查靴数上限
        if st.session_state.shoe_count >= MAX_SHOES:
            msg = f"已达到最大练习靴数 ({MAX_SHOES})。" if is_cn else f"Max shoes reached ({MAX_SHOES})."
            st.error(msg)
            st.stop()
            return

        # B. 检查余额 (新靴开始前必须校验)
        if st.session_state.balance < 100:
            msg = "余额不足，无法开启新靴。" if is_cn else "Insufficient balance for new shoe."
            st.error(msg)
            st.stop()
            return
        if 'factory' not in st.session_state:
            st.session_state.factory = ShoeFactory()
        st.session_state.shoe = st.session_state.factory.create_shoe()
        st.session_state.cut_card_at = random.randint(14, 20)
        st.session_state.end_shoe = False
        st.session_state.results = []
        st.session_state.clean_results = []
        st.session_state.styled_results = []
        st.session_state.bet_history = []
        st.session_state.stats = {"B": 0, "P": 0, "T": 0}
        st.session_state.rank_counts = {i: (128 if i == 0 else 32) for i in range(10)}
        st.session_state.last_outcome_obj = None
        st.session_state.last_fp_advice = {"match": False, "fp_id": "READY", "action": "WAIT"}
        st.session_state.streak_bet_locked = False

        # --- 修正后的代码块 (请直接替换) ---
    if 'bac_pro_v8_final' not in st.session_state:
        st.session_state.bac_pro_v8_final = True
        st.session_state.dealer = BaccaratDealer()
        st.session_state.factory = ShoeFactory(decks=8)
        
        # 严格余额同步
        if 'balance' not in st.session_state or st.session_state.balance == 0:
            rw = st.session_state.get('record_adapter')
            # 拿到当前真实的 UID
            target_uid = st.session_state.get('auth_user', "J") 
            
            if rw:
                db_val = rw.client.hget(f"u:info:{target_uid}", "balance")
                if db_val is not None:
                    st.session_state.balance = float(db_val)
                else:
                    st.session_state.balance = 0.0
            else:
                st.session_state.balance = 0.0
        
        # ！！重置逻辑必须缩进到这个 if 块里面 ！！
        reset_logic()
        
     
        
    def handle_deal_click():
        # 0. 初始状态重置
        is_ai_match = False
        current_action = None
        
        # A. 余额不足拦截
        if st.session_state.balance < 100:
            is_cn = st.session_state.get('lang') == "CN"
            msg = "余额不足，发牌停止。" if is_cn else "Insufficient balance, dealing stopped."
            st.warning(msg)
            st.session_state.auto_run_active = False 
            return
            
        if 'styled_results' not in st.session_state: st.session_state.styled_results = []
        if 'clean_results' not in st.session_state: st.session_state.clean_results = []

        # --- 1. Redis 初始化 ---
        if 'redis_adapter' not in st.session_state or 'record_adapter' not in st.session_state:
            try:
                prod_url = st.secrets["BACC_PRO_PROD"]["REDIS_URL"]
                st.session_state.redis_adapter = RedisAdapter(prod_url)
                record_url = st.secrets["UNIFIED_ACCOUNT_SYSTEM"]["REDIS_URL"]
                st.session_state.record_adapter = RedisAdapter(record_url)
            except Exception as e:
                st.error(f"Redis 初始化失败: {e}")

        bet_b = st.session_state.get("bet_input_red", 0)
        bet_p = st.session_state.get("bet_input_blue", 0)
        current_bets = {"B": int(bet_b), "P": int(bet_p), "T": 0}
        total_bet = sum(current_bets.values())

        if total_bet <= st.session_state.balance:
            try:
                # --- 2. 锁定发牌前的快照 ---
                pre_deal_seq = list(st.session_state.get('clean_results', []))
                pre_cur_side = pre_deal_seq[-1] if pre_deal_seq else None
                pre_cur_len = 0
                if pre_cur_side:
                    for x in reversed(pre_deal_seq):
                        if x == pre_cur_side: pre_cur_len += 1
                        else: break
                
                # 记录下注瞬间的连开长度
                betting_moment_len = pre_cur_len

                # --- 3. 物理发牌 ---
                oc = st.session_state.dealer.deal_one_hand(st.session_state.shoe)
                st.session_state.last_outcome_obj = oc
                res = oc.winner
                print(f"\n[BACKEND-3] 最新发牌结果: {res}")

                # --- 4. 结算 (已重构) ---
                # 仅调用 settle_hand 来计算该手的 net_profit
                # 传入 st.session_state.balance 仅作为基数参考，我们不再使用其返回的 new_bal
                _, net_profit, _ = settle_hand(res, current_bets, st.session_state.balance)

                # 注意：这里删掉了 st.session_state.balance = new_bal

                # ---  handle_deal_click 中的计数逻辑 ---
                actual_bet_made = current_bets["B"] + current_bets["P"]
                if actual_bet_made > 0:
                    if res in ['B', 'P']:  # 严格限制只有 B 或 P 才增加计数
                        st.session_state.streak_counter += 1
                        print(f"[STRATEGY EXCUTION] ✅ Effective Bet Counted（锁定下注➕开牌/上手的结算）: {st.session_state.streak_counter}/3")
                    else:
                        # 遇到 T 时，明确不增加计数器，确保下一手依然使用当前的 Step 注码
                        print(f"[STRATEGY EXCUTION] 🟡 TIE Detected - Counter held at: {st.session_state.streak_counter}/3")
                        
                # --- 5. AI 决策判定 (全面拦截版本) ---
                adapter = st.session_state.get('redis_adapter')
                h_min = st.session_state.get('h_min_slider', 3) 
                b_len_threshold = st.session_state.get('bet_len_slider_input', 1) # 获取路长拦截阈值
                
                if adapter and res in ['B', 'P']:
                    # 构造包含刚刚出的结果的序列 (原有逻辑)
                    current_full_seq = pre_deal_seq + [res]
                    
                    # A. 计算这一手产生后的连开长度 (原有逻辑)
                    check_side = current_full_seq[-1]
                    check_len = 0
                    for x in reversed(current_full_seq):
                        if x == check_side: check_len += 1
                        else: break
                    
                    # --- 【新增需求 1】：每个 DEAL 都需要计算指纹，用于 UI 状态同步 ---
                    components = get_fp_components(current_full_seq, h_min=h_min)
                    state_hash = generate_fp_hash(*components)
                    
                    # 预设共享变量的基础结构，确保 UI 始终能拿到当前的 Hash
                    shared_payload = {
                        "hash": state_hash,
                        "decision": None,
                        "status": f"WAITING ({check_len}/{b_len_threshold})"
                    }

                    # B. 【全面拦截点】只有长度达标才请求 Redis
                    if check_len >= b_len_threshold:
                        # 执行 Redis 比对 (保持原有 adapter 调用)
                        decision = adapter.get_state_decision(state_hash)
                        
                        if decision:
                            # --- 原有逻辑保留：设置当前决策方向 ---
                            is_ai_match = True
                            raw_val = str(decision.get('action', '')).upper()
                            if "CU" in raw_val or raw_val == "C": current_action = "C"
                            elif "CO" in raw_val or raw_val == "S": current_action = "S"
                            else: current_action = "?"
                            
                            # --- 【新增需求 2】：共享比对结果给 UI ---
                            shared_payload["decision"] = decision
                            shared_payload["status"] = "MATCHED"
                        else:
                            is_ai_match = False
                            shared_payload["status"] = f"NO MATCH ({check_len})"
                            print(f"[BACKEND-2] ⚪ NO MATCH at length {check_len}")
                    else:
                        # 长度不达标，完全不触发比对 (原有逻辑)
                        is_ai_match = False
                        shared_payload["status"] = f"WAITING ({check_len}/{b_len_threshold})"
                        # print(f"[BACKEND-2] Blocked: {check_len} < {b_len_threshold}")

                    # --- 【核心共享点】：存入 session_state 供 UI 侧边栏读取 ---
                    st.session_state['shared_ai_data'] = shared_payload

                # --- 6. 判定渲染标记强度 ---
                marked_len_for_ui = 0
                if res in ['B', 'P']:
                    if betting_moment_len > 0 and res == pre_deal_seq[-1]:
                        marked_len_for_ui = betting_moment_len + 1
                    else:
                        marked_len_for_ui = 1
                # --- 7. 写入 Redis 存证 (保留映射并同步余额) ---
                record_writer = st.session_state.get('record_adapter')
                if record_writer and actual_bet_made > 0:
                    try:
                        target_uid = st.session_state.get('auth_user', "J")
                        target_uname = st.session_state.get('username', f"User_{target_uid}")
                        
                        # ✅ 保留映射逻辑：将 C/S 转换为易读的单词
                        act_map = {"C": "CUT", "S": "CONTINUE"}
                        act = act_map.get(current_action, "MANUAL")
                        
                        # 执行写入，并获取 Redis 实时计算出的 new_balance
                        db_updated_balance = record_writer.record_app_transaction(
                            user_id=target_uid,             
                            username=target_uname,      
                            amount=net_profit,       
                            tx_type="AUTORUN" if st.session_state.auto_run_active else "DEAL",
                            strategy=st.session_state.get('strategy_mode', "V8_AUTO"), 
                            hist_len=h_min, 
                            bet_len=betting_moment_len, 
                            action=act  # 使用转换后的单词
                        )

                        # ✅ 同步：让 UI 余额等于数据库返回的真实数字
                        if db_updated_balance is not None:
                            st.session_state.balance = db_updated_balance
                            
                    except Exception as e:
                        print(f"❌ Redis Sync Error: {e}")



                # --- 8. 更新路单渲染池 ---
                st.session_state.rank_counts, st.session_state.stats = update_shoe_stats(oc, st.session_state.rank_counts, st.session_state.stats)
                st.session_state.results.append(res)
                
                bet_res = "win" if net_profit > 0 else "loss" if actual_bet_made > 0 and res != 'T' else None
                
                st.session_state.styled_results.append({
                    "v": res,
                    "m": is_ai_match, 
                    "r": marked_len_for_ui if res != 'T' else bet_res,
                    "action": current_action
                })

                # --- 9. 物理序列入库 & 策略重置判定 ---
                if res in ['B', 'P']: 
                    st.session_state.clean_results.append(res)
                    
                    # 检查是否变路 (用于 S1 策略重置)
                    current_clean_seq = st.session_state.clean_results
                    if len(current_clean_seq) >= 2:
                        if current_clean_seq[-1] != current_clean_seq[-2]:
                            st.session_state.streak_counter = 0
                            st.session_state.active_streak_side = None
                            st.session_state.streak_bet_locked = False
                            print("[S1 STRATEGY] 🔄 Road Changed - S1 Reset")

                # 满 3 注拦截逻辑（规则 5）
                if st.session_state.streak_counter >= 3:
                    # 3 注任务已完成，等待下次变路重置
                    pass

                if actual_bet_made > 0:
                    st.session_state.bet_history.append({"hand_no": len(st.session_state.results), "winner": oc.winner, "net": net_profit})
                
                # 下注输入框归零
                st.session_state.bet_input_red = 0
                st.session_state.bet_input_blue = 0

            except IndexError:
                st.session_state.end_shoe = True
    

    with st.sidebar:
        # --- 侧边栏：AI 策略配置 (多语言适配版) ---
        st.divider()
        is_cn = st.session_state.get('lang', 'EN') == "CN"

        # 文本定义
        ui_title = "⚙️ AI 策略配置" if is_cn else "⚙️ AI STRATEGY CONFIG"
        ui_help = "配置 AI 扫描深度、下注长度门槛及频率策略" if is_cn else "Configure AI depth, length threshold, and strategy."
        label_hmin = "扫描深度" if is_cn else "Scanning Depth"
        label_blen = "下注门槛" if is_cn else "Betting Threshold"
        label_strat = "下注策略" if is_cn else "Betting Strategy"
        strat_options = ["单注", "连注"] if is_cn else ["Single", "Continuous"]

        st.markdown(f"**{ui_title}**", help=ui_help)

        # A. 扫描深度
        st.session_state.hist_min_slider = st.sidebar.slider(
            label=label_hmin, min_value=1, max_value=12, 
            value=st.session_state.get('hist_min_slider', 4), key="h_min_slider"
        )

        # B. 长度门槛 (bet_len)
        st.session_state.bet_len_slider_input = st.sidebar.slider(
            label=label_blen, min_value=1, max_value=10, 
            value=st.session_state.get('bet_len_slider_input', 4)
        )


        # --- 侧边栏：S1 策略矩阵配置 ---
        is_cn = st.session_state.get('lang', 'CN') == "CN"

        # 1. 定义多语言文案
        label_s1_strat = "投注策略矩阵" if is_cn else "Betting Strategy Matrix"
        help_s1 = "选择连续 3 注的注码分配方案 (S1 规范)" if is_cn else "Select betting distribution for 3 consecutive bets (S1 Standard)."

        # 2. 策略选项定义
        strat_options = ["100", "110", "111", "121", "137", "AUTO"]

        # 3. 渲染下拉选择框
        selected_strat = st.sidebar.selectbox(
            label=label_s1_strat,
            options=strat_options,
            index=0,  # 默认指向 "100"
            help=help_s1
        )

        # 4. 状态同步
        # current_strategy_key 用于逻辑计算提取 STRATEGY_LIB 的值
        st.session_state.current_strategy_key = selected_strat 

        # strategy_mode 用于 UI 显示或 Redis 存证
        st.session_state.strategy_mode = f"S1-{selected_strat}"

        
# --- 5.A 顶部：下注区分割线 (保持不变) ---
        divider_text = "BETTING ZONE" if st.session_state.lang == "EN" else "下注区"
        st.markdown(f"""
            <div style="display: flex; align-items: center; margin: 10px 0px 15px 0px;">
                <div style="flex-grow: 1; height: 1px; background: #444;"></div>
                <span style="padding: 0 10px; color: #888; font-size: 0.75rem; font-weight: bold; letter-spacing: 1px;">{divider_text}</span>
                <div style="flex-grow: 1; height: 1px; background: #444;"></div>
            </div>
        """, unsafe_allow_html=True)

        # --- 5.B 实时下注数额显示面板 (保持不变) ---
        current_b = st.session_state.get('bet_input_red', 0)
        current_p = st.session_state.get('bet_input_blue', 0)

        side_label_b = "🔴 BANKER" if st.session_state.lang == "EN" else "🔴 庄"
        side_label_p = "🔵 PLAYER" if st.session_state.lang == "EN" else "🔵 闲"

        st.markdown(f"""
            <div style="background: rgba(255,255,255,0.05); padding: 10px; border-radius: 8px; border: 1px solid #444; margin-bottom: 15px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 5px;">
                    <span style="font-size: 0.7rem; color: #888;">{side_label_b}</span>
                    <span style="font-size: 1.1rem; font-weight: bold; color: #FF4500;">${current_b:,.0f}</span>
                </div>
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <span style="font-size: 0.7rem; color: #888;">{side_label_p}</span>
                    <span style="font-size: 1.1rem; font-weight: bold; color: #1E90FF;">${current_p:,.0f}</span>
                </div>
            </div>
        """, unsafe_allow_html=True)


        # --- 🛠️ 关键修改点：移除 key 绑定，改用变量赋值 ---
        # 只有这样做，handle_deal_click 里的 st.session_state.bet_input_red = 0 才能生效而不报错
        # --- 🛠️ 必须这样写：去掉 key 参数，改用变量接收返回值 ---

        st.session_state.bet_input_red = st.number_input(
            "B", # 这个 Label 必须保留，供下方 CSS 选择器识别
            value=float(st.session_state.get('bet_input_red', 0)),
            step=100.0,
            format="%.0f",
            key=None # 显式设为 None 或直接不写 key 参数
        )

        st.session_state.bet_input_blue = st.number_input(
            "P", 
            value=float(st.session_state.get('bet_input_blue', 0)),
            step=100.0,
            format="%.0f",
            key=None # 显式设为 None 或直接不写 key 参数
        )
        # --- 5.C 核心样式注入 (CSS 逻辑保持不变) ---
        st.markdown("""
        <style>
            /* 1. 彻底隐藏所有 number_input 的标签 (B/P) */
            section[data-testid="stSidebar"] div[data-testid="stNumberInput"] label {
                display: none !important;
                height: 0px !important;
                visibility: hidden !important;
            }

            /* 2. 庄 (B) 输入框强力染色 */
            section[data-testid="stSidebar"] div.stNumberInput:has(input[aria-label="B"]) div[data-testid="stNumberInput-InputContextContainer"] {
                background-color: rgba(255, 69, 0, 0.25) !important;
                border: 1px solid rgba(255, 69, 0, 0.5) !important;
                border-radius: 4px !important;
            }
            section[data-testid="stSidebar"] div.stNumberInput:has(input[aria-label="B"]) input {
                color: #FF4500 !important;
                font-weight: bold !important;
            }

            /* 3. 闲 (P) 输入框强力染色 */
            section[data-testid="stSidebar"] div.stNumberInput:has(input[aria-label="P"]) div[data-testid="stNumberInput-InputContextContainer"] {
                background-color: rgba(30, 144, 255, 0.25) !important;
                border: 1px solid rgba(30, 144, 255, 0.5) !important;
                border-radius: 4px !important;
            }
            section[data-testid="stSidebar"] div.stNumberInput:has(input[aria-label="P"]) input {
                color: #1E90FF !important;
                font-weight: bold !important;
            }

            /* 4. 解决部分版本白色底色残留问题 */
            section[data-testid="stSidebar"] input {
                background-color: transparent !important;
            }
        </style>
        """, unsafe_allow_html=True)
        # --- 5.D 物理输入框区 ---
        #sb2, sb1 = st.columns(2)
        # 这里的 "B" 和 "P" 是 CSS 识别的关键钥匙
        #bet_b = sb1.number_input("B", min_value=0, step=100, key="bet_input_red")
        #bet_p = sb2.number_input("P", min_value=0, step=100, key="bet_input_blue")

        # --- 5.E 剩余牌数与投注记录 ---
        remaining = len(st.session_state.shoe)
        if remaining <= st.session_state.cut_card_at:
            st.session_state.end_shoe = True
        
        st.caption(f"Remaining: {remaining} (Cut: {st.session_state.cut_card_at})")

        if st.session_state.end_shoe:
            st.warning("🟥 切牌线已到" if st.session_state.lang == "CN" else "🟥 CUT CARD REACHED")
        # ... 在 sidebar 或主面板的合适位置 ...
        st.markdown("---")
        
        # 按钮布局

        is_cn = (lang == "CN")
        c_btn1, c_btn2 = st.columns(2)
            
        with c_btn1:
            if st.button("📊 " + ("最近下注" if is_cn else "Recent"),width="stretch"):
                show_recent_bets_dialog()
                
        with c_btn2:
            if st.button("📈 " + ("综合报表" if is_cn else "Reports"),width="stretch"):
                show_summary_report_dialog()

    # --- 6. 主界面渲染 ---
    # 获取当前语言字典 (与 i18n.py 键值对齐)
    lt = TRANSLATIONS.get(st.session_state.lang, {})
    # 第一步：渲染牌桌（发牌图片）
    render_casino_table(st.session_state.get('last_outcome_obj'), lang=st.session_state.lang)
    # --- 2. 核心：并排按钮区 (视觉焦点 2) ---
    st.markdown("<br>", unsafe_allow_html=True)
    
    
        # --- 6.2 按钮区渲染 ---
    # --- 按钮区渲染 ---
    _, btn_container, _ = st.columns([0.1, 3.8, 0.1])
    with btn_container:
        c1, c_auto, c2, c3 = st.columns(4)
        is_cn = st.session_state.lang == "CN"
        
        with c1:
            st.button(lt.get("btn_deal"), width="stretch", type="primary", 
                      disabled=st.session_state.end_shoe, on_click=handle_deal_click)
        
        with c_auto:
            is_active = st.session_state.get('auto_run_active', False)
            is_cn = (lang == "CN")
            # 重新定义，确保按钮可用
            a_label = "🤖 自动运行" if is_cn else "🤖 AUTORUN"
            s_label = "🛑 停止运行" if is_cn else "🛑 STOP"
            
            if st.button(s_label if is_active else a_label, 
                         width="stretch", 
                         type="primary" if is_active else "secondary", 
                         key="auto_btn"):
                st.session_state.auto_run_active = not is_active
                if st.session_state.auto_run_active:
                    run_auto_engine() # 点击瞬间立即触发第一手
                st.rerun()

        with c2:
            if st.button(lt.get("btn_new_shoe"), width="stretch"):
                reset_logic()
                # --- 3 FREE HANDS ---
                handle_deal_click()
                handle_deal_click()
                handle_deal_click()
                
                st.rerun()

        with c3:
            label_marker = "🎯 标记模式" if is_cn else "🎯 MARKER"
            label_natural = "🍃 自然模式" if is_cn else "🍃 NATURAL"
            curr_mode = label_marker if st.session_state.marker_mode else label_natural
            if st.button(curr_mode, width="stretch"):
                st.session_state.marker_mode = not st.session_state.marker_mode
                st.rerun()


    # --- 3. 大路演示图 (视觉焦点 3 - CSS 物理擦除标签) ---
    st.markdown("""
        <style>
        /* 强制隐藏渲染函数中可能带有的 subheader (h3) */
        [data-testid="stVerticalBlock"] > div:nth-child(n) h3 {
            display: none !important;
        }
        /* 极致缩减路图与按钮之间的间距 */
        hr { margin-top: 0.2rem !important; margin-bottom: 0.5rem !important; }
        .stPlotlyChart { margin-top: -10px !important; }
        </style>
    """, unsafe_allow_html=True)
    
# --- 2.5 实时统计：[B | T | P] 终极防漏 + 多语言版 ---
    stats = st.session_state.get('stats', {"B": 0, "P": 0, "T": 0})
    total_hands = sum(stats.values())
    
    # 定义清洗函数：核心是去掉字符串中连续的空格，防止触发 Markdown 代码块识别
    def clean_translate(text):
        import re
        # 将多个空格替换为一个空格，并移除换行
        return re.sub(r'\s+', ' ', text).strip()

    # 获取并清洗翻译
    txt_b = clean_translate(lt.get('stat_b', 'BANKER'))
    txt_t = clean_translate(lt.get('stat_t', 'TIE'))
    txt_p = clean_translate(lt.get('stat_p', 'PLAYER'))

    def get_pct(val):
        if total_hands == 0: return "0%"
        return f"{(val/total_hands)*100:.1f}%"

    # 构造 HTML：严格物理顺序 B | T | P
    # 注意：div 标签必须紧贴左侧，不要有任何前置空格或 Tab
    stats_html = f"""
        <div style="display: flex; justify-content: space-around; background: rgba(255,255,255,0.03); padding: 12px; border-radius: 12px; margin: 10px 0; border: 1px solid #444; align-items: center;">
        <div style="text-align: center; flex: 1;">
        <div style="font-size: 0.75rem; color: #BBB; margin-bottom: 5px;">{txt_b}</div>
        <div style="display: flex; align-items: baseline; justify-content: center; gap: 6px;">
        <span style="font-size: 1.4rem; font-weight: bold; color: #FF4500;">{stats['B']}</span>
        <span style="font-size: 0.9rem; color: #FF4500CC;">({get_pct(stats['B'])})</span>
        </div>
        </div>
        <div style="text-align: center; flex: 1; border-left: 1px solid #444; border-right: 1px solid #444; padding: 0 5px;">
        <div style="font-size: 0.75rem; color: #BBB; margin-bottom: 5px;">{txt_t}</div>
        <div style="display: flex; align-items: baseline; justify-content: center; gap: 6px;">
        <span style="font-size: 1.4rem; font-weight: bold; color: #00FFAA;">{stats['T']}</span>
        <span style="font-size: 0.9rem; color: #00FFAACC;">({get_pct(stats['T'])})</span>
        </div>
        </div>
        <div style="text-align: center; flex: 1;">
        <div style="font-size: 0.75rem; color: #BBB; margin-bottom: 5px;">{txt_p}</div>
        <div style="display: flex; align-items: baseline; justify-content: center; gap: 6px;">
        <span style="font-size: 1.4rem; font-weight: bold; color: #1E90FF;">{stats['P']}</span>
        <span style="font-size: 0.9rem; color: #1E90FFCC;">({get_pct(stats['P'])})</span>
        </div>
        </div>
        </div>
        """
    # 🚨 这里的关键：直接渲染，不留任何被识别为代码块的机会
    st.markdown(stats_html.strip(), unsafe_allow_html=True)




    # 第二步：紧贴渲染 Big Road (路单)
    st.subheader(t("big_road"))
    # [修改点]：根据模式选择渲染数据集和模式
    # 核心：使用 if-else 二选一，确保只调用一次函数
    if st.session_state.get('marker_mode', False):
            # 标注模式：传入带元数据的字典列表
        render_big_road(st.session_state.styled_results, mode="MARKER")
    else:
            # 自然模式：传入原始字符串列表
        render_big_road(st.session_state.results, mode="NATURAL")        

    st.divider()



    
    # --- 7. 双核诊断面板 (完全修复显示问题版) ---
        # ==========================================
    # 1. 物理连接单点锁定 (全局唯一初始化)
    # ==========================================
    use_cloud = st.secrets.get("USE_CLOUD_REDIS", False)
    current_mode_str = "CLOUD" if use_cloud else "LOCAL"

    # 核心同步逻辑：检测到模式切换（本地转云端或反之），立即销毁旧实例
    if 'last_redis_mode' in st.session_state and st.session_state.last_redis_mode != current_mode_str:
        st.session_state.pop('redis_adapter', None)
        print(f"🔄 [GLOBAL] 模式强制同步: {st.session_state.last_redis_mode} -> {current_mode_str}")

    # 执行单点初始化
    if 'redis_adapter' not in st.session_state:
        try:
            target_url = st.secrets["UPSTASH_REDIS_URL"] if use_cloud else st.secrets["LOCAL_REDIS_URL"]
            st.session_state.redis_adapter = RedisAdapter(target_url)
            st.session_state.last_redis_mode = current_mode_str
            # 仅在第一次或重连时打印，减少日志干扰
            print(f"📡 [CONN] 已锁定物理连接: {current_mode_str}")
        except Exception as e:
            st.error(f"❌ Redis 物理连接建立失败: {e}")


    
    
    unified_blue = "#1E90FF"
    
    # 强制单行样式定义，避免换行符干扰 Markdown 渲染
    c_style = "background-color:#0a141e;border:1px solid #444;border-radius:10px;padding:20px;min-height:320px;display:flex;flex-direction:column;width:100%;box-sizing:border-box;color:#ffffff;"
    
    col_left, col_right = st.columns(2)
    
    with col_left:
        # 1. 语言与标签初始化
        is_cn = st.session_state.get('lang', 'CN') == "CN"
        label_theoretical = "权重分布模型" if is_cn else "RANK DISTRIBUTION MODEL"
        label_historical = "熵值指纹模型" if is_cn else "ENTROPY FINGERPRINT MODEL"
        label_init = "【初始状态】已就绪" if is_cn else "[INITIAL STATE] Ready"
        label_miss = "牌组序列呈现随机游走，无显著 EV 信号。"
        label_miss_en = "Card sequence shows a random walk; no significant EV signal detected."
        display_title = "🎯 双核引擎算牌追踪" if is_cn else "🎯 DUAL-CORE RANK-BIAS TRACKING"
        
        # 2. Redis 连接检查 (已在 main.py 统一定义，此处仅引用)
        use_cloud = st.secrets.get("USE_CLOUD_REDIS", False)
        adapter = st.session_state.get('redis_adapter')

        # 3. 生成 18 位指纹 ID
        counts = st.session_state.get('rank_counts', {i: 32 for i in range(1, 10)})
        out_rk_list = [f"{(32 - counts.get(i, 32)):02d}" for i in range(1, 10)]
        current_rk = "".join(out_rk_list).zfill(18)
        is_initial = (current_rk == "000000000000000000")

        # 4. 执行深度查询 (使用新增所在的 get_entropy_decision)
        # 计算理论 SBI
        sbi = compute_sbi_ev_from_counts(8, counts)
        
        # 获取历史 Entropy 数据
        decision = None
        if adapter:
            # 直接调用你新增的专用函数
            decision = adapter.get_entropy_decision(current_rk)
            


        # 5. 状态与颜色渲染逻辑
        if decision:
            #st.balloons()
            # 从新函数返回的对象中提取字段
            ev_p_txt = f"{decision['ev_cont']*100:+.2f}%"
            ev_b_txt = f"{decision['ev_cut']*100:+.2f}%"
            act_name = {"B": "B", "P": "P"}.get(decision['action'], decision['action'])
            status = f"{'方向' if is_cn else 'SIDE'}: {act_name} | {'评级' if is_cn else 'Rate'}: {decision['tier']}"
            status_color = "#00FFAA"
        else:
            ev_p_txt, ev_b_txt = "n/a", "n/a"
            status = label_init if is_initial else (label_miss if is_cn else label_miss_en)
            status_color = "#FFAA00" if is_initial else "#A0A4B8"

        # 6. 构造 HTML (UI 保持一致)
        h = f'<div style="{c_style}">'
        h += f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:15px;border-bottom:1px solid #333;padding-bottom:10px;"><span style="color:{unified_blue};font-weight:bold;font-size:1rem;">{display_title}</span><span style="font-size:0.6rem;color:#ffffff;background:rgba(30,144,255,0.3);padding:2px 6px;border-radius:4px;">PRO-{"ONLINE" if use_cloud else "LOCAL"}</span></div>'

        # 🟢 核心修改点：调整 size、color 及 padding 以完全对齐 col_right
        display_rk = "READY" if is_initial else current_rk
        h += f'<div style="font-size:0.65rem;color:#FFFFFF;margin-bottom:15px;font-family:monospace;background:rgba(0,0,0,0.4);padding:5px 10px;border-radius:5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">🫆{display_rk}</div>'

        h += f'<div style="display:flex;flex-direction:column;gap:18px;">'
        h += f'<div style="border-left:4px solid {unified_blue};padding-left:12px;"><div style="font-size:0.7rem;color:{unified_blue};font-weight:bold;">{label_theoretical}</div><div style="font-size:1.3rem;margin-top:4px;color:#ffffff;font-family:monospace;font-weight:bold;">P: {sbi["ev_p"]*100:+.2f}% | B: {sbi["ev_b_comm"]*100:+.2f}%</div></div>'
        h += f'<div style="border-left:4px solid {unified_blue};padding-left:12px;"><div style="font-size:0.7rem;color:{unified_blue};font-weight:bold;">{label_historical}</div><div style="font-size:1.3rem;margin-top:4px;color:#ffffff;font-family:monospace;font-weight:bold;">P: {ev_p_txt} | B: {ev_b_txt}</div><div style="font-size:0.7rem;color:{status_color};margin-top:4px;line-height:1.2;">{status}</div></div>'
        h += '</div></div>'

        st.markdown(h, unsafe_allow_html=True)

    with col_right:
        # 1. 基础配置与语言映射
        if 'ai_zone_placeholder' not in st.session_state:
            st.session_state.ai_zone_placeholder = st.empty()
            
        is_cn = st.session_state.get('lang', 'CN') == 'CN'
        lang_map = {
            # 🟢 锁定方案：格阵指纹 (Grid-ID)
            "title": "🔍 AI 点阵指纹扫描" if is_cn else "🔍 AI PATTERN RECOGNITION",
            "waiting": "Waiting for data..." if not is_cn else "等待数据中...",
            "action_label": "Best Action" if not is_cn else "最优决策",
            "edge_label": "Edge Advantage" if not is_cn else "优势概率",
            "insufficient": "DEPTH INSUFFICIENT..." if not is_cn else "序列深度不足...",
            # 🟢 锁定方案：迷雾区提示
            "miss": "走势进入“迷雾区”，AI建议规避风险。" if is_cn else "Pattern entered the 'Fog Zone'. AI suggests risk avoidance.",
        }

        # 2. 状态逻辑初始化 (必须在 HTML 拼接前完成)
        clean_seq = st.session_state.get('clean_results', [])
        h_min = st.session_state.get('hist_min', 3) 
        fp_advice = {"match": False, "status": "WAITING", "fp_id": ""}
        
        # 获取由 col_left 已经统一初始化好的连接
        adapter = st.session_state.get('redis_adapter')

        if clean_seq:
            # 🚀 A. 一站式整理 5 要素
            components = get_fp_components(clean_seq, h_min=h_min)
            c_side, c_len, hB_f, hP_f, _ = components 

            # 🚀 B. 约束检查：只有历史区存在数据才计算
            if not hB_f and not hP_f:
                fp_advice.update({"status": lang_map["insufficient"], "fp_id": "Insufficient data..."})
            else:
                # 🚀 C. 物理对齐生成 Hash
                state_hash = generate_fp_hash(*components)
                
                # 🚀 D. 执行查询
                if adapter:
                    # 使用针对 Hash 结构的专用查询函数
                    decision = adapter.get_state_decision(state_hash)
                    if decision:
                        fp_advice.update({
                            "match": True,
                            "action": decision["action"],
                            "edge": decision["edge"],
                            "ev_cut": decision["ev_cut"],
                            "ev_cont": decision["ev_cont"],
                            "fp_id": state_hash
                        })
                        # 触发特效
                        if st.session_state.get("last_balloon_hash") != state_hash:
                            #st.balloons()
                            if decision["edge"] > 0.01: st.snow()
                            st.session_state.last_balloon_hash = state_hash
                    else:
                        fp_advice.update({"status": lang_map["miss"], "fp_id": state_hash})

        # 3. 最终 UI 渲染 (严格像素对齐)
        with st.session_state.ai_zone_placeholder.container():
            html = f'<div style="{container_style}">'
            html += f'<div style="{header_style}"><span>{lang_map["title"]}</span><span style="font-size:0.6rem;color:#FFFFFF;background:rgba(0,0,0,0.2);padding:2px 6px;border-radius:4px;">AI ONLINE</span></div>'
            
            # --- 🚀 调整位置：将指纹 ID 行提到所有状态逻辑之前，实现与 col_left 物理对齐 ---
            fid_display = fp_advice.get("fp_id", "") if fp_advice.get("fp_id") else "READY"
            html += f'<div style="font-family:monospace;font-size:0.65rem;color:#FFFFFF;background:rgba(0,0,0,0.3);padding:5px 10px;border-radius:4px;margin-bottom:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">🫆{fid_display}</div>'

            if not fp_advice.get('match') and fp_advice.get('status') == 'WAITING':
                html += f'<div style="color:#666;text-align:center;padding-top:80px;">{lang_map["waiting"]}</div>'
            
            elif fp_advice.get('match'):
                act = fp_advice["action"]
                edge_pct = f'{fp_advice["edge"]:+.2%}'
                e_cut_pct, e_cont_pct = f'{fp_advice["ev_cut"]*100:+.2f}%', f'{fp_advice["ev_cont"]*100:+.2f}%'

                html += f'''
                    <div>
                        <div style="text-align:center;margin-bottom:15px;">
                            <div style="font-size:0.7rem;color:#888;text-transform:uppercase;">{lang_map["action_label"]}</div>
                            <div style="font-size:2.2rem;font-weight:800;color:#00FFAA;text-shadow:0 0 10px rgba(0,255,170,0.4);">{act}</div>
                        </div>
                        <div style="display:flex;gap:10px;margin-bottom:12px;">
                            <div style="flex:1;background:rgba(255,255,255,0.05);padding:8px;border-radius:8px;text-align:center;border:1px solid #444;">
                                <div style="font-size:0.6rem;color:#aaa;">EV (CUT)</div>
                                <div style="font-size:1.0rem;font-weight:bold;color:#fff;">{e_cut_pct}</div>
                            </div>
                            <div style="flex:1;background:rgba(255,255,255,0.05);padding:8px;border-radius:8px;text-align:center;border:1px solid #444;">
                                <div style="font-size:0.6rem;color:#aaa;">EV (CONT)</div>
                                <div style="font-size:1.0rem;font-weight:bold;color:#fff;">{e_cont_pct}</div>
                            </div>
                        </div>
                        <div style="text-align:center;background:rgba(0,255,170,0.1);padding:5px;border-radius:20px;border:1px solid #00FFAA33;">
                            <span style="font-size:0.8rem;color:#00FFAA;font-weight:bold;">{lang_map["edge_label"]}: {edge_pct}</span>
                        </div>
                    </div>
                '''
            else:
                # 此时 ID 已在上方显示，下方仅保留文案
                html += f'''
                    <div style="margin-top:40px;text-align:center;">
                        <div style="color:#FF4444;font-size:0.9rem;margin-bottom:8px;font-weight:bold;">⚠️ {fp_advice["status"]}</div>
                    </div>
                '''

            html += '</div>'
            st.markdown(html, unsafe_allow_html=True)
     # --- 底部循环点火器 (解决靴末停滞) ---
    if st.session_state.get('auto_run_active', False):
        # 只要下注框已清零（表示上一手处理完），就自动执行下一手
        if st.session_state.bet_input_red == 0 and st.session_state.bet_input_blue == 0:
            time.sleep(0.1) # 增加微小延迟防止 UI 渲染过载
            run_auto_engine()
            st.rerun()

