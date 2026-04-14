# main.py
import streamlit as st
import os
import sys
import base64
from modules.i18n import t
from tabs.tab_practice import render_practice_tab
from tabs.tab_ai_vision import render_ai_vision_tab  
from tabs.tab_bacc_knowledge import render_knowledge_tab
from core.db_adapter import RedisAdapter

def get_base64_img(file_path):
    try:
        with open(file_path, "rb") as f:
            data = f.read()
        return base64.b64encode(data).decode()
    except Exception:
        return None

# 1. 路径注入
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# 2. 全局页面配置
st.set_page_config(
    layout="wide", 
    page_title="BACC-INTELLI Pro | Studio <The Great Way, Made Simple>", 
    page_icon="🤖"
)

# main.py
if "redis_adapter" not in st.session_state:
    st.session_state.redis_adapter = RedisAdapter(st.secrets["REDIS_URL"])



# 3. 初始化全局状态
if 'lang' not in st.session_state:
    st.session_state.lang = "EN"

# ✅ 默认启动页面设置为：首页/知识库
if 'menu_choice' not in st.session_state:
    st.session_state.menu_choice = t("nav_knowledge", st.session_state.lang)

# 4. 侧边栏布局
with st.sidebar:
    # Logo 展示
    st.image("assets/J Studio LOGO.PNG", use_container_width=True)

    # --- 语言选择器 ---
    lang_options = {"EN": "English", "CN": "中文"}
    curr_lang_idx = 0 if st.session_state.lang == "EN" else 1
    
    selected_lang = st.radio(
        "语言 / LANGUAGE",
        options=list(lang_options.keys()),
        index=curr_lang_idx,
        format_func=lambda x: lang_options[x],
        horizontal=True,
        key="lang_selector_widget" # 独立 Key
    )
    
    # 如果切换语言，同步更新菜单文本以防 index 溢出
    if selected_lang != st.session_state.lang:
        # 获取切换前的菜单索引，用于保持在当前页面
        old_labels = [t("nav_practice", st.session_state.lang), t("nav_ai", st.session_state.lang), t("nav_knowledge", st.session_state.lang)]
        try:
            curr_idx = old_labels.index(st.session_state.menu_choice)
        except:
            curr_idx = 2
        
        st.session_state.lang = selected_lang
        # 更新 menu_choice 为新语言下的对应文本
        new_labels = [t("nav_practice", selected_lang), t("nav_ai", selected_lang), t("nav_knowledge", selected_lang)]
        st.session_state.menu_choice = new_labels[curr_idx]
        st.rerun()

    st.divider()

    # --- 功能菜单导航 ---
    # 定义所有标签库
    full_nav_labels = [
        t("nav_practice", st.session_state.lang), 
        t("nav_ai", st.session_state.lang), 
        t("nav_knowledge", st.session_state.lang)
    ]
    
    # ✅ 修改逻辑：一旦进入功能页，隐藏“知识库/首页”选项
    if st.session_state.menu_choice in [full_nav_labels[0], full_nav_labels[1]]:
        nav_labels = [full_nav_labels[0], full_nav_labels[1]]
    else:
        nav_labels = full_nav_labels

    # 根据全局变量动态计算 Index
    try:
        active_index = nav_labels.index(st.session_state.menu_choice)
    except ValueError:
        # 如果当前选中的不在 nav_labels 中（即刚从首页跳转），默认指向功能页
        active_index = 0

    choice = st.radio(
        "MENU", 
        nav_labels, 
        index=active_index,
        label_visibility="collapsed"
    )
    
    # 如果用户在侧边栏手动点击切换，同步回全局状态
    if choice != st.session_state.menu_choice:
        st.session_state.menu_choice = choice
        st.rerun()

    st.divider()

    # 签名展示
    sig_b64 = get_base64_img("assets/J Signature.png")
    if sig_b64:
        st.markdown(
            f"""
            <div style="display: flex; align-items: center; gap: 0px; font-size: 0.9rem; color: #1E90FF; font-family: sans-serif; font-weight: 500;">
                <span style="white-space: nowrap; margin-top: 2px;">👨‍💻 Code & Design: &nbsp;&nbsp;&nbsp</span>
                <img src="data:image/png;base64,{sig_b64}" 
                     style="height: 45px; margin-left: -5px; margin-bottom: -2px; filter: brightness(1.2) contrast(1.2);">
            </div>
            """, 
            unsafe_allow_html=True
        )
    else:
        st.markdown("<p style='color: #1E90FF; font-size: 0.9rem; font-weight: 500;'>👨‍💻 Code & Design: J Studio</p>", unsafe_allow_html=True)

    st.caption("👑 Powered by Gemini AI & OpenAI")

# --- 5. 路由分发 ---
# 根据全局状态渲染对应的 Tab
if st.session_state.menu_choice == t("nav_practice", st.session_state.lang):
    render_practice_tab(st.session_state.lang)
elif st.session_state.menu_choice == t("nav_ai", st.session_state.lang):
    render_ai_vision_tab(st.session_state.lang)
else:
    # 默认进入 BACC-INTELLI Pro AI Engine 首页
    render_knowledge_tab(st.session_state.lang)