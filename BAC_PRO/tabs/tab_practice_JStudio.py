# ---------------------------------------------------------
# tab_practice_JStudio_Autorun_v1.py
#完全封装的AUTORUN，完整保留MANUAL DEAL
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
from core.orchestrator import Orchestrator
from core.data_center import DataCenter
from core.decision_center import DecisionCenter
from core.strategy_engine import StrategyEngine
from core.report_service import ReportService
import streamlit as st
import streamlit.components.v1 as components

@st.dialog("📈 综合报表")
def show_summary_report_dialog():

    service = ReportService(st.session_state.record_adapter)
    uid = st.session_state.auth_user

    df = service.get_summary_df(uid)

    if df is None or df.empty:
        st.info("No data")
        return

    html = service.build_html_report(df)

    components.html(html, height=650, scrolling=True)

@st.dialog("📊 最近 20 手下注")
def show_recent_bets_dialog():

    service = ReportService(st.session_state.record_adapter)
    uid = st.session_state.auth_user
    is_cn = st.session_state.get("lang") == "CN"

    df = service.get_recent_bets_df(uid, limit=20)

    df = service.render_recent_bets_df(df, is_cn)

    st.dataframe(df, width='stretch')

  


            
def render_practice_tab(lang):
    def render_ai_config_panel(label_hmin, label_blen):
        # 初始化默认值
        if 'hist_min_slider' not in st.session_state:
            st.session_state.hist_min_slider = 3
        if 'bet_len_slider_input' not in st.session_state:
            st.session_state.bet_len_slider_input = 3
        if 'current_strategy_key' not in st.session_state:
            st.session_state.current_strategy_key = "000"
        # 新增：初始化锁定状态
        if 'lock_ai_config' not in st.session_state:
            st.session_state.lock_ai_config = False

        # =========================================================
        # ✅ AI CONFIG FORM — 保留 form 防抖，修复写入时机
        # =========================================================
        with st.sidebar.form("ai_config_form"):
            is_cn = st.session_state.get('lang', 'CN') == "CN"

            # --- 1. HIST LEN ---
            h_min = st.slider(
                label="历史扫描深度 (Scanning Depth)" if is_cn else "Scanning Depth",
                min_value=3,
                max_value=14,
                value=st.session_state.hist_min_slider,
                disabled=st.session_state.lock_ai_config  # 锁定逻辑同步
            )

            # --- 2. BET LEN ---
            b_len = st.slider(
                label="起步长度门槛 (BET_DEPTH)" if is_cn else "Betting Depth",
                min_value=3,
                max_value=14,
                value=st.session_state.bet_len_slider_input,
                disabled=st.session_state.lock_ai_config  # 锁定逻辑同步
            )

            # --- 3. STRATEGY MATRIX ---
            strat_options = ["000", "100", "110", "120", "111", "121", "137", "AUTO","XYZ"]
            current_strat = st.session_state.current_strategy_key
            strat_index = strat_options.index(current_strat) if current_strat in strat_options else 0

            selected_strat = st.selectbox(
                label="投注策略矩阵" if is_cn else "Betting Strategy Matrix",
                options=strat_options,
                index=strat_index,
                disabled=st.session_state.lock_ai_config  # 锁定逻辑同步
            )

            # 修改：增加 disabled 参数
            submitted = st.form_submit_button(
                "✅ APPLY & LOCK", 
                disabled=st.session_state.lock_ai_config
            )

        # =========================================================
        # 🚀 关键修复：写入逻辑移到 form 块外部
        # =========================================================
        if submitted:
            st.session_state.hist_min_slider = h_min
            st.session_state.bet_len_slider_input = b_len
            st.session_state.current_strategy_key = selected_strat
            st.session_state.strategy_mode = "S1-AUTO" if selected_strat == "AUTO" else f"S1-{selected_strat}"
            
            # 修改：点击后将状态置为 True
            st.session_state.lock_ai_config = True
            
            st.toast(f"✅ Config Applied: H{h_min} / B{b_len} / {selected_strat}")
            st.rerun()

        # =========================================================
        # 💡 提示：Orchestrator 内部读取逻辑校验
        # =========================================================
        # 请确保 core/orchestrator.py 内部是这样读取的：
        # h_min = session_state.get("hist_min_slider", 3)
        # b_len = session_state.get("bet_len_slider_input", 3)
        # strat = session_state.get("current_strategy_key", "000")
 
    # 定义常量约束
    #MAX_SHOES = 10000
    is_cn = lang == "CN"


    # --- 1. 核心初始化（必须放在最前面） ---
    if "strategy_engine" not in st.session_state:
        # 确保你已经从 core.strategy_engine 导入了 StrategyEngine
        st.session_state.strategy_engine = StrategyEngine()
    
    if "auto_state" not in st.session_state:
        st.session_state.auto_state = "STOP"
        
    if "auto_clean_seq" not in st.session_state:
        st.session_state.auto_clean_seq = []
    if 'bet_input_red' not in st.session_state: st.session_state.bet_input_red = 0
    if 'bet_input_blue' not in st.session_state: st.session_state.bet_input_blue = 0
    if 'marker_mode' not in st.session_state: st.session_state.marker_mode = False
    if 'styled_results' not in st.session_state: st.session_state.styled_results = []
    if 'clean_results' not in st.session_state: st.session_state.clean_results = []
    if "auto_state" not in st.session_state:st.session_state.auto_state = "IDLE"
    if "auto_tick" not in st.session_state:st.session_state.auto_tick = 0
    if "auto_lock" not in st.session_state:st.session_state.auto_lock = False
    # 在 render_practice_tab 函数内的变量初始化区域添加：
    if 'bet_len_slider' not in st.session_state: st.session_state.bet_len_slider = 1
    if 'strategy_mode' not in st.session_state: st.session_state.strategy_mode = "单注 (Streak-1)"
    # --- 约第 35 行附近 ---
    if 'ai_zone_container' not in st.session_state: st.session_state.ai_zone_container = st.empty()
    if 'streak_counter' not in st.session_state:st.session_state.streak_counter = 0
    # --- 2. 语言与样式初始化 (核心修复：提前定义 lt) ---
    lt = TRANSLATIONS.get(st.session_state.lang, {})
    def t(key): return TRANSLATIONS.get(st.session_state.lang, {}).get(key, key)
    
    container_style = "padding:18px;border:2px solid #1E90FF;border-radius:15px;background-color:#0a141e;box-shadow:0 4px 15px rgba(0,0,0,0.5);min-height:320px;color:#FFFFFF;display:flex;flex-direction:column;box-sizing:border-box;"
    header_style = "font-weight:bold;color:#1E90FF;font-size:1.1rem;letter-spacing:1px;margin-bottom:12px;border-bottom:1px solid #1E90FF44;padding-bottom:8px;display:flex;justify-content:space-between;align-items:center;"

    def reset_logic():
        # A. 语言映射与基础校验
        is_cn = st.session_state.get('lang', 'cn') == 'cn'
        
        # B. 检查余额 (新靴开始前必须校验)
        if st.session_state.balance < 100:
            msg = "余额不足，无法开启新靴。" if is_cn else "Insufficient balance for new shoe."
            st.error(msg)
            st.stop()
            return

        # C. 物理实体工厂重置 (保持原样)
        if 'factory' not in st.session_state:
            st.session_state.factory = ShoeFactory()
        st.session_state.shoe = st.session_state.factory.create_shoe()
        st.session_state.cut_card_at = random.randint(14, 20)
        st.session_state.end_shoe = False

        # ---------------------------------------------------------
        # 🚀 核心改进点：原材料物理隔离 (锁定 HASH 工厂的纯净数据源)
        # ---------------------------------------------------------
        # 强制清空自动引擎序列，确保下一手发出的牌是本靴第一手
        st.session_state.auto_clean_seq = [] 

        # 换靴时强制归零引擎，防止上一靴的 ACTIVE/B-LOCK 状态污染新靴
        if "strategy_engine" in st.session_state:
            st.session_state.strategy_engine._terminate()
            
        # 决策状态同步重置：清除上一靴的匹配残余，将 ID 标记为 NEW_SHOE
        st.session_state.last_fp_advice = {
            "match": False,
            "fp_id": "NEW_SHOE_READY",
            "action": "WAIT",
            "status": "READY",
            "edge": 0,
            "ev_cut": 0,
            "ev_cont": 0,
            "tie_hold": False,
        }
        
        # ---------------------------------------------------------

        # D. UI 与 统计量重置 (保持原样)
        st.session_state.results = []
        st.session_state.clean_results = []
        st.session_state.styled_results = []
        st.session_state.stats = {"B": 0, "P": 0, "T": 0}
        st.session_state.rank_counts = {i: (128 if i == 0 else 32) for i in range(10)}
        st.session_state.last_outcome_obj = None
        if "strategy_engine" in st.session_state:st.session_state.strategy_engine._terminate()
        # 终端调试日志
        import sys
        sys.stdout.write(">>> [FACTORY] 原材料仓库已归零。准备为新靴进行第一次采样拍照。\n")
        sys.stdout.flush()

    if 'bac_pro_v8_final' not in st.session_state:
        st.session_state.dealer = BaccaratDealer()
        st.session_state.factory = ShoeFactory(decks=8)
        # ✅ 从 Redis 读取真实余额，读取失败才用 0 占位
        try:
            _uid = st.session_state.get('auth_user', '').upper()
            _adapter = st.session_state.get('record_adapter')
            if _adapter and _uid:
                _val = _adapter.client.hget(f"u:info:{_uid}", "balance")
                st.session_state.balance = float(_val) if _val is not None else 0.0
            else:
                st.session_state.balance = 0.0
        except Exception:
            st.session_state.balance = 0.0
        reset_logic()
        st.session_state.bac_pro_v8_final = True
    else:
        # ✅ 防御性检查：每次 exec_module 后重建类引用
        # 动态加载导致每次重渲染产生新的类对象，必须用 isinstance 校验类型一致性
        try:
            dealer_ok = isinstance(st.session_state.get('dealer'), BaccaratDealer)
        except Exception:
            dealer_ok = False
        try:
            factory_ok = isinstance(st.session_state.get('factory'), ShoeFactory)
        except Exception:
            factory_ok = False
        try:
            shoe_ok = st.session_state.get('shoe') is not None and factory_ok
        except Exception:
            shoe_ok = False

        if not dealer_ok:
            st.session_state.dealer = BaccaratDealer()
        if not factory_ok:
            st.session_state.factory = ShoeFactory(decks=8)
        

        # 基础列表兜底
        for _key in ['clean_results', 'styled_results', 'results']:
        ###for _key in ['clean_results', 'styled_results', 'results', 'bet_history']:
            if _key not in st.session_state:
                st.session_state[_key] = []

    def execute_physical_deal():
        try:
            shoe = st.session_state.get("shoe")
            if shoe is None:
                st.session_state.auto_state = "STOP"
                return None

            # 1. 执行物理抽牌
            oc = st.session_state.dealer.deal_one_hand(shoe)
            res = oc.winner
            
            # 2. 更新基础统计 (B/P/T 计数)
            st.session_state.rank_counts, st.session_state.stats = update_shoe_stats(
                oc, st.session_state.rank_counts, st.session_state.stats
            )

            # 3. 更新原始结果列表
            st.session_state.results.append(res)

            # 4. 更新大路专用渲染列表 (styled_results)
            # 注意：自动模式下暂不计算 AI 匹配和 Marked Len，先保证渲染出来
            st.session_state.styled_results.append({
                "v": res,
                "m": False,  # 稍后由 Orchestrator 更新或在此计算
                "r": 1 if res != 'T' else None,
                "action": None
            })

            # 5. 更新清洗后的序列 (用于算法计算)
            if res in ['B', 'P']:
                st.session_state.clean_results.append(res)


            import sys
            _SEP = "=" * 48
            sys.stdout.write(f"\n{_SEP}\n")
            sys.stdout.write(f"[大路渲染] 🎰 结果: {res} | 数据已回填至 SessionState\n")
            sys.stdout.flush()
            return res

        except IndexError:
            st.session_state.auto_state = "STOP"
            st.session_state.end_shoe = True
            return None
        except Exception as e:
            st.session_state.auto_state = "STOP"
            return None
        
    def handle_deal_click():
        # 0. 初始状态重置
        is_ai_match = False
        current_action = None
        
        # B. 检查余额 - 仅在已初始化后才校验
        if st.session_state.get('bac_pro_v8_final'):
            try:
                _uid = st.session_state.get('auth_user', '').upper()
                _adapter = st.session_state.get('record_adapter')
                if _adapter and _uid:
                    _val = _adapter.client.hget(f"u:info:{_uid}", "balance")
                    st.session_state.balance = float(_val) if _val is not None else 0.0
            except Exception:
                pass

            if st.session_state.get('balance', 0) < 100:
                msg = "余额不足，无法开启新靴。" if is_cn else "Insufficient balance for new shoe."
                st.error(msg)
                st.stop()
                return
        
        if 'styled_results' not in st.session_state:
            st.session_state.styled_results = []
        if 'clean_results' not in st.session_state:
            st.session_state.clean_results = []

        # --- 1. Redis 初始化 ---
        if 'redis_adapter' not in st.session_state or 'record_adapter' not in st.session_state:
            try:
                prod_url = st.secrets["BACC_PRO_PROD"]["REDIS_URL"]
                st.session_state.redis_adapter = RedisAdapter(prod_url)
                record_url = st.secrets["UNIFIED_ACCOUNT_SYSTEM"]["REDIS_URL"]
                st.session_state.record_adapter = RedisAdapter(record_url)
            except Exception as e:
                st.error(f"Redis 初始化失败: {e}")

        # --- 读取下注 ---
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
                        if x == pre_cur_side:
                            pre_cur_len += 1
                        else:
                            break
                
                betting_moment_len = pre_cur_len

                # --- 3. 物理发牌 ---
                oc = st.session_state.dealer.deal_one_hand(st.session_state.shoe)
                st.session_state.last_outcome_obj = oc
                res = oc.winner

                # --- 4. 结算 ---
                new_bal, net_profit, _ = settle_hand(res, current_bets, st.session_state.balance)
                st.session_state.balance = new_bal

                # --- 计数逻辑 ---
                actual_bet_made = current_bets["B"] + current_bets["P"]
                if actual_bet_made > 0:
                    if res in ['B', 'P']:
                        st.session_state.streak_counter += 1

                # --- 5. AI 判定 ---
                adapter = st.session_state.get('redis_adapter')
                h_min = st.session_state.get('hist_min_slider', 3)
                b_len_threshold = st.session_state.get('bet_len_slider_input', 3)

                if adapter and res in ['B', 'P']:
                    current_full_seq = pre_deal_seq + [res]

                    check_side = current_full_seq[-1]
                    check_len = 0
                    for x in reversed(current_full_seq):
                        if x == check_side:
                            check_len += 1
                        else:
                            break

                    components = get_fp_components(current_full_seq, h_min=h_min)
                    state_hash = generate_fp_hash(*components)

                    shared_payload = {
                        "hash": state_hash,
                        "decision": None,
                        "status": f"WAITING ({check_len}/{b_len_threshold})"
                    }

                    if check_len >= b_len_threshold:
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

                            shared_payload["decision"] = decision
                            shared_payload["status"] = "MATCHED"
                        else:
                            is_ai_match = False
                            shared_payload["status"] = f"NO MATCH ({check_len})"
                    else:
                        is_ai_match = False
                        shared_payload["status"] = f"WAITING ({check_len}/{b_len_threshold})"

                    st.session_state['shared_ai_data'] = shared_payload

                # --- 6. 渲染强度 ---
                marked_len_for_ui = 0
                if res in ['B', 'P']:
                    if betting_moment_len > 0 and res == pre_deal_seq[-1]:
                        marked_len_for_ui = betting_moment_len + 1
                    else:
                        marked_len_for_ui = 1

                # --- 7. Redis 写入 ---
                record_writer = st.session_state.get('record_adapter')
                if record_writer and actual_bet_made > 0:
                    try:
                        target_uid = st.session_state.get('auth_user', "J")
                        target_uname = st.session_state.get('username', f"User_{target_uid}")
                        act_map = {"C": "CUT", "S": "CONTINUE"}
                        act = act_map.get(current_action, "MANUAL")

                        record_writer.record_app_transaction(
                            user_id=target_uid,
                            username=target_uname,
                            amount=net_profit,
                            tx_type="DEAL",
                            strategy=st.session_state.get('strategy_mode', "V8_AUTO"),
                            hist_len=h_min,
                            bet_len=betting_moment_len,
                            action=act
                        )
                    except Exception as e:
                        print(f"Redis Sync Error: {e}")

                # --- 8. 更新路单 ---
                st.session_state.rank_counts, st.session_state.stats = update_shoe_stats(
                    oc, st.session_state.rank_counts, st.session_state.stats
                )
                st.session_state.results.append(res)

                bet_res = "win" if net_profit > 0 else "loss" if actual_bet_made > 0 and res != 'T' else None

                st.session_state.styled_results.append({
                    "v": res,
                    "m": is_ai_match,
                    "r": marked_len_for_ui if res != 'T' else bet_res,
                    "action": current_action
                })

                # --- 9. clean_results ---
                if res in ['B', 'P']:
                    st.session_state.clean_results.append(res)

                    current_clean_seq = st.session_state.clean_results


            except IndexError:
                st.session_state.end_shoe = True

            finally:
                pass


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

        #渲染HIST_LEN , BET_LEN 参数
        render_ai_config_panel(label_hmin, label_blen)



        
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
        #####--------------------新修改V8----------------

                # --- UI 输入（不直接写 session_state） ---
        ui_b = st.number_input(
            "B",
            value=float(st.session_state.get('bet_input_red', 0)),
            step=100.0,
            format="%.0f"
        )

        ui_p = st.number_input(
            "P", 
            value=float(st.session_state.get('bet_input_blue', 0)),
            step=100.0,
            format="%.0f"
        )

        # --- 只有用户改了才写回 ---
        if ui_b != st.session_state.get('bet_input_red', 0):
            st.session_state.bet_input_red = ui_b

        if ui_p != st.session_state.get('bet_input_blue', 0):
            st.session_state.bet_input_blue = ui_p

        #####--------------------新修改V8结束----------------
            
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
            # 只要在运行中，或者牌靴结束，就禁用 DEAL
            is_busy = (st.session_state.get("auto_state") == "RUNNING")
            
            st.button(
                lt.get("btn_deal"), 
                use_container_width=True, 
                type="primary", 
                disabled=st.session_state.end_shoe or is_busy, 
                on_click=handle_deal_click
            )
        with c_auto:
            is_cn = (lang == "CN")
            a_label = "🤖 自动运行" if is_cn else "🤖 AUTORUN"
            s_label = "🛑 停止运行" if is_cn else "🛑 STOP"

            # --- 1. 权限检查 ---
            autorun_enabled = False
            try:
                _adapter = st.session_state.get('record_adapter')
                _uid = st.session_state.get('auth_user', '').upper()
                if _adapter and _uid:
                    _val = _adapter.client.hget(f"u:info:{_uid}", "balance")
                    autorun_enabled = float(_val) > 1_000_000 if _val else False
            except:
                autorun_enabled = False

            is_running = (st.session_state.auto_state == "RUNNING")

            # --- 2. 按钮逻辑 ---
            # 按钮点击后会切换 auto_state 状态
            if st.button(
                s_label if is_running else a_label,
                use_container_width=True, # 替代 width="stretch"
                type="primary" if is_running else "secondary",
                disabled=not autorun_enabled
            ):
                if is_running:
                    # 点击 STOP：将状态设为 STOP，系统会停止自动调用执行逻辑
                    st.session_state.auto_state = "STOP"
                else:
                    # 点击 AUTORUN：启动运行，重置计数器
                    st.session_state.auto_state = "RUNNING"
                    st.session_state.auto_tick = 0
                
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
        #if 'ai_zone_placeholder' not in st.session_state:
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

        # ---------------------------------------------------------
        # 🚀 修改部分：由【主动计算】改为【被动读取】
        # ---------------------------------------------------------
        # 这里的 last_fp_advice 是由后台驱动引擎 Orchestrator.run() 统一更新的
        fp_advice = st.session_state.get('last_fp_advice', {"match": False, "status": "WAITING", "fp_id": ""})
        
        # 触发特效：保留原有的逻辑，但 state_hash 改为从 fp_advice 中提取
        if fp_advice.get("match"):
            state_hash = fp_advice.get("fp_id")
            if st.session_state.get("last_balloon_hash") != state_hash:
                if fp_advice.get("edge", 0) > 0.01: 
                    st.snow()
                st.session_state.last_balloon_hash = state_hash
        # ---------------------------------------------------------
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
                act = fp_advice.get("action", "?")
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
                # 使用 .get() 安全获取状态，如果键不存在则回退到 lang_map 中的默认文字
                status_text = fp_advice.get("status", lang_map.get("miss", "NO MATCH"))
                html += f'''
                    <div style="margin-top:40px;text-align:center;">
                        <div style="color:#FF4444;font-size:0.9rem;margin-bottom:8px;font-weight:bold;">⚠️ {status_text}</div>
                    </div>
                '''

            html += '</div>'
            st.markdown(html, unsafe_allow_html=True)
# ---------------------------------------------------------
    # [FINAL STEP] 强化型自动化驱动引擎 (唯一真理源)
    # ---------------------------------------------------------
    if st.session_state.get("auto_state") == "RUNNING":
        
        # A. 换靴逻辑 (略, 保持你之前的 reset_logic 即可)
        if st.session_state.get("end_shoe", False):
            import sys
            sys.stdout.write("\n>>> [SYSTEM] SHOE END - RESETTING...\n")
            sys.stdout.flush()
            reset_logic()
            time.sleep(2.0)
            st.rerun()

        # B. 正常驱动逻辑
        else:
            # 1. 物理层动作：产生新结果
            res = execute_physical_deal()
            
            if res is not None:
                import sys
                import traceback
                try:
                    # ── 调度层：四张证件的唯一入口 ──────────────────
                    orch = Orchestrator(
                        data_center=DataCenter(st.session_state),
                        decision_center=DecisionCenter(st.session_state.get('redis_adapter')),
                        strategy_engine=st.session_state.strategy_engine,
                        redis_record=st.session_state.get('record_adapter')
                    )
                    orch.run(context={"last_result": res}, session_state=st.session_state)

                    # ── 🪖 【退休证】帧收尾汇总 ──────────────────────
                    # Orchestrator 已完成四张证件的完整流程，
                    # 此处读取最终落盘结果，确认本帧与 UI 的一致性。
                    final_advice = st.session_state.get('last_fp_advice', {})
                    is_match     = final_advice.get('match', False)
                    status       = final_advice.get('status', 'N/A')
                    action       = final_advice.get('action', '—')
                    edge         = final_advice.get('edge', 0)
                    tie_hold     = final_advice.get('tie_hold', False)

                    import sys
                    _SEP = "=" * 48
                    sys.stdout.write(
                        f"🪖 [退休证] 帧闭环确认\n"
                        f"           本帧结果 : {res}"
                        f"  tie_hold={tie_hold}\n"
                        f"           UI状态   : match={is_match}"
                        f"  status={status}\n"
                        f"           建议方向 : action={action}"
                        f"  edge={edge:+.4f}\n"
                        f"           → 本帧证件链完整，准备 rerun\n"
                        f"{_SEP}\n"
                    )
                    sys.stdout.flush()

                except Exception as e:
                    sys.stdout.write(
                        f"💥 [CRITICAL ERROR] 证件链断裂于本帧\n"
                        f"           result={res}\n"
                        f"           error ={str(e)}\n"
                    )
                    traceback.print_exc()
                    sys.stdout.flush()

                time.sleep(1.2)
                st.rerun()
