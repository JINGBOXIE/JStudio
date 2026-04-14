#目前运行的V1版，AUTORUN功能可以自动运行，自动下注功能将在V3实现

import streamlit as st
import os
import sys
import pandas as pd
import random
import redis
import time  # <--- 添加这一行
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

def render_practice_tab(lang):
    # --- 1. 必须放在函数的第一行，确保任何地方引用它都不会报错 ---
    # 1. 状态初始化
    if 'bet_input_red' not in st.session_state:
        st.session_state.bet_input_red = 0
    if 'bet_input_blue' not in st.session_state:
        st.session_state.bet_input_blue = 0
    if 'auto_run_active' not in st.session_state:
        st.session_state.auto_run_active = False
    if 'marker_mode' not in st.session_state:
        st.session_state.marker_mode = False
    
    if 'styled_results' not in st.session_state:
        st.session_state.styled_results = []


    # --- 1. 样式扁平化处理 (杜绝 Markdown 干扰) ---
    # 显式使用深色背景 (#0a141e) 和 纯白文字 (#FFFFFF)
    container_style = "padding:18px;border:2px solid #1E90FF;border-radius:15px;background-color:#0a141e;box-shadow:0 4px 15px rgba(0,0,0,0.5);min-height:320px;color:#FFFFFF;display:flex;flex-direction:column;box-sizing:border-box;"
    
    header_style = "font-weight:bold;color:#1E90FF;font-size:1.1rem;letter-spacing:1px;margin-bottom:12px;border-bottom:1px solid #1E90FF44;padding-bottom:8px;display:flex;justify-content:space-between;align-items:center;"

    # tabs/tab_practice.py 内部初始化部分
    if 'clean_results' not in st.session_state:
        st.session_state.clean_results = []  # 专门存放剔除 T 后的序列
    # 抽取翻译工具函数（适配当前 session_state.lang）
    def t(key): return TRANSLATIONS.get(st.session_state.lang, {}).get(key, key)

    # --- 3. CSS 样式 (保持原样) ---
    
    st.markdown("""
    <style>
        [data-testid="stSidebarContent"] { padding-top: 1rem !important; }
        [data-testid="stVerticalBlock"] > div { gap: 0.5rem !important; }
        
        /* ✅ 删除或注释掉下面这一行 */
        /* [data-testid="stNumberInput"] label { height: 0px; overflow: hidden; display: none; } */
        
        hr { margin-top: 0.8rem !important; margin-bottom: 0.8rem !important; }
    </style>
""", unsafe_allow_html=True)

    def reset_logic():
        import random
        
        # 1. 牌靴物理重置
        if 'factory' not in st.session_state:
            from dealer.baccarat_dealer import ShoeFactory
            st.session_state.factory = ShoeFactory()
        
        st.session_state.shoe = st.session_state.factory.create_shoe()
        st.session_state.cut_card_at = random.randint(14, 20)
        st.session_state.end_shoe = False
        
        # 2. 数据清空 (核心逻辑)
        st.session_state.results = []           # 原始路单
        st.session_state.clean_results = []     # 去和路单
        st.session_state.styled_results = []    # 标记模式路单 [新]
        st.session_state.bet_history = []       # 投注记录
        
        # 3. 统计指标重置
        st.session_state.stats = {"B": 0, "P": 0, "T": 0}
        st.session_state.rank_counts = {i: (128 if i == 0 else 32) for i in range(10)}
        st.session_state.last_outcome_obj = None
        
        # 4. AI 状态重置
        st.session_state.last_fp_advice = {
            "match": False, 
            "fp_id": "READY", 
            "action": "WAIT", 
            "edge": 0.0, 
            "ev_info": {}
        }
    if 'bac_pro_v8_final' not in st.session_state:
        st.session_state.dealer = BaccaratDealer()
        st.session_state.factory = ShoeFactory(decks=8)
        st.session_state.balance = 10000.0
        reset_logic()
        st.session_state.bac_pro_v8_final = True

    def handle_deal_click(is_auto=False):
        """
        终极锁定版：物理隔离 Redis 延迟 + 自动运行引擎控制。
        """
        # --- [前置检查] 若已触红卡，立即停止一切动作 ---
        if st.session_state.get('end_shoe', False):
            st.session_state.auto_run_active = False
            return

        # 1. 确保基础列表存在
        if 'styled_results' not in st.session_state: st.session_state.styled_results = []
        if 'clean_results' not in st.session_state: st.session_state.clean_results = []

        # 2. 赌注计算
        bet_b = st.session_state.get("bet_input_red", 0)
        bet_p = st.session_state.get("bet_input_blue", 0)
        current_bets = {"B": int(bet_b), "P": int(bet_p), "T": 0}
        total_bet = sum(current_bets.values())

        if total_bet <= st.session_state.balance:
            try:
                # --- 🛡️ 核心锁定：发牌前快照 ---
                raw_road_snapshot = list(st.session_state.clean_results)
                
                is_ai_match = False
                current_action = None  
                adapter = st.session_state.get('redis_adapter')
                h_min = st.session_state.get('hist_min', 3)
                
                if adapter and raw_road_snapshot:
                    components = get_fp_components(raw_road_snapshot, h_min=h_min)
                    state_hash = generate_fp_hash(*components)
                    decision = adapter.get_state_decision(state_hash)
                    if decision:
                        is_ai_match = True
                        raw_val = str(decision.get('action', '')).upper()
                        if "CU" in raw_val or raw_val == "C":
                            current_action = "C"
                        elif "CO" in raw_val or raw_val == "S":
                            current_action = "S"
                        else:
                            current_action = "?"

                # --- 🚀 执行发牌 ---
                oc = st.session_state.dealer.deal_one_hand(st.session_state.shoe)
                st.session_state.last_outcome_obj = oc

                # --- 💰 结算 ---
                new_bal, net_profit, _ = settle_hand(oc.winner, current_bets, st.session_state.balance)
                st.session_state.balance = new_bal
                st.session_state.rank_counts, st.session_state.stats = update_shoe_stats(
                    oc, st.session_state.rank_counts, st.session_state.stats
                )

                # --- 🏷️ 绑定转换后的 S/C 存入路单 ---
                bet_res = None
                if total_bet > 0 and oc.winner != 'T':
                    bet_res = "win" if net_profit > 0 else "loss"
                
                st.session_state.results.append(oc.winner)
                st.session_state.styled_results.append({
                    "v": oc.winner,      
                    "m": is_ai_match,    
                    "r": bet_res,        
                    "action": current_action  
                })

                if oc.winner in ['B', 'P']:
                    st.session_state.clean_results.append(oc.winner)

                if total_bet > 0:
                    st.session_state.bet_history.append({
                        "hand_no": len(st.session_state.results),
                        "winner": oc.winner,
                        "net": net_profit
                    })
                st.session_state.bet_input_red = 0
                st.session_state.bet_input_blue = 0

            except IndexError:
                st.session_state.end_shoe = True
                st.session_state.auto_run_active = False 
        else:
            # 🛑 余额不足时的安全退出
            st.session_state.auto_run_active = False
            st.toast("余额不足，自动运行已停止", icon="⚠️")

        # --- 最终刷新判定 (handle_deal_click 函数末尾) ---
        if not is_auto:
            # 只有当非回调触发（例如你直接在主流程调用）才需要 rerun
            # 但因为你是通过 on_click=handle_deal_click 调用的，执行完会自动刷新
            # 所以这里直接 return 即可，不要写 st.rerun()
            return
            
    with st.sidebar:
        # --- 补回 hist_min 调节功能（中英文适配版 - 极简布局） ---
        st.divider()

        # 1. 定义多语言文本
        is_cn = st.session_state.get('lang', 'EN') == "CN"
        ui_title = "⚙️  AI指纹 深度配置▒" if is_cn else "⚙️  AI FINGERPRINT CONFIG▒"
        ui_help = "调节该值会改变AI🫆截取的历史数据范围" if is_cn else "Adjusts the historical data range for AI🫆 generation."
        # 2. 标题与帮助提示并排显示
        st.markdown(f"**{ui_title}**", help=ui_help)

        # 3. 绑定滑块 (label 设为空字符串以取消显示)
        st.session_state.hist_min = st.sidebar.slider(
            label="", 
            min_value=1, 
            max_value=12, 
            value=st.session_state.get('hist_min', 3),
            key="hist_min_slider"
        )

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
        sb2, sb1 = st.columns(2)
        # 这里的 "B" 和 "P" 是 CSS 识别的关键钥匙
        #bet_b = sb1.number_input("B", min_value=0, step=100, key="bet_input_red")
        #bet_p = sb2.number_input("P", min_value=0, step=100, key="bet_input_blue")

        # --- 5.E 剩余牌数与投注记录 ---
        remaining = len(st.session_state.shoe)
        if remaining <= st.session_state.cut_card_at:
            st.session_state.end_shoe = True
        
        st.caption(f"Remaining: {remaining} (Cut: {st.session_state.cut_card_at})")

        exp_title = "💰 Betting History" if st.session_state.lang == "EN" else "💰 投注记录"
        with st.expander(exp_title, expanded=True):
            st.metric("Balance (USD)", f"${st.session_state.balance:,.2f}")
            if st.session_state.get('bet_history'):
                history_html = ""
                for rec in reversed(st.session_state.bet_history):
                    net_color = "#00FFAA" if rec['net'] > 0 else "#FF4444" if rec['net'] < 0 else "#888"
                    history_html += f"""
                    <div style='font-size:0.8rem; margin-bottom:8px; border-bottom:1px solid #444; padding-bottom:4px; font-family:monospace;'>
                        <span style='color:#888;'>#{rec['hand_no']}</span> | <b>{rec['winner']}</b> | 
                        <span style='color:{net_color};'>${rec['net']:+,.2f}</span>
                    </div>"""
                st.markdown(f'<div style="height: 200px; overflow-y: auto;">{history_html}</div>', unsafe_allow_html=True)
            else:
                st.caption("No records." if st.session_state.lang == "EN" else "本靴暂无记录")

        if st.session_state.end_shoe:
            st.warning("🟥 切牌线已到" if st.session_state.lang == "CN" else "🟥 CUT CARD REACHED")

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
            st.button(lt.get("btn_deal"), use_container_width=True, type="primary", 
                      disabled=st.session_state.end_shoe, on_click=handle_deal_click)
        
        with c_auto:
            is_active = st.session_state.get('auto_run_active', False)
            auto_label = "🤖 自动运行" if is_cn else "🤖 AUTORUN"
            stop_label = "🛑 停止运行" if is_cn else "🛑 STOP"
            curr_label = stop_label if is_active else auto_label
            curr_type = "primary" if is_active else "secondary"
            
            if st.button(curr_label, use_container_width=True, type=curr_type, key="auto_btn"):
                st.session_state.auto_run_active = not is_active
                st.rerun()

        with c2:
            if st.button(lt.get("btn_new_shoe"), use_container_width=True):
                reset_logic()
                st.rerun()

        with c3:
            label_marker = "🎯 标记模式" if is_cn else "🎯 MARKER"
            label_natural = "🍃 自然模式" if is_cn else "🍃 NATURAL"
            curr_mode = label_marker if st.session_state.marker_mode else label_natural
            if st.button(curr_mode, use_container_width=True):
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
                            st.balloons()
                            if decision["edge"] > 0.01: st.snow()
                            st.session_state.last_balloon_hash = state_hash
                    else:
                        fp_advice.update({"status": lang_map["miss"], "fp_id": state_hash})

        # 3. 最终 UI 渲染 (严格像素对齐)
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

    # =========================================================
    # --- [逻辑修正] AUTORUN 引擎 (确保在 render_practice_tab 的最后一行) ---
    # =========================================================
    if st.session_state.get('auto_run_active', False):
        if st.session_state.get('end_shoe', False) or st.session_state.balance < 10:
            st.session_state.auto_run_active = False
            st.rerun()
        else:
            # 给用户留出 0.5 秒看牌的时间
            time.sleep(0.5) 
            # 执行发牌逻辑
            handle_deal_click(is_auto=True)
            # 引擎触发重绘，进入下一手循环
            st.rerun()

