#core/engine_source.py
# -*- coding: utf-8 -*-
import os
import sys
import hashlib
from typing import List, Dict

# 确保导入同级目录下的精算模型
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

from sbi_full_model import compute_sbi_ev_from_counts

class AnalysisEngine:
    """
    BACC-INTELLI 核心集成引擎 (NEXUS)
    整合左核 (Math/Rank) 与 右核 (Pattern/Snap)
    """
    def __init__(self, decks=8):
        self.decks = decks

    # --- 右核：图形特征提取与哈希匹配 (保留并增强旧逻辑) ---
    def get_snapshot_advice(self, results: List[str]) -> str:
        """提取最近 10 手特征并生成 StateID"""
        if not results:
            return "Waiting for data..."
            
        # 1. 提取最近 10 手特征
        pattern = "".join(results[-10:])
        
        # 2. 生成特征哈希 (StateID) - 用于逻辑定位
        state_id = hashlib.md5(pattern.encode()).hexdigest()[:8].upper()
        
        # 3. 基础势能逻辑判定
        if len(results) >= 3 and results[-3:] == ['B', 'B', 'B']:
            advice = f"[{state_id}]: 庄势连贯，图形库匹配：建议顺势。"
        elif "BPBP" in pattern:
            advice = f"[{state_id}]: 发现单跳波段，倾向于维持跳位。"
        else:
            advice = f"[{state_id}]: 图形处于平衡区，特征不显著。"
            
        return advice

    # --- 左核：数学精算偏移 (基于 SBI_FULL_MODEL) ---

# --- core/engine_source.py ---

    def get_rank_bias(self, rank_counts: Dict[int, int]) -> Dict:
        # 1. 调用 V7 整合版接口
        # 注意：rank_counts 包含 0-9，但 model 内部循环 range(1,10) 会自动忽略 0
        results = compute_sbi_ev_from_counts(self.decks, rank_counts)
        
        bias_label = results.get("bias_label", "Neutral")
        
        # 2. 从 results 提取实时 EV (由 sbi_full_model 计算得出)
        ev_p = results.get("ev_p", 0.0)
        ev_b = results.get("ev_b_comm", 0.0)
        
        # 💡 返回给 UI 的格式化字符串
        return {
            "label": bias_label,
            "detail": f"{bias_label} (P:{ev_p*100:+.3f}% / B:{ev_b*100:+.3f}%)",
            "raw": results
        }


# 单例实例化，供 streamlit_app.py 调用
engine = AnalysisEngine(decks=8)