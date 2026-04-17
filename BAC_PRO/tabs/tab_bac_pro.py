import streamlit as st
import os
import sys
# --- 1. 基础路径配置 (必须最先运行) ---
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

# 现在可以安全导入了
try:
    from modules.i18n import t
except ImportError:
    # 备用方案：如果 i18n 还没写好，防止崩溃
    def t(key, lang): return key

# ✅ 统一修改为直接从当前搜索路径导入
from tab_practice_JStudio import render_practice_tab
from tab_ai_vision import render_ai_vision_tab

def render_bac_pro_sidebar(lang):
    nav_labels = [t("nav_practice", lang), t("nav_ai", lang)]
    st.markdown("<p style='...'>ENGINE NAV</p>", unsafe_allow_html=True)
    
    current_choice = st.session_state.get('bac_menu_choice')
    
    # 查找当前选中项的索引
    try:
        active_index = nav_labels.index(current_choice)
    except (ValueError, KeyError):
        active_index = None # 如果是 None，则 radio 不会预选任何项

    # 使用 index=active_index，当 active_index 为 None 时，radio 处于未选中状态
    choice = st.radio(
        "BAC_MENU_RADIO", 
        nav_labels, 
        index=active_index, # Streamlit 1.35+ 支持 index=None
        label_visibility="collapsed",
        key="bac_sidebar_radio_internal" # 使用不同 key 避免冲突
    )
    
    # 如果用户手动点击了侧边栏，更新全局状态并重跑
    if choice != current_choice:
        st.session_state.bac_menu_choice = choice
        st.rerun()

def render_bac_pro_tab(lang):
    """
    主画面分发：如果未选中 Practice/AI，则渲染搬运过来的知识库内容。
    """
    is_cn = lang == "CN"
    current_choice = st.session_state.get('bac_menu_choice')

    # --- 路由分发 ---
    if current_choice == t("nav_practice", lang):
        render_practice_tab(lang)
    elif current_choice == t("nav_ai", lang):
        render_ai_vision_tab(lang)
    else:
        # --- 核心：原 tab_bacc_knowledge 的搬运内容 ---
        st.markdown("""
            <style>
            div[data-testid="stColumn"] button {
                color: white !important;
                font-weight: bold !important;
                height: 3.5rem !important;
                border: none !important;
                border-radius: 8px !important;
                width: 100% !important;
            }
            div[data-testid="stHorizontalBlock"] div[data-testid="stColumn"]:nth-of-type(1) button {
                background-color: #1E90FF !important;
            }
            div[data-testid="stHorizontalBlock"] div[data-testid="stColumn"]:nth-of-type(2) button {
                background-color: #FF4B4B !important;
            }
            </style>
        """, unsafe_allow_html=True)

        label_drill = "🧠 策略模拟训练 (DRILL)" if is_cn else "🧠 STRATEGY DRILL"
        label_live = "⚡ AI 现场决策 (LIVE)" if is_cn else "⚡ AI In-Play Vision"

        c1, c2 = st.columns(2)
        with c1:
            if st.button(label_drill, use_container_width=True, key="btn_drill_main"):
                st.session_state.bac_menu_choice = t("nav_practice", lang)
                st.rerun()
        with c2:
            if st.button(label_live, use_container_width=True, key="btn_live_main"):
                st.session_state.bac_menu_choice = t("nav_ai", lang)
                st.rerun()

        st.divider()
        
        
            # 严格按照用户要求的字体大小层级
    TITLE_SIZE = "2.2rem"    # TITLE: 加黑
    SUBTITLE_SIZE = "1.6rem" # SUBTITLE: 加黑, 比 Title 小一号
    BODY_SIZE = "1.1rem"     # 其他文字: 比 Subtitle 小一号

    if is_cn:
        st.markdown(f"""
        <div style="font-size: {TITLE_SIZE}; font-weight: bold; margin-bottom: 12px;">
            BACC-INTELLI Pro AI 引擎
        </div>
        
        <div style="font-size: {BODY_SIZE}; line-height: 1.6;">
            BacPro 是一款将万亿级大数据与人类直觉深度融合的新型博弈辅助工具。通过 AI 驱动的 Rank 权重算法与 1500 万在线特征指纹库，在不确定性中，为您捕捉那份瞬间的确定性。
        </div>

        <br>
        <div style="font-size: {SUBTITLE_SIZE}; font-weight: bold; margin-bottom: 8px;">
            🛡️ 核心技术：1万亿牌靴(Shoes) AI 训练成果
        </div>
        <div style="font-size: {BODY_SIZE}; line-height: 1.6;">
            • 数据底座：深度掌握大路形态在极端波动与常态分布的演变规律，及时捕捉概率切入点<br>
            • 1500万AI特征在线指纹库：在线AI指纹库毫秒级全量匹配，从 50:50 的均等漂移中锁定那稍纵即逝的赌场瞬间劣势。<br>
            • 瞬时响应：拍照上传路单，AI 立即完成识别比对，秒回数据反馈，供实时决策参考。
        </div>

        <br>
        <div style="font-size: {SUBTITLE_SIZE}; font-weight: bold; margin-bottom: 8px;">
            🧠 智能决策：数据驱动下的实时指导
        </div>
        <div style="font-size: {BODY_SIZE}; line-height: 1.6;">
            • 下注倾向分析：AI 结合 Rank 权重得分，实时返回当前瞬间庄闲的优势百分比。<br>
            • 策略动态优化：根据 AI 实时指导数据，动态调整下注策略与仓位（Bet Sizing）。在确定性最高时重注出击，在波动不稳时避险，实现逻辑化的头寸管理。
        </div>

        <br>
        <div style="font-size: {SUBTITLE_SIZE}; font-weight: bold; margin-bottom: 8px;">
            💡 核心功能：人机合一的自我训练
        </div>
        <div style="font-size: {BODY_SIZE}; line-height: 1.6;">
            本 App 采用 100% 真实盘数据，驱动玩家的深度进化：<br>
            1. 感知力重塑：在高频次对比训练中，培养对“赌场瞬间劣势”的生理性敏感度，强化实战中的自我控制。<br>
            2. 简单与专注：屏蔽所有无效干扰，剔除情绪化噪音，让注意力锁定在避开陷阱后的确定性瞬间。
        </div>

        <br>
        <div style="font-size: {SUBTITLE_SIZE}; font-weight: bold; margin-bottom: 8px;">
            🎯 核心愿景
        </div>
        <div style="font-size: {BODY_SIZE}; line-height: 1.6; font-style: italic;">
            博弈始终是概率游戏。瞬间得失属于正常波动，概率优势决定长期走势，而非即刻锁定胜局。<br>
            <b>科学博弈，从万亿级数据的避险与确定性捕捉开始。</b>
        </div>
        
        """, unsafe_allow_html=True)
        
        st.divider()
        st.markdown(f"""
        

        <div style="text-align: center; color: #888; font-family: sans-serif; font-size: 12px; margin-top: 40px; letter-spacing: 1px;">
        <strong>✎</strong> DESIGNED BY <strong>J STUDIO -- 简单➕专注</strong>

        """, unsafe_allow_html=True)

        
    else:
        st.markdown(f"""
        <div style="font-size: {TITLE_SIZE}; font-weight: bold; margin-bottom: 12px;">
            BACC-INTELLI Pro AI Engine
        </div>
        
        <div style="font-size: {BODY_SIZE}; line-height: 1.6;">
            BacPro is a next-generation betting assistant that deeply integrates trillion-level Big Data with human intuition. Driven by an AI-powered Rank Weighting Algorithm and a 15-million online feature fingerprint library, it captures that moment of certainty amidst uncertainty.
        </div>

        <br>
        <div style="font-size: {SUBTITLE_SIZE}; font-weight: bold; margin-bottom: 8px;">
            🛡️ Core Technology: AI Training from 1 Trillion Shoes
        </div>
        <div style="font-size: {BODY_SIZE}; line-height: 1.6;">
            • Data Foundation: Mastery of Big Road pattern evolution across extreme fluctuations and normal distributions to pinpoint high-probability entry points.<br>
            • 15-Million AI Feature Online Fingerprint Library: Achieve millisecond-level full matching across our massive online database. Pinpoint those fleeting moments of casino disadvantage, locking onto the edge even within a 50:50 equilibrium drift.<br>
            • Instant Response: Snap and upload roadmaps; AI completes identification and comparison instantly, returning real-time data for decision support.
        </div>

        <br>
        <div style="font-size: {SUBTITLE_SIZE}; font-weight: bold; margin-bottom: 8px;">
            🧠 Intelligent Decision-Making: Data-Driven Guidance
        </div>
        <div style="font-size: {BODY_SIZE}; line-height: 1.6;">
            • Betting Tendency Analysis: AI combines Rank Weighting scores to return real-time Banker/Player advantage percentages.<br>
            • Dynamic Strategy Optimization: Self-adjust betting strategies and Bet Sizing based on real-time AI guidance. Strike hard at peak certainty and hedge during volatility to achieve logical position management.
        </div>

        <br>
        <div style="font-size: {SUBTITLE_SIZE}; font-weight: bold; margin-bottom: 8px;">
            💡 Core Function: Human-AI Synergy Training
        </div>
        <div style="font-size: {BODY_SIZE}; line-height: 1.6;">
            Powered by 100% real-shoe data, this app drives the deep evolution of players:<br>
            1. Perception Remolding: High-frequency training develops physiological sensitivity to "Instantaneous Casino Disadvantage," strengthening self-control.<br>
            2. Simplicity & Focus: Filter out noise and emotional interference to lock focus on the moment of certainty after bypassing traps.
        </div>

        <br>
        <div style="font-size: {SUBTITLE_SIZE}; font-weight: bold; margin-bottom: 8px;">
            🎯 Core Vision
        </div>
        <div style="font-size: {BODY_SIZE}; line-height: 1.6; font-style: italic;">
            Betting is always a game of probability. Instant gains or losses are normal fluctuations; a probabilistic edge determines the long-term trend, not an immediate victory.<br>
            <b>Scientific betting begins with risk evasion and certainty capture through trillion-level data.</b>
        </div>
    
        """, unsafe_allow_html=True)

        st.divider()
        st.markdown(f"""
        

        <div style="text-align: center; color: #888; font-family: sans-serif; font-size: 12px; margin-top: 40px; letter-spacing: 1px;">
        <strong>✎</strong> DESIGNED BY <strong>J STUDIO -- SIMPLICITY & FOCUS</strong>

        """, unsafe_allow_html=True)







       
