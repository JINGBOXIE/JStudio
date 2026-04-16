#modules/tab_main_launcher.py
import streamlit as st

def render_launcher_home(lang):
    """
    渲染门户主页内容：功能模块详细介绍与系统状态
    """
    # 1. 语言文案配置
    if lang == "CN":
        TITLE = "J STUDIO | 核心功能矩阵"
        DESC = "欢迎访问统一集成开发环境。当前核心引擎已就绪："
        
        # 模块介绍
        MOD_IMARKET = {
            "title": "📈 iMarket Pro",
            "desc": "实时金融数据监控与决策支持。集成 TSLA 成本分析、宏观新闻聚合及深度市场趋势扫描。"
        }
        MOD_BACPRO = {
            "title": "🃏 BAC_PRO Engine",
            "desc": "基于 AI 指纹识别的大规模数据模拟器。支持 10 亿级样本运行，实现精准的模式识别与逻辑校验。"
        }
        MOD_BOOK = {
            "title": "📜 The Great Way",
            "desc": "大道至简：深度哲学讨论社区。旨在将复杂的哲学思考系统化、简洁化（模块开发中）。"
        }
        
        STATUS_TITLE = "🛰️ 系统运行状态"
        TIP = "提示：点击左侧功能键进入具体模块，点击底部 EXIT 安全登出。"
    else:
        TITLE = "J STUDIO | CORE MATRIX"
        DESC = "Welcome to the unified environment. Core engines are currently active:"
        
        # Module Info
        MOD_IMARKET = {
            "title": "📈 iMarket Pro",
            "desc": "Real-time financial monitoring. Integrated TSLA cost-basis analysis and macro market intelligence."
        }
        MOD_BACPRO = {
            "title": "🃏 BAC_PRO Engine",
            "desc": "AI Fingerprint scanning & massive data simulation. Supports 1-billion-sample pattern recognition."
        }
        MOD_BOOK = {
            "title": "📜 The Great Way",
            "desc": "Philosophy Simplified: A deep thinking forum designed for systemic conceptual clarity (In Dev)."
        }
        
        STATUS_TITLE = "🛰️ SYSTEM STATUS"
        TIP = "Tip: Use sidebar buttons to switch modules. Click EXIT to log out securely."

    # --- 2. UI 渲染 ---
    
    # 标题与简介
    st.markdown(f"### {TITLE}")
    st.info(DESC)

    # 3. 功能介绍卡片 (使用 HTML/CSS 打造黑金质感)
    col1, col2, col3 = st.columns(3)

    # 通用卡片样式定义
    card_style = """
        padding: 20px; 
        border-radius: 12px; 
        border: 1px solid #333; 
        background-color: #1a1a1a; 
        min-height: 200px;
        transition: transform 0.3s ease;
    """

    with col1:
        st.markdown(f"""
        <div style="{card_style}">
            <h4 style="color:#d4af37; margin-top:0;">{MOD_IMARKET['title']}</h4>
            <p style="font-size:0.85rem; color:#888; line-height:1.6;">{MOD_IMARKET['desc']}</p>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown(f"""
        <div style="{card_style}">
            <h4 style="color:#d4af37; margin-top:0;">{MOD_BACPRO['title']}</h4>
            <p style="font-size:0.85rem; color:#888; line-height:1.6;">{MOD_BACPRO['desc']}</p>
        </div>
        """, unsafe_allow_html=True)

    with col3:
        st.markdown(f"""
        <div style="{card_style}">
            <h4 style="color:#d4af37; margin-top:0;">{MOD_BOOK['title']}</h4>
            <p style="font-size:0.85rem; color:#888; line-height:1.6;">{MOD_BOOK['desc']}</p>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")

    # 4. 系统运行指标 (增强开发环境氛围)
    st.write(f"#### {STATUS_TITLE}")
    s_col1, s_col2, s_col3, s_col4 = st.columns(4)
    
    s_col1.metric("Node Status", "ACTIVE", delta="Normal")
    s_col2.metric("Sync Latency", "24ms", delta="-2ms")
    s_col3.metric("DB Connections", "Secure", delta="SSL ON")
    s_col4.metric("AI Core", "Gemini 3 Flash", delta="READY")

    # 底部说明
    st.caption(TIP)