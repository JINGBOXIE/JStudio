import streamlit as st
import yfinance as yf
import ai_engine_v3 as ae3 
from datetime import datetime
import streamlit.components.v1 as components

class MarketAnalyst:
    def __init__(self, watchlist_data, report_lang="中文"):
        self.watchlist_data = watchlist_data
        self.report_lang = report_lang

    def _get_stock_data(self, symbol):
        try:
            ticker = yf.Ticker(symbol)
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
        # 1. 动态获取当前时间，作为 AI 检索实时信息的基准
        from datetime import datetime
        now = datetime.now()
        current_date_str = now.strftime('%Y-%m-%d')
        current_month = now.month
        
        # 2. 动态季节性预测逻辑 (保持框架)
        if current_month == 3:
            seasonal_lookahead = "4月强劲行情"
        elif current_month == 4:
            seasonal_lookahead = "5月枯水期 (Sell in May)"
        else:
            seasonal_lookahead = f"{current_month + 1}月市场趋势"

        # 3. 异动标的数据提取
        vol_str = "市场波动平稳 (Stable Market)" 
        volatility_items = []
        for symbol, names in list(self.watchlist_data.items()):
            price, change = self._get_stock_data(symbol)
            if abs(change) >= 1.5:
                name = names[0] if self.report_lang == "中文" else names[1]
                volatility_items.append(f"{symbol}({name}): {change:+.2f}%")
        if volatility_items:
            vol_str = ", ".join(volatility_items)

        # --- 核心修改：将固定事件改为“动态指令”，要求 AI 自行识别当时重大事件 ---
        full_prompt = f"""
        Role: iMarket Pro Chief Strategist & Macro Economist.
        Current Time: {current_date_str}.
        Location: Pickering, ON, Canada.

        【核心任务：动态报告命名与季节性逻辑】
        根据当前日期（{current_date_str}）和“{seasonal_lookahead}”的前瞻，拟定一个包含 "iMarket Pro" 和 "2026" 的专业标题。

        【重点模块 1：🌎 全球宏观与地缘政治 (Macro & Geopolitics)】
        本节目标：识别影响估值的天花板。你必须根据【当前日期】的实时市场数据，分析以下动态三点：
        1. 实时宏观周期定位 (Current Macro Nexus)：
           - 自动识别当前主流利率环境（如 Fed/BoC 最新决议）及其对全球流动性的压制或释放逻辑。
        2. 实时地缘政治黑天鹅 (Live Geopolitical Risks)：
           - 核心：自动检索并评估【当前时刻】全球最重大的地缘冲突（如中东、东欧或贸易争端）。
           - 影响：分析该冲突对能源（原油/天然气）的传导逻辑，以及对关键指数（如 TSX, S&P 500）的提振或打压作用。
        3. 货币避险与估值逻辑 (Currency & Valuation)：
           - 分析当前美元指数 (DXY) 的强弱逻辑，及其对黄金 (GOLD) 和跨国科技巨头海外营收的实际影响。

        【重点模块 2：📊 季节性效应 (Seasonality) 参考】
        1月: 1月效应; 2月: 获利回吐; 4月: 强劲财报; 5-10月: Sell in May; 11-12月: 圣诞拉力。

        【重点模块 3：📈 投资逻辑与实战指令】
        - 结合异动标的 {vol_str} 给出分析。
        - 评估在【当前环境】下，防御性策略（如高股息）与进攻性策略（如 AI 科技）的权重分配建议。
        - 输出包含：[Score: X.X] 综合投资建议。

        【格式要求】: 
        1. 第一行是 # [动态标题]。
        2. 数字与汉字间保持 1 个空格。
        3. 全程使用语言: {self.report_lang}。
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
        [iMarket Pro] 全息战略报告生成核心方法。
        基于“宏观-产业-龙头”三层嵌套逻辑，动态结合当前时间与地缘环境。
        """
        # 1. 动态获取环境上下文 (不再锁定 2026-04，而是以运行时刻为准)
        current_date = datetime.now().strftime('%Y-%m-%d')
        
        # 注入动态环境变量（包含实时模拟的 2026 背景参数）
        env_context = f"""
        Current Report Date: {current_date}
        Estimated Context: 2026 Cycle Peak, Geopolitics: Iran Conflict Risk, Brent Oil: $120/bbl, Technology: Generative AI Mass Expansion.
        """
        
        # 2. 构建锁定的 4-Stage Prompt 框架
        full_strategic_prompt = f"""
        {env_context}
        
        # Role (角色定位)
        You are the iMarket Pro Global Chief Strategist. Your mission is to generate a 3-tier holistic strategy report.
        你现在是 iMarket Pro 全球首席策略官，负责生成“宏观-产业-龙头”三位一体的全息战略报告。

        # Stage 1: Macro Nexus (第一层：宏观天候图)
        - Define current Economic Cycle (e.g., Stagflation/Expansion) and Monetary Cycle (e.g., Pivot/Tightening).
        - Analyze geopolitical impact, specifically the 'Iran War' and '$120 Oil' context.
        - 必须首先判定当前经济周期（如：滞胀/扩张）与货币周期（如：转向/紧缩），并结合伊朗局势及 120 美金油价进行宏观定调。

        # Stage 2: Industry Waves (第二层：产业周期波浪)
        - Full scan of ALL 10 major sectors: Tech, Healthcare, Finance, Energy, Retail, Consumer, Defense, Utilities, REITs, Aviation.
        - Classify each sector's stage in the current cycle tide.
        - 全面扫描十大产业：科技、医疗、金融、能源、零售、消费、军工、公用事业、地产、航空，并识别它们在当前周期浪潮中的阶段。

        # Stage 3: Titan Deep-Dive (第三层：龙头微观穿透)
        - Analyze TOP 3 TITANS for each of the 10 industries (Total 30 companies).
        - Evaluate their financial resilience and strategic moat under the current Macro Nexus.
        - 针对十大行业的每一家 TOP 3 龙头（共 30 家），分析它们在当前宏观天候下的财务韧性与战略护城河。

        # Stage 4: Strategic Conclusion (第四层：总结与行动)
        - Highlight HOTSPOTS from the 30 titans. Provide actionable allocation advice (Offense vs Defense).
        - 从 30 家龙头中提取热点，给出具体的进攻与防御配置建议。

        【格式要求】:
        1. 使用 Markdown 格式，层级清晰。
        2. 重要数据与公司代码 ($TICKER) 加粗显示。
        3. 全程使用语言: {self.report_lang}。
        """

        # 3. 调用 AI 引擎 (ae3)，使用独立的 segment 标识以隔离逻辑
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
        pr_label = "🖨️ 打印" if self.report_lang == "中文" else "🖨️ Print"
        cl_label = "❌ 关闭" if self.report_lang == "中文" else "❌ Close"

        c1.download_button(dl_label, data=content, file_name="iMarket_Report_2026.md", use_container_width=True)
        if c2.button(pr_label, use_container_width=True):
            components.html("<script>window.print();</script>", height=0)
        if c3.button(cl_label, use_container_width=True):
            st.rerun()
