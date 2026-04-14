# modules/i18n.py
# i18n.py
# modules/i18n.py 示例

TRANSLATIONS = {
    "CN": {
        "stat_b": "🔴（庄）      🎲 45.86%",
        "stat_p": "🔵（闲）      🎲 44.62%",
        "stat_t": "和           🎲 9.52%",
        "btn_deal": "发牌",
        "btn_new_shoe": "洗牌",
        "nav_practice": "🧠 策略模拟训练",
        "nav_ai": "⚡ AI 现场决策",
        "nav_knowledge": "💠 BACC-INTELLI-PRO AI 引擎",
        "welcome": "简单与专注",
        "lang_switch": "语言选择 / Language",
        "theoretical": "理论模型 (SBI)",
        "historical": "大数据字典 (DICT)",
        "deal_btn": "🚀 DEAL / 发牌",
        "ai_title": "实时视觉诊断中心",
        "upload_btn": "拍照或上传大路图",
        "start_ai": "开始 AI 智能扫描",
        "diag_report": "大数据诊断报告",
        "neutral": "中性",
        "loading_ai": "AI 正在深度解析大路图...",
        "big_road": "大路演示",
    },
    "EN": {
        "stat_b": "🔴(BANKER)      🎲 45.86%",
        "stat_p": "🔵(PLAYER)      🎲 44.62%",
        "stat_t": "TIE             🎲 9.52%",
        "btn_deal": "DEAL",
        "btn_new_shoe": "NEW SHOE",
        "nav_practice": "🧠 Strategy Drill",
        "nav_ai": "⚡ AI In-Play Vision",
        "nav_knowledge": "💠 BACC-INTELLI-PRO AI ENGINE",
        "welcome": "Simplicity and Focus",
        "lang_switch": "Language",
        "theoretical": "Theoretical (SBI)",
        "historical": "Historical (DICT)",
        "deal_btn": "🚀 DEAL / DRAW",
        "ai_title": "Live Vision Diagnostic",
        "upload_btn": "Capture or Upload Road Map",
        "start_ai": "Start AI Scan",
        "diag_report": "Big Data Report",
        "neutral": "Neutral",
        "loading_ai": "AI is analyzing the roadmap...",
        "big_road": "BIG ROAD", 
    }
}

def t(key, lang="CN"):
    return TRANSLATIONS.get(lang, {}).get(key, key)