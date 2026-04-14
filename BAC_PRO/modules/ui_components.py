import streamlit as st
import os
import base64

def get_base64_img(relative_path):
    """🧱 路径兼容逻辑：自动寻找项目根目录并转码图片"""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    full_path = os.path.join(base_dir, relative_path)
    if os.path.exists(full_path):
        with open(full_path, "rb") as f:
            return f"data:image/png;base64,{base64.b64encode(f.read()).decode()}"
    return ""

def render_casino_table(last_outcome, lang="CN"):
    """🃏 牌桌渲染：比分暴力抓取 + 物理旋转 90 度"""
    ps, bs = 0, 0
    winner = 'T'
    p_cards, b_cards = [], []
    
    if last_outcome:
        winner = getattr(last_outcome, 'winner', 'T')
        p_cards = getattr(last_outcome, 'player_cards', [])
        b_cards = getattr(last_outcome, 'banker_cards', [])
        # 🚨 暴力扫描属性获取比分，确保不显示为 0
        try:
            for a in dir(last_outcome):
                val = getattr(last_outcome, a)
                if not isinstance(val, (int, float)): continue
                name = a.lower()
                if ('p_' in name or 'player' in name) and any(x in name for x in ['score', 'point', 'val']):
                    ps = int(val)
                if ('b_' in name or 'banker' in name) and any(x in name for x in ['score', 'point', 'val']):
                    bs = int(val)
        except: pass

    # 颜色与文字逻辑
    if not last_outcome:
        banner_color = "#555"
        res_text = "等待发牌..." if lang == "CN" else "WAITING FOR DEAL..."
    else:
        banner_color = "#1E90FF" if winner == 'P' else "#FF4500" if winner == 'B' else "#32CD32"
        win_map = {"P": "闲赢", "B": "庄赢", "T": "和局"} if lang == "CN" else {"P": "PLAYER WIN", "B": "BANKER WIN", "T": "TIE"}
        res_text = f"{'结果: ' if lang=='CN' else 'RESULT: '}{win_map.get(winner, '')}"

    st.markdown(f"""
        <style>
            .result-banner {{ text-align: center; background: #1a1a1a; color: {banner_color}; padding: 12px; font-weight: bold; border-radius: 12px 12px 0 0; border: 1px solid #333; font-size: 1.3rem; min-height: 55px; }}
            .table-container {{ display: flex; justify-content: space-around; background: #072b11; padding: 25px 10px; border-radius: 0 0 12px 12px; border: 1px solid #333; min-height: 220px; }}
            .casino-card {{ width: 60px; height: 90px; margin: 3px; border-radius: 4px; display: inline-block; vertical-align: middle; box-shadow: 2px 2px 8px rgba(0,0,0,0.5); background: rgba(255,255,255,0.05); }}
            /* 第三张牌物理旋转 90 度 */
            .third-card-rotate {{ transform: rotate(90deg); margin: 0 -12px; position: relative; top: 8px; }}
            .winner-glow {{ border: 2px solid {banner_color}; box-shadow: 0 0 15px {banner_color}; }}
        </style>
    """, unsafe_allow_html=True)

    def get_cards_html(card_list, is_side_winner):
        if not card_list: return '<div class="casino-card"></div><div class="casino-card"></div>'
        html = ""
        IMG_DIR = "app/PIC/CARDS_PNG"
        suit_map = {"Hearts": "H", "Spades": "S", "Diamonds": "D", "Clubs": "C"}
        for idx, card_tuple in enumerate(card_list):
            c_str = str(card_tuple).replace("('", "").replace("')", "").replace("'", "").split(' of ')
            if len(c_str) == 2:
                filename = f"{c_str[0]}{suit_map.get(c_str[1], '')}.png"
                b64 = get_base64_img(f"{IMG_DIR}/{filename}")
                rotate = "third-card-rotate" if idx == 2 else ""
                win_class = "winner-glow" if is_side_winner else ""
                if b64: html += f'<img src="{b64}" class="casino-card {win_class} {rotate}">'
        return html

    st.markdown(f'<div class="result-banner">{res_text} (P:{ps} vs B:{bs})</div>', unsafe_allow_html=True)
    st.markdown(f"""
        <div class="table-container">
            <div style="text-align:center; flex:1;">
                <div style="color:#1E90FF; font-weight:bold; margin-bottom:12px;">PLAYER</div>
                <div>{get_cards_html(p_cards, winner == 'P')}</div>
            </div>
            <div style="text-align:center; flex:1;">
                <div style="color:#FF4500; font-weight:bold; margin-bottom:12px;">BANKER</div>
                <div>{get_cards_html(b_cards, winner == 'B')}</div>
            </div>
        </div>
    """, unsafe_allow_html=True)

import streamlit as st

def render_bias_panel(sig, lang="CN"):
    """📊 序列偏值分析：中英文双语版"""
    if not sig:
        sig = {
            "mode": "SBI", 
            "side": "Neutral", 
            "p_val": "0.00%", 
            "b_val": "0.00%", 
            "detail": "Waiting..." if lang=="EN" else "等待数据..."
        }
    
    # 1. 判定颜色与标签逻辑
    is_dict = (sig.get("mode") == "DICT")
    color = "#FFD700" if is_dict else "#32CD32"
    
    # 新增的 t_title 变量
 
    
    # 标签 (Tag) 翻译
    if is_dict:
        tag = "DICT HIT" if lang == "EN" else "指纹匹配"
    else:
        tag = "REAL-TIME" if lang == "EN" else "实时算力"
    
    # 2. 标题翻译
    side_val = sig.get("side", "Neutral")
    side_map = {"Neutral": "中立", "Banker": "庄", "Player": "闲"}
    side_label = side_val if lang == "EN" else side_map.get(side_val, side_val)
    
    if is_dict:
        title = f"🎯 RANK BIAS HIT: {side_label}" if lang == "EN" else f"🎯 指纹偏差命中: {side_label}"
    else:
        title = f"📊 RANK BIAS: {side_label}" if lang == "EN" else f"📊 序列偏差分析: {side_label}"
    
    # 3. 准备数值
    p_val = sig.get("p_val", "0.00%")
    b_val = sig.get("b_val", "0.00%")
    detail = sig.get("detail", "")
    
    t_player = "PLAYER" if lang == "EN" else "闲 (P)"
    t_banker = "BANKER" if lang == "EN" else "庄 (B)"

    # 4. 渲染 HTML (已加入 t_title 占位符)
    st.markdown(f"""
        <div style="padding: 15px; border: 2px solid {color}; border-radius: 8px; background-color: rgba(0,0,0,0.2); position: relative; min-height: 160px;">
            <div style="position: absolute; top: 8px; right: 10px; font-size: 0.65rem; color: {color}; border: 1px solid {color}; padding: 1px 6px; border-radius: 4px; font-weight: bold; letter-spacing: 0.5px;">
                {tag}
            </div>
            


            <div style="font-weight: bold; color: {color}; font-size: 1.1rem; margin-bottom: 5px;">
                {title}
            </div>
            
            <div style="font-size: 0.8rem; color: #888; margin-bottom: 12px; height: 1.2rem; overflow: hidden;">
                {detail}
            </div>
            
            <div style="font-family: 'Courier New', monospace; font-size: 1.2rem; line-height: 1.8;">
                <span style="color: #1E90FF; font-weight: bold;">● {t_player}: {p_val}</span> <br>
                <span style="color: #FF4500; font-weight: bold;">● {t_banker}: {b_val}</span>
            </div>
        </div>
    """, unsafe_allow_html=True)
    
# modules/ui_components.py

def render_snapshot_ai(fp_advice, lang='CN'):
    # 1. 定义多语言字典
    texts = {
        'CN': {
            'title': '🎯 AI 策略引擎',
            'matching': '🧬 正在匹配指纹库...',
            'edge': '优势边际',
            'action': '建议动作',
            'ev_labels': {
                '斩 (Cut)': '斩 (Cut)',
                '跟 (Cont)': '跟 (Cont)'
            }
        },
        'EN': {
            'title': '🎯 AI STRATEGY ENGINE',
            'matching': '🧬 Matching Fingerprint...',
            'edge': 'Edge Margin',
            'action': 'Action',
            'ev_labels': {
                '斩 (Cut)': 'Cut',
                '跟 (Cont)': 'Cont'
            }
        }
    }
    t = texts[lang]

    # 2. 渲染外框（使用 border=True 确保与左侧对称）
    with st.container(border=True):
        st.markdown(f"**{t['title']}**")
        
        if not fp_advice.get('match'):
            st.info(t['matching'])
            # 保持高度占位，防止闪烁
            st.caption(f"Fingerprint: {fp_advice.get('fp_id', 'N/A')[:16]}...")
            return

        # 获取数据
        action = fp_advice.get('action', 'WAIT')
        edge = fp_advice.get('edge', 0.0)
        ev_info = fp_advice.get('ev_info', {}) # 格式: {'斩 (Cut)': 0.0067, '跟 (Cont)': -0.0315}

        # 显示 Key (与左侧 RANK BIAS 对齐)
        st.code(f"Key: {fp_advice.get('fp_id')[:32]}...", language="text")

        # 核心指标：动作与 Edge
        col1, col2 = st.columns(2)
        with col1:
            st.caption(t['action'])
            color = "#00FF00" if edge > 0 else "#FF4B4B"
            st.markdown(f"<h2 style='color:{color}; margin:0;'>{action}</h2>", unsafe_allow_html=True)
        with col2:
            # 统一使用 USD 计价逻辑显示优势
            st.metric(label=t['edge'], value=f"{edge:.2%}")

        st.divider()

        # 3. 分语言显示 EV 详情
        st.caption("Detailed EV" if lang=='EN' else "详细预期值")
        ev_cols = st.columns(len(ev_info))
        
        # 遍历原始数据中的 Key，通过字典转换标签
        for i, (raw_key, val) in enumerate(ev_info.items()):
            display_label = t['ev_labels'].get(raw_key, raw_key)
            with ev_cols[i]:
                st.write(f"{display_label}:")
                # 正值加粗绿色，负值红色
                v_color = "green" if val >= 0 else "#FF4B4B"
                st.markdown(f"<code style='color:{v_color};'>{val:.4f}</code>", unsafe_allow_html=True)
