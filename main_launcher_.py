import streamlit as st
import os
import sys
import base64
if 'bac_menu_choice' not in st.session_state:
    st.session_state.bac_menu_choice = None
# 1. 确保 CURRENT_DIR 被定义
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

# 2. 将必要的路径加入 sys.path
# 包含根目录和 BAC_PRO 目录，确保能找到 modules 文件夹
paths_to_add = [CURRENT_DIR, os.path.join(CURRENT_DIR, "BAC_PRO")]
for p in paths_to_add:
    if p not in sys.path:
        sys.path.insert(0, p)

# 3. 尝试导入翻译函数 t
try:
    from modules.i18n import t
except (ImportError, ModuleNotFoundError):
    # 🚀 兜底方案：如果导入失败，定义一个简单的 t 函数，直接返回 key
    # 这样可以防止程序报 NameError: name 't' is not defined
    def t(key, lang=None):
        return key
    print("WARNING: modules.i18n 导入失败，已启动简易翻译模式。")
    
import importlib.util


def get_base64_img(file_path):
    """将签名图片转为 Base64"""
    try:
        with open(file_path, "rb") as f:
            data = f.read()
        return base64.b64encode(data).decode()
    except Exception:
        return None
def load_tab_module(app_folder, tab_file):
    # 1. 强制获取并注入项目根目录 (JStudio 文件夹)
    # CURRENT_DIR 应该是你 main_launcher.py 所在的绝对路径
    if CURRENT_DIR not in sys.path:
        sys.path.insert(0, CURRENT_DIR)

    # 2. 获取子模块路径
    app_root = os.path.join(CURRENT_DIR, app_folder)
    tabs_path = os.path.join(app_root, "tabs")
    
    # 3. 注入子路径
    if app_root not in sys.path:
        sys.path.insert(0, app_root)
    if tabs_path not in sys.path:
        sys.path.insert(0, tabs_path)

    # 4. 执行加载逻辑
    file_path = os.path.join(tabs_path, tab_file)
    spec = importlib.util.spec_from_file_location(tab_file, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module) # 报错发生在这里
    return module
# --- 2. 页面配置与初始化 ---
st.set_page_config(
    layout="wide", 
    page_title="J Studio | Gaming Logic", 
    page_icon="🤖"
)

if 'lang' not in st.session_state: st.session_state.lang = "EN"
if 'auth_user' not in st.session_state: st.session_state.auth_user = None
if 'menu_choice' not in st.session_state: st.session_state.menu_choice = "PORTAL"
# ✨ 新增：初始化子引擎的状态，防止 KeyError
if 'bac_menu_choice' not in st.session_state: st.session_state.bac_menu_choice = None
L_MAP = {
    "CN": {
        "exit": "退出", 
        "bal": "J 资金余额", 
        "back": "返回主页",
        "welcome": "简单➕专注", 
        "select": "请选择左侧功能模块开始体验",
        # 新增以下三行
        "nav_im": "iMarket-投资AI引擎", 
        "nav_bp": "iBACCARAT-投注AI引擎", 
        "nav_gw": "博弈逻辑"
    },
    "EN": {
        "exit": "EXIT", 
        "bal": "J Balance", 
        "back": "PORTAL",
        "welcome": "J STUDIO | SIMPLICITY ◈ FOCUS", 
        "select": "Select Functional Engine from sidebar",
        # 新增以下三行
        "nav_im": "iMarket - AI ENGINE", 
        "nav_bp": "iBACCARAT- AI ENGINE", 
        "nav_gw": "GAMING LOGIC"
    }
}

# --- 3. 登录墙 ---
if not st.session_state.auth_user:
    # 1. 顶部留白
    st.markdown("<div style='margin-top:15vh;'></div>", unsafe_allow_html=True)
    
    # 2. 居中展示 Logo (缩放至约 1/4 面积)
    # 通过增加两边的比例 [1.5, 1, 1.5]，中间的图片只会占用总宽度的 1/4 左右
    _, img_col, _ = st.columns([1.5, 1, 1.5]) 
    with img_col:
        st.image("assets/banner.png", use_container_width=True)
    
    # 3. 登录表单
    _, col, _ = st.columns([1, 0.8, 1])
    with col:
        st.markdown("<div style='margin-top:30px;'></div>", unsafe_allow_html=True)
        u_id = st.text_input("Operator UID", placeholder="J / A / D").strip().upper()
        
        if st.button("ACCESS SYSTEM", use_container_width=True):
            if u_id in ['J', 'D', 'A']:
                st.session_state.auth_user = u_id
                st.rerun()
            else: 
                st.error("Access Denied")
    st.stop()
    
# --- 4. 侧边栏布局 ---
with st.sidebar:
    # A. Logo 展示
    logo_path = os.path.join(CURRENT_DIR, "assets", "banner.png")
    if os.path.exists(logo_path):
        st.image(logo_path, use_container_width=True)
    
    # B. 语言选择器
    lang_options = {"EN": "English", "CN": "中文"}
    selected_lang = st.radio("LANGUAGE/语言", options=list(lang_options.keys()), 
                             index=0 if st.session_state.lang == "EN" else 1,
                             format_func=lambda x: lang_options[x], horizontal=True)
    if selected_lang != st.session_state.lang:
        st.session_state.lang = selected_lang
        st.rerun()
    
    #st.markdown("---")

    sub_sidebar_slot = st.container()

    # --- C. 侧边栏公共导航区 ---
    # 只有在非首页或者特定条件下显示这些快捷导航
    if st.session_state.menu_choice == "PORTAL":
        st.write("Quick Navigation")
        if st.button(L_MAP[st.session_state.lang]['nav_im'], use_container_width=True, key="side_nav_im"):
            st.session_state.menu_choice = "IMARKET"
            st.rerun()
            
        if st.button(L_MAP[st.session_state.lang]['nav_bp'], use_container_width=True, key="side_nav_bp"):
            st.session_state.menu_choice = "BAC_PRO"
            st.session_state.bac_menu_choice = None  
            st.rerun()

        if st.button(L_MAP[st.session_state.lang]['nav_gw'], use_container_width=True, key="side_nav_gw"):
            st.session_state.menu_choice = "BOOK"
            st.rerun()


# --- D. 样式注入 ---
    st.markdown("""
    <style>
    /* 1. 增加组件间的垂直间距 */
    [data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap: 0.6rem !important; }

    /* 2. 按钮样式保持，但确保高度不塌陷 */
    [data-testid="stSidebar"] button {
        height: 32px !important; min-height: 32px !important;
        padding: 0px !important; font-size: 13px !important;
    }
    
    /* 3. 新增：强制给侧边栏垂直块增加底部内边距，防止内容紧贴底部 */
    [data-testid="stSidebar"] .stVerticalBlockBorderWrapper > div {
        padding-bottom: 20px;
    }
    </style>""", unsafe_allow_html=True)
    # 💡 改动点：删掉原来的 flex-grow div，改用下面这两行
    st.sidebar.write("")      # 增加一个空行
    st.sidebar.divider()    # 增加一条物理分割线，强制切断上方内容
    
    if st.session_state.menu_choice != "PORTAL":
        #st.divider()
        if st.button(f"🏠 {L_MAP[st.session_state.lang]['back']}", use_container_width=True, key="fixed_home_btn"):
            st.session_state.menu_choice = "PORTAL"
            st.rerun()

    #st.divider()
    
    sig_path = os.path.join(CURRENT_DIR, "assets", "J Signature.png") 
    sig_b64 = get_base64_img(sig_path)
    if sig_b64:
        st.markdown(f"""
            <div style="display: flex; align-items: center; gap: 0px; font-size: 0.85rem; color: #1E90FF; font-family: sans-serif; font-weight: 500; margin-bottom: 8px;">
                <span style="white-space: nowrap; margin-top: 2px;">👨‍💻 Code & Design: &nbsp;&nbsp;&nbsp;</span>
                <img src="data:image/png;base64,{sig_b64}" style="height: 30px; filter: brightness(1.2) contrast(1.2); margin-left: -10px;">
            </div>""", unsafe_allow_html=True)

    st.markdown("<p style='font-size: 0.7rem; color: #555; margin-top: 5px; margin-bottom: 0px;'>👑 Powered by Gemini AI & OpenAI</p>", unsafe_allow_html=True)
    st.divider()
    # 1. 改为 1:1 平分空间
    col_bal, col_exit = st.columns([1, 1]) 

    # --- 建议修改的代码块 ---
    with col_bal:
            display_balance = "N/A"
            # 动态获取当前用户名
            current_uid = st.session_state.get('auth_user', 'J').upper()
            user_map = {"J": "J", "A": "A", "D": "D"}
            display_name = user_map.get(current_uid, current_uid)
            
            # 定义双语标签
            bal_label = "资金余额" if st.session_state.lang == "CN" else "Balance"
            
            try:
                from core.db_adapter import RedisAdapter
                
                if 'record_adapter' not in st.session_state:
                    record_url = st.secrets["UNIFIED_ACCOUNT_SYSTEM"]["REDIS_URL"]
                    st.session_state.record_adapter = RedisAdapter(record_url)
                
                adapter = st.session_state.record_adapter
                # 从 Redis 获取实时余额
                val = adapter.client.hget(f"u:info:{current_uid}", "balance")
                
                if val is not None:
                    display_balance = f"${float(val):,.0f}"
                else:
                    display_balance = "$0"
                    
            except Exception as e:
                print(f"❌ [MAIN] Balance Sync Error: {e}")
                display_balance = "CONN_ERR"

            # 渲染为： 用户名 Balance: $余额
            st.markdown(f"""
                <p style="font-size: 12px; margin: 0; line-height: 32px;">
                    <span style="color: #555;"></span><span style="color: #BBB; font-weight: 600;">{current_uid}</span>
                    <span style="color: #00FFAA; margin-left: 10px; font-family: monospace;">{display_balance}</span>
                </p>
            """, unsafe_allow_html=True)
        
    with col_exit:
        # 2. 显式开启 use_container_width，确保按钮撑满 50% 的列宽
        if st.button(L_MAP[st.session_state.lang]['exit'], key="mini_exit_link", use_container_width=True):
            st.session_state.auth_user = None
            st.session_state.menu_choice = "PORTAL"
            st.rerun()
    
# --- 5. 主路由分发 ---
if st.session_state.menu_choice == "PORTAL":
    st.markdown(f"<h2 style='text-align:center; color:#d4af37;'>{L_MAP[st.session_state.lang]['welcome']}</h2>", unsafe_allow_html=True)
    st.write("---")
    c1, c2, c3 = st.columns(3)
    if c1.button("iMarket Pro", use_container_width=True, key="p_im"):
        st.session_state.menu_choice = "IMARKET"; st.rerun()
    if c2.button("BAC_PRO Engine", use_container_width=True, key="p_bp"):
        st.session_state.menu_choice = "BAC_PRO"
        st.session_state.bac_menu_choice = None # 确保进入介绍页
        st.rerun()

    if c3.button("The Great Way", use_container_width=True, key="p_gw"):
        st.session_state.menu_choice = "BOOK"; st.rerun()
    st.divider()
    
    try:
        from modules.tab_main_launcher import render_launcher_home
        render_launcher_home(st.session_state.lang)
    except Exception:
        st.info(L_MAP[st.session_state.lang]['select'])

elif st.session_state.menu_choice == "IMARKET":
    m = load_tab_module("iMarket", "tab_imarket.py")
    
    # --- 核心修复：将 iMarket 侧边栏内容发送到预留插槽 ---
    if hasattr(m, 'render_imarket_sidebar'):
        with sub_sidebar_slot:
            m.render_imarket_sidebar(st.session_state.lang)
    
    # 渲染主页面
    m.render_imarket_tab(st.session_state.lang)

elif st.session_state.menu_choice == "BAC_PRO":
    # 统一使用动态加载器，确保 sys.path 自动处理好 BAC_PRO 内部的引用
    m_bp = load_tab_module("BAC_PRO", "tab_bac_pro.py")
    
    # 1. 渲染侧边栏插槽 (始终保持显示，以便随时切换子功能)
    if hasattr(m_bp, 'render_bac_pro_sidebar'):
        with sub_sidebar_slot:
            m_bp.render_bac_pro_sidebar(st.session_state.lang)
    
    # 获取当前的子菜单选择
    cur_bac_choice = st.session_state.get('bac_menu_choice')
    
    # 2. 核心路由逻辑分发
    if cur_bac_choice is None:
        # 情况 A: 处于过渡期/介绍页
        m_bp.render_bac_pro_tab(st.session_state.lang)
    
    elif cur_bac_choice == t("nav_practice", st.session_state.lang):
        # 情况 B: 练习模式
        # 💡 检查点：确保文件名是 tab_practice_J.py 还是 tab_practice_JStudio.py
        m_prac = load_tab_module("BAC_PRO", "tab_practice_JStudio.py") 
        m_prac.render_practice_tab(st.session_state.lang)
        
    elif cur_bac_choice == t("nav_ai", st.session_state.lang):
        # 情况 C: AI 视觉模式
        m_ai = load_tab_module("BAC_PRO", "tab_ai_vision.py")
        m_ai.render_ai_vision_tab(st.session_state.lang)
    
elif st.session_state.menu_choice == "BOOK":
    st.title("The Great Way, Made Simple")
    st.info("Philosophical Forum under development.")

