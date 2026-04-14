import streamlit as st

def get_big_road_matrix(results):
    """
    核心坐标算法：兼容处理 字符串列表 或 字典列表(styled_results)
    """
    if not results: return {}, 0
    matrix = {}
    max_x, curr_x, curr_y = 0, 0, 0
    last_main_winner = None
    initial_ties = 0
    
    for item in results:
        # 1. 安全提取结果字符
        if isinstance(item, dict):
            r = item.get('v')
        else:
            r = item
            
        if r is None: continue

        # 2. 和局逻辑
        if r == 'T':
            if last_main_winner is None: 
                initial_ties += 1
            else:
                if (curr_x, curr_y) in matrix: 
                    matrix[(curr_x, curr_y)]['ties'] += 1
            continue
            
        # 封装节点数据
        node_data = {'type': r, 'ties': 0}
        if isinstance(item, dict):
            node_data.update(item)

        # 3. 换列与拐弯逻辑
        if last_main_winner is None:
            node_data['ties'] = initial_ties
            matrix[(0, 0)] = node_data
            last_main_winner, curr_x, curr_y = r, 0, 0
        elif r == last_main_winner:
            nx, ny = curr_x, curr_y + 1
            if ny >= 6 or (nx, ny) in matrix: 
                nx, ny = curr_x + 1, curr_y
            matrix[(nx, ny)] = node_data
            curr_x, curr_y = nx, ny
        else:
            sx = 0
            while (sx, 0) in matrix: sx += 1
            curr_x, curr_y, last_main_winner = sx, 0, r
            matrix[(curr_x, curr_y)] = node_data
        
        max_x = max(max_x, curr_x)
    return matrix, max_x

def render_big_road(results, mode="NATURAL"):
    """
    极简微型版渲染器：支持 S/C 决策覆盖显示
    """
    matrix, max_x = get_big_road_matrix(results)
    
    if not matrix:
        return 

    # --- 📐 渲染参数设定 ---
    cell_size = 16  
    dot_size = 13   # 略微增大圆点以容纳字母
    font_size = 8   # 优化字体大小
    tie_size = 8    

    display_cols = max(60, max_x + 2)
    grid_total_width = display_cols * cell_size

    grid_style = (
        f"display: grid; "
        f"grid-template-columns: repeat({display_cols}, {cell_size}px); "
        f"grid-template-rows: repeat(6, {cell_size}px); "
        f"background-color: #fff; "
        f"background-image: "
        f"linear-gradient(#f1f1f1 1px, transparent 1px), "
        f"linear-gradient(90deg, #f1f1f1 1px, transparent 1px); "
        f"background-size: {cell_size}px {cell_size}px; "
        f"width: {grid_total_width}px; "
        f"height: {cell_size * 6}px;"
    )

    html = [
        f'<div id="road-scroll-container" style="width:100%; overflow-x:auto; background:#fafafa; '
        f'padding:5px; border:1px solid #dcdcdc; border-radius:4px; white-space:nowrap;">'
        f'<div style="{grid_style}">'
    ]
    
    for (x, y), item in matrix.items():
        # --- 🚀 核心显示逻辑：决策字符覆盖 ---
        # 默认显示原始结果 (B/P)
        v_orig = item.get('v') if item.get('v') else item.get('type', '')
        if not v_orig: continue
        
        r_text = v_orig
        base_color = "#FF4500" if v_orig == 'B' else "#1E90FF"
        bg_style = "background:white;"
        border_color, text_color = base_color, base_color
        
        # --- 🎯 MARKER 模式增强逻辑 ---
        if mode == "MARKER":
            if item.get('m') == True: 
                # AI 命中：文字替换为 S 或 C，背景设为实心橙色
                r_text = item.get('action', '?') 
                border_color = "#FFA500"
                bg_style = f"background:{border_color};"
                text_color = "white"
            elif item.get('r') == 'win':
                # 历史注单赢：绿色实心
                border_color = "#00FFAA"; bg_style = f"background:{border_color};"; text_color = "white"
            elif item.get('r') == 'loss':
                # 历史注单输：红色实心
                border_color = "#FF4444"; bg_style = f"background:{border_color};"; text_color = "white"
        
        # 和局标记
        tie_tag = (
            f'<div style="position:absolute; top:-2px; right:-2px; background:#32CD32; '
            f'color:white; border-radius:50%; width:{tie_size}px; height:{tie_size}px; '
            f'font-size:6px; line-height:{tie_size}px; text-align:center; '
            f'border:1px solid white; z-index:10;">{item["ties"]}</div>' 
            if item.get('ties', 0) > 0 else ""
        )
        
        cell = (
            f'<div style="grid-column:{x+1}; grid-row:{y+1}; position:relative; '
            f'width:{cell_size}px; height:{cell_size}px; display:flex; align-items:center; justify-content:center;">'
            f'<div style="width:{dot_size}px; height:{dot_size}px; border:1px solid {border_color}; '
            f'border-radius:50%; display:flex; align-items:center; justify-content:center; {bg_style}">'
            f'<b style="color:{text_color}; font-size:{font_size}px; font-family:sans-serif;">{r_text}</b></div>{tie_tag}</div>'
        )
        html.append(cell)
        
    html.append('</div></div>')
    
    # 自动滚动 JS (保持滚动到最右侧)
    html.append(
        '<script>'
        '(function() {'
        '  var el = document.getElementById("road-scroll-container");'
        '  if(el) { setTimeout(function(){ el.scrollLeft = el.scrollWidth; }, 50); }'
        '})();'
        '</script>'
    )
    
    st.markdown("".join(html), unsafe_allow_html=True)