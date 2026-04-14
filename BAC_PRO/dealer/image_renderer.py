#dealer/image_renderer.py 
import streamlit as st
import os

def render_casino_table(last_outcome, lang="CN"):
    """渲染专业赌场牌桌：包含第三张牌横放和赢家光晕"""
    if not last_outcome:
        return

    # 路径配置
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    IMG_DIR = "app/PIC/CARDS_PNG"
    suit_map = {"Hearts": "H", "Spades": "S", "Diamonds": "D", "Clubs": "C"}
    
    def get_cards_html(card_list, is_winner):
        html = ""
        win_class = "winner-glow" if is_winner else ""
        for idx, card_tuple in enumerate(card_list):
            # 解析卡片文件名: ('4 of Hearts',) -> 4H.png
            c_str = str(card_tuple).replace("('", "").replace("')", "").split(' of ')
            if len(c_str) == 2:
                filename = f"{c_str[0]}{suit_map.get(c_str[1], '')}.png"
                img_path = os.path.join(IMG_DIR, filename)
                
                # 🔄 物理相位：第三张牌 (index 2) 旋转90度
                rotate_class = "third-card-rotate" if idx == 2 else ""
                html += f'<img src="{img_path}" class="casino-card {win_class} {rotate_class}">'
        return html

    p_cards = get_cards_html(last_outcome.player_cards, last_outcome.winner == 'P')
    b_cards = get_cards_html(last_outcome.banker_cards, last_outcome.winner == 'B')

    # CSS 注入 (缩小版渲染优化)
    st.markdown("""
    <style>
        .casino-card { width: 55px; height: auto; margin: 2px; border-radius: 4px; display: inline-block; }
        .third-card-rotate { transform: rotate(90deg); margin-left: -12px; margin-right: -12px; position: relative; top: 6px; }
        .winner-glow { border: 2px solid #FFD700; box-shadow: 0 0 10px #FFD700; }
        .table-container { display: flex; justify-content: space-around; background: #072b11; padding: 15px; border-radius: 10px; border: 2px solid #333; }
        .zone-box { text-align: center; flex: 1; }
    </style>
    """, unsafe_allow_html=True)

    # 渲染 HTML
    st.markdown(f"""
        <div class="table-container">
            <div class="zone-box">
                <div style="color:#1E90FF; font-weight:bold;">PLAYER {last_outcome.player_score}</div>
                <div>{p_cards}</div>
            </div>
            <div class="zone-box">
                <div style="color:#FF4500; font-weight:bold;">BANKER {last_outcome.banker_score}</div>
                <div>{b_cards}</div>
            </div>
        </div>
    """, unsafe_allow_html=True)