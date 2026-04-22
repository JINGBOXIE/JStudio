import streamlit as st
import os
import sys
import re
import google.generativeai as genai
from PIL import Image
import importlib

# --- 1. 路径注入 (确保从 JStudio/BAC_PRO/tabs/ 向上跳两级能找到 core) ---
CURRENT_FILE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(CURRENT_FILE_DIR, "../../"))

# 强制刷新路径优先级，处理 iCloud 路径识别问题
sys.path = [p for p in sys.path if "JStudio" not in p]
sys.path.insert(0, ROOT_DIR)

# --- 2. 核心模块导入 ---
try:
    if 'core' in sys.modules:
        del sys.modules['core']
    
    from core.ai_config import ai_manager
    from core.constants import AI_VISION_ROLE_PROMPT
    from core.snapshot_engine import get_fp_components
    from core.db_adapter import RedisAdapter, generate_fp_hash
except ImportError as e:
    st.error(f"核心模块导入失败: {e}")
    st.code(f"当前搜寻根目录: {ROOT_DIR}\n目录内容: {os.listdir(ROOT_DIR) if os.path.exists(ROOT_DIR) else '路径不存在'}")

# --- 3. 核心调用函数 (已修复逻辑重叠与清洗逻辑) ---
def call_vision_ai(image_file, prompt_text):
    """
    调用 Gemini 2.5 视觉引擎并执行深度结果清洗
    """
    model_name, status = ai_manager.configure_engine()
    
    if status != "SUCCESS":
        return f"AI Engine Error: {status}"
    
    try:
        model = genai.GenerativeModel(model_name)
        
        # 确保图片指针在起始位置，防止 Streamlit 多次读取导致空流
        if hasattr(image_file, 'seek'):
            image_file.seek(0)
            
        img = Image.open(image_file)
        
        # 调用 AI 引擎
        response = model.generate_content([prompt_text, img])
        
        if response and response.text:
            clean_text = response.text.strip()
            
            # 1. 循环移除 Markdown 包裹标记 (如 ```json 或 ```text)
            while clean_text.startswith("```") or clean_text.endswith("```"):
                clean_text = clean_text.strip("`").strip()
            
            # 2. 移除模型可能自带的 "text" 字符串
            if clean_text.lower().startswith("text"):
                clean_text = clean_text[4:].strip()
            
            # 3. 使用正则提取所有的 B/P (解决 "AI found no valid B/P" 问题的核心)
            # 这样无论 AI 返回 "B, P, B" 还是 "BPB"，都能正确识别
            detected_seq = re.findall(r'[BP]', clean_text.upper())
            return ",".join(detected_seq) if detected_seq else "ERROR: No valid B/P found"
            
        return "ERROR: AI returned an empty response"
            
    except Exception as e:
        return f"AI Logic Error: {str(e)}"

def render_ai_vision_tab(lang):
    """
    AI 视觉决策中心：整合视觉识别、指纹计算与 Redis 实时决策
    """
    is_cn = lang == "CN"
    
    # 1. 样式与 UI 配置 (统一管理，避免重定义冲突)
    STYLE_CARD = "padding: 20px; border: 1px solid #333; border-radius: 12px; background: #0d0d0d; margin-bottom: 20px;"
    STYLE_DECISION = "padding: 20px; border: 1px solid #333; border-radius: 12px; background: #0d0d0d; min-height: 280px;"
    STYLE_HEADER = "display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; color: #00FFAA; font-weight: bold;"
    
    ui_text = {
        "header": "🔍 AI FINGERPRINT🫆 MATCH" if not is_cn else "🔍 AI 指纹🫆特征比对 ",
        "sub_header": "📸 Capture & Recognize" if not is_cn else "📸 图像捕捉与识别",
        "uploader_label": "Upload Big Road Screenshot" if not is_cn else "上传大路截图",
        "camera_label": "Live Camera Scan" if not is_cn else "现场拍照扫描",
        "btn_run": "🚀 Run AI Deep Scan" if not is_cn else "🚀 启动 AI 深度扫描",
        "status_ai": "AI analyzing image..." if not is_cn else "AI 正在分析图像...",
        "toast_sync": "Sequence Synchronized!" if not is_cn else "大路序列已同步！",
        "info_wait": "💡 Waiting for AI identification." if not is_cn else "💡 请先上传图片或拍照，识别后将展示分析结果。",
        "expander_raw": "📄 View Raw Sequence" if not is_cn else "📄 查看已提取的原始序列",
    }

    lang_map = {
        "title": "🔍 AI FINGERPRINT SCANNING" if not is_cn else "🔍 AI 指纹扫描决策",
        "waiting": "Waiting for AI Data..." if not is_cn else "等待 AI 识别数据...",
        "action_label": "Best Action" if not is_cn else "最优决策",
        "edge_label": "Edge Advantage" if not is_cn else "优势概率",
        "insufficient": "DEPTH INSUFFICIENT" if not is_cn else "序列深度不足",
        "miss": "FINGERPRINT MISS" if not is_cn else "未匹配到有效指纹",
    }

    st.header(ui_text["header"])

    # --- 第一部分：图像输入与视觉识别 ---
    st.markdown(f"### {ui_text['sub_header']}")
    col_input1, col_input2 = st.columns(2)
    with col_input1:
        uploaded_file = st.file_uploader(ui_text["uploader_label"], type=['png', 'jpg', 'jpeg'])
    with col_input2:
        camera_file = st.camera_input(ui_text["camera_label"])

    input_image = uploaded_file or camera_file

    if input_image:
        st.image(input_image, caption="Input Source", width="stretch")
        #st.image(input_image, caption="Input Source", use_container_width=True)
        if st.button(ui_text["btn_run"], type="primary", width="stretch") :
        #if st.button(ui_text["btn_run"], type="primary", use_container_width=True):
            # ... 在识别成功后的代码块中修改 ...
            with st.status(ui_text["status_ai"]) as status:
                ai_result = call_vision_ai(input_image, AI_VISION_ROLE_PROMPT)
                
                if "ERROR" in ai_result:
                    st.error(f"AI Engine Error: {ai_result}")
                else:
                    # --- 优化后的提取逻辑 ---
                    # 1. 强制转大写
                    raw_content = ai_result.upper()
                    # 2. 使用正则匹配所有的 B 或 P (无视空格、逗号或换行)
                    detected_seq = re.findall(r'[BP]', raw_content)
                    
                    if not detected_seq:
                        st.warning(f"AI Response: {ai_result}") # 打印原文看看 AI 到底说了什么
                        st.warning("AI found no valid B/P sequence.")
                    else:
                        # 同步到全局状态
                        st.session_state.clean_results = detected_seq
                        if 'results' in st.session_state:
                            st.session_state.results = detected_seq
                        
                        status.update(label="✅ Success", state="complete")
                        st.toast(ui_text["toast_sync"])

    st.divider()

    # --- 第二部分：核心逻辑处理与 Redis 查询 ---
    # 引入必要的工具


    # 初始化 Redis (单例模式)
    if 'redis_adapter' not in st.session_state:
        try:
            use_cloud = st.secrets.get("USE_CLOUD_REDIS", False)
            target_url = st.secrets["UPSTASH_REDIS_URL"] if use_cloud else st.secrets["LOCAL_REDIS_URL"]
            st.session_state.redis_adapter = RedisAdapter(target_url)
        except Exception as e:
            st.error(f"Redis Connection Error: {e}")
            return

    clean_seq = st.session_state.get('clean_results', [])
    h_min = st.session_state.get('hist_min', 3)  # 实时联动侧边栏参数
    fp_advice = {"match": False, "status": "WAITING", "fp_id": ""}
    state_hash = None

    # 执行 V8 核心算法逻辑
    # 数据链条演示
    clean_seq = st.session_state.get('clean_results', [])
    h_min = st.session_state.get('hist_min', 3)
    
    if clean_seq:
        components = get_fp_components(clean_seq, h_min=h_min)
        state_hash = generate_fp_hash(*components)
        
        # 检查 redis_adapter 是否在 session_state 中
        if "redis_adapter" in st.session_state:
            decision_data = st.session_state.redis_adapter.get_state_decision(state_hash)
            
            if decision_data:
                # 更新 UI 逻辑...
                pass
        else:
            st.error("Redis Adapter not initialized. Please check connection.")

    

    # --- 第三部分：双栏 UI 渲染 ---
    col_vis, col_dec = st.columns([1, 1.2])

    with col_vis:
        st.markdown(f"### " + ("🔍 识别预览" if is_cn else "🔍 RECOGNITION"))
        if not clean_seq:
            st.info(ui_text["info_wait"])
        else:
            # 动态生成最后 8 个点的彩色预览
            nodes_html = "".join([f'<span style="color: {"#FF4B4B" if n == "B" else "#1E90FF"}; margin: 0 4px;">{n}</span>' for n in clean_seq[-8:]])
            st.markdown(f"""
                <div style="{STYLE_CARD}">
                    <div style="font-size: 0.75rem; color: #1E90FF; font-family: monospace; word-break: break-all;">ID: {state_hash or 'N/A'}</div>
                    <div style="margin-top: 20px; text-align: center;">
                        <div style="font-size: 0.8rem; color: #888; margin-bottom: 8px;">SEQUENCE SNAPSHOT</div>
                        <div style="font-size: 1.6rem; font-weight: bold;">{nodes_html}</div>
                    </div>
                </div>
            """, unsafe_allow_html=True)
            with st.expander(ui_text["expander_raw"]):
                st.write(", ".join(clean_seq))

    with col_dec:
        st.markdown(f"### " + ("🔍 决策分析" if is_cn else "🔍 DECISION ANALYSIS"))
        
        # 1. 重新声明/抓取必要变量，确保在线环境作用域正确
        v_clean_seq = st.session_state.get('clean_results', [])
        v_h_min = st.session_state.get('hist_min', 3)
        v_adapter = st.session_state.get('redis_adapter') # 确保获取到 adapter
        
        v_fp_advice = {"match": False, "status": "WAITING", "fp_id": ""}
        
        # 2. 执行逻辑比对
        if v_clean_seq:
            v_components = get_fp_components(v_clean_seq, h_min=v_h_min)
            v_state_hash = generate_fp_hash(*v_components)
            
            if v_adapter:
                v_decision = v_adapter.get_state_decision(v_state_hash)
                if v_decision:
                    v_fp_advice.update({
                        "match": True, 
                        "action": v_decision["action"], 
                        "edge": v_decision["edge"], 
                        "ev_cut": v_decision["ev_cut"], 
                        "ev_cont": v_decision["ev_cont"], 
                        "fp_id": v_state_hash
                    })
                else:
                    v_fp_advice.update({"status": lang_map["miss"], "fp_id": v_state_hash})
            else:
                # 针对在线环境的兜底报错
                v_fp_advice.update({"status": "REDIS OFFLINE", "fp_id": "CONNECTION ERROR"})

        # 3. 完整 UI 渲染 (补全缺失的 EV 显示)
        html = f'<div style="{STYLE_DECISION}">'
        html += f'<div style="{STYLE_HEADER}"><span>{lang_map["title"]}</span><span style="font-size: 0.6rem; color: #555; background: rgba(0,0,0,0.2); padding: 2px 6px; border-radius: 4px;">V8-PRO</span></div>'
        
        fid_display = v_fp_advice.get("fp_id", "") if v_fp_advice.get("fp_id") else "READY"
        html += f'<div style="font-family: monospace; font-size: 0.65rem; color: #1E90FF; background: rgba(0,0,0,0.3); padding: 5px 10px; border-radius: 4px; margin-bottom: 12px; overflow: hidden; text-overflow: ellipsis;">🫆 {fid_display}</div>'

        if not v_fp_advice.get('match') and v_fp_advice.get('status') == 'WAITING':
            html += f'<div style="color:#666; text-align:center; padding-top: 80px;">{lang_map["waiting"]}</div>'
        
        elif v_fp_advice.get('match'):
            # --- 补全 col_right 的完整显示逻辑 ---
            act = v_fp_advice["action"]
            edge_pct = f'{v_fp_advice["edge"]:+.2%}'
            e_cut_pct, e_cont_pct = f'{v_fp_advice["ev_cut"]*100:+.2f}%', f'{v_fp_advice["ev_cont"]*100:+.2f}%'

            html += f'''
                <div>
                    <div style="text-align:center;margin-bottom:15px;">
                        <div style="font-size:0.7rem;color:#888;">{lang_map["action_label"]}</div>
                        <div style="font-size:2.2rem;font-weight:800;color:#00FFAA;">{act}</div>
                    </div>
                    <div style="display:flex;gap:10px;margin-bottom:12px;">
                        <div style="flex:1;background:rgba(255,255,255,0.05);padding:8px;border-radius:8px;text-align:center;border:1px solid #444;">
                            <div style="font-size:0.6rem;color:#aaa;">EV (CUT)</div><div style="font-size:1.0rem;font-weight:bold;color:#fff;">{e_cut_pct}</div>
                        </div>
                        <div style="flex:1;background:rgba(255,255,255,0.05);padding:8px;border-radius:8px;text-align:center;border:1px solid #444;">
                            <div style="font-size:0.6rem;color:#aaa;">EV (CONT)</div><div style="font-size:1.0rem;font-weight:bold;color:#fff;">{e_cont_pct}</div>
                        </div>
                    </div>
                    <div style="text-align:center;background:rgba(0,255,170,0.1);padding:5px;border-radius:20px;border:1px solid #00FFAA33;">
                        <span style="font-size:0.8rem;color:#00FFAA;font-weight:bold;">{lang_map["edge_label"]}: {edge_pct}</span>
                    </div>
                </div>
            '''
        else:
            html += f'<div style="margin-top: 60px; text-align:center;"><div style="color:#FF4444; font-size: 0.9rem; font-weight:bold;">⚠️ {v_fp_advice["status"]}</div></div>'

        html += '</div>'
        st.markdown(html, unsafe_allow_html=True)
