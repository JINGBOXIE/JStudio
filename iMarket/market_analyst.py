import streamlit as st
import yfinance as yf
import ai_engine_v3 as ae3
import os
import requests
from datetime import datetime
import streamlit.components.v1 as components

def _make_yf_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection":      "keep-alive",
    })
    return session

_YF_SESSION = _make_yf_session()


def _check_api_key() -> bool:
    """验证 GEMINI_API_KEY 是否存在于 Secrets 或环境变量，给出精确提示"""
    key = st.secrets.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not key:
        st.error(
            "⚠️ JStudio 引擎未检测到有效 API Key。\n\n"
            "**修复步骤（Streamlit Cloud）：**\n"
            "1. 进入 App → Settings → **Secrets**\n"
            "2. 添加以下内容（注意大小写必须完全一致）：\n"
            "```toml\n"
            'GEMINI_API_KEY = "AIza...你的Key..."\n'
            "```\n"
            "3. 保存后点击 **Reboot app**"
        )
        return False
    return True


class MarketAnalyst:
    def __init__(self, watchlist_data, report_lang="中文"):
        self.watchlist_data = watchlist_data
        self.report_lang = report_lang

    def _get_stock_data(self, symbol):
        try:
            ticker = yf.Ticker(symbol, session=_YF_SESSION)
            # 优先用 fast_info，避免 info 接口限流
            fi = ticker.fast_info
            current_price = getattr(fi, 'last_price', None)
            prev_close    = getattr(fi, 'previous_close', None)
            if current_price and not float(current_price) == float('nan'):
                prev = prev_close if prev_close else current_price
                change = ((float(current_price) - float(prev)) / float(prev)) * 100
                return float(current_price), change
        except Exception:
            pass

        # fallback: history
        try:
            hist = ticker.history(period="2d")
            if len(hist) >= 2:
                curr = hist['Close'].iloc[-1]
                prev = hist['Close'].iloc[-2]
                change = ((curr - prev) / prev) * 100
                return curr, change
        except Exception:
            pass

        return 0, 0

    def generate_content(self, index_data):
        # API Key 前置检查
        if not _check_api_key():
            return "❌ API Key 未配置，无法生成报告。"

        vol_str = "市场波动平稳 (Stable Market)"
        volatility_items = []
        for symbol, names in list(self.watchlist_data.items()):
            price, change = self._get_stock_data(symbol)
            if abs(change) >= 1.5:
                name = names[0] if self.report_lang == "中文" else names[1]
                volatility_items.append(f"{symbol}({name}): {change:+.2f}%")
        if volatility_items:
            vol_str = ", ".join(volatility_items)

        current_date = datetime.now().strftime('%Y-%m-%d %H:%M')

        full_prompt = f"""
        Role: iMarket Pro Chief Strategist & Macro Economist.
        Current Time: {current_date} (2026).
        Location: Pickering, ON, Canada.

        【核心任务：动态报告命名与季节性逻辑】
        根据当前日期和市场背景，拟定一个包含 "iMarket Pro" 和 "2026" 的专业标题。

        【重点模块 1：🌎 全球宏观与地缘政治 (Macro & Geopolitics)】
        1. 2026 宏观周期定位：分析当前 3.5%-3.75% 利率环境对整体流动性的压制逻辑。
        2. 地缘政治黑天鹅：评估伊朗与霍尔木兹海峡局势，分析原油在高位对通胀的传导。
        3. 汇率与避险：分析美元指数 (DXY) 对黄金 (GOLD) 及跨国科技巨头海外营收折算的影响。

        【重点模块 2：📊 季节性效应参考】
        1月: 1月效应; 2月: 获利回吐; 4月: 强劲财报/退税入场; 5-10月: Sell in May; 9月: 最弱; 11-12月: 圣诞拉力。

        【重点模块 3：📈 投资逻辑与实战指令】
        - 结合异动标的 {vol_str} 给出分析。
        - 评估高股息策略 ($MO, $TGT, $ENB) 在当前市场中的护城河价值。
        - 输出包含：[Score: X.X] 综合投资建议。

        【格式要求】:
        1. 第一行是 # [动态标题]。
        2. 使用 Markdown 格式，关键数据加粗。
        3. 数字与汉字间保持 1 个空格。
        4. 全程使用语言: {self.report_lang}。
        """

        report = ae3.run_v3_specialized_report(
            ticker="Macro_Market_Scan",
            segment="macro",
            data_payload=full_prompt,
            lang=self.report_lang
        )
        return report

    def generate_strategic_report(self):
        """
        [iMarket Pro] 全息战略报告 — 宏观-产业-龙头三层嵌套逻辑
        """
        if not _check_api_key():
            return "❌ API Key 未配置，无法生成报告。"

        current_date = datetime.now().strftime('%Y-%m-%d')

        env_context = f"""
        Current Report Date: {current_date}
        Context: 2026 Cycle Peak, Geopolitics: Iran Conflict Risk, Brent Oil: $120/bbl,
        Technology: Generative AI Mass Expansion.
        """

        full_strategic_prompt = f"""
        {env_context}

        # Role
        You are the iMarket Pro Global Chief Strategist.
        你现在是 iMarket Pro 全球首席策略官，负责生成"宏观-产业-龙头"三位一体的全息战略报告。

        # Stage 1: Macro Nexus（宏观天候图）
        - 判定当前经济周期（滞胀/扩张）与货币周期（转向/紧缩）。
        - 结合伊朗局势及 120 美金油价进行宏观定调。

        # Stage 2: Industry Waves（产业周期波浪）
        - 全面扫描十大产业：科技、医疗、金融、能源、零售、消费、军工、公用事业、地产、航空。
        - 识别它们在当前周期浪潮中的阶段。

        # Stage 3: Titan Deep-Dive（龙头微观穿透）
        - 针对十大行业各 TOP 3 龙头（共 30 家），分析财务韧性与战略护城河。

        # Stage 4: Strategic Conclusion（总结与行动）
        - 从 30 家龙头中提取热点，给出进攻与防御配置建议。

        【格式要求】:
        1. 使用 Markdown 格式，层级清晰。
        2. 重要数据与公司代码 ($TICKER) 加粗显示。
        3. 全程使用语言: {self.report_lang}。
        """

        report = ae3.run_v3_specialized_report(
            ticker="STRATEGIC_NEXUS",
            segment="strategic_v4",
            data_payload=full_strategic_prompt,
            lang=self.report_lang
        )
        return report

    @st.dialog("iMarket Pro Analysis", width="large")
    def display_report(self, content):
        st.caption(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} | Pickering, ON")
        st.markdown(content)
        st.divider()
        c1, c2, c3 = st.columns(3)

        dl_label = "📥 下载报告" if self.report_lang == "中文" else "📥 Download"
        pr_label = "🖨️ 打印"   if self.report_lang == "中文" else "🖨️ Print"
        cl_label = "❌ 关闭"   if self.report_lang == "中文" else "❌ Close"

        c1.download_button(dl_label, data=content,
                           file_name="iMarket_Report_2026.md",
                           use_container_width=True)
        if c2.button(pr_label, use_container_width=True):
            components.html("<script>window.print();</script>", height=0)
        if c3.button(cl_label, use_container_width=True):
            st.rerun()
