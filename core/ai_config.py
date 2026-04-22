import streamlit as st
import google.generativeai as genai
import os

class AIConfigManager:
    """
    JStudio AI KPI 统一管理中心
    实现功能：
    1. 自动读取并清洗 API Key (兼容多种命名)
    2. 统一管理模型优先级 (锁定 2.5 付费版)
    3. 全局一致性配置分发
    """
    
    # 统一模型优先级列表
    MODEL_CANDIDATES = [
        'gemini-2.5-flash',        # 优先级 1：付费最新测试版
        'gemini-1.5-flash-latest', # 优先级 2
        'gemini-1.5-flash-002',    # 优先级 3
        'gemini-1.5-flash'         # 优先级 4
    ]

    @classmethod
    def configure_engine(cls):
        """
        供各功能模块调用：一键配置并返回模型名称
        """
        # 从 Secrets 获取 Key (增加容错)
        raw_key = st.secrets.get("GOOGLE_API_KEY") or st.secrets.get("GEMINI_API_KEY")
        
        if not raw_key:
            return None, "ERROR: GOOGLE_API_KEY not found"
            
        try:
            # 1. 强力清洗
            api_key_clean = str(raw_key).strip().replace("\n", "").replace("\r", "")
            genai.configure(api_key=api_key_clean)
            
            # 2. 动态检测当前 Key 权限内最合适的模型
            # 如果是付费 Key，这里会成功匹配到 gemini-2.5-flash
            final_model = cls.MODEL_CANDIDATES[0] 
            try:
                available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
                for cand in cls.MODEL_CANDIDATES:
                    if any(cand in am for am in available_models):
                        final_model = cand
                        break
            except:
                pass # 获取列表失败则直接使用首选 2.5
                
            return final_model, "SUCCESS"
            
        except Exception as e:
            return None, f"AI_CONFIG_ERROR: {str(e)}"

# 实例化管理器
ai_manager = AIConfigManager()
