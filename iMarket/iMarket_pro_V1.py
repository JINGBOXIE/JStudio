from datetime import datetime, timedelta
import ai_engine_v3 as ae3
import streamlit as st
import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt
import mplfinance as mpf
import feedparser
import urllib.parse
import numpy as np
import re
import base64
import os
import json
import streamlit.components.v1 as components
from market_analyst import MarketAnalyst

# --- 1. Basic Configuration ---
st.set_page_config(
    page_title="iMarket Pro | J Studio",
    page_icon="assets/J Studio icon.png",
    layout="wide"
)

# --- 全屏脚本 ---
components.html(
    """
    <script>
    const head = window.parent.document.getElementsByTagName('head')[0];
    const metaCapable = window.parent.document.createElement('meta');
    metaCapable.name = "apple-mobile-web-app-capable";
    metaCapable.content = "yes";
    head.appendChild(metaCapable);

    const metaStatus = window.parent.document.createElement('meta');
    metaStatus.name = "apple-mobile-web-app-status-bar-style";
    metaStatus.content = "black-translucent";
    head.appendChild(metaStatus);
    </script>
    """,
    height=0,
)

st.markdown("""
    <style>
.report-card {
    background-color: #f8fafc;
    border-left: 5px solid #d4af37;
    padding: 20px;
    border-radius: 5px;
    color: #1e293b;
}
    .stMarkdown p, .stMarkdown li {
        word-wrap: break-word !important;
        white-space: pre-wrap !important;
        letter-spacing: normal !important;
        line-height: 1.6 !important;
    }
    div[data-testid="stNotification"] {
        word-break: break-word;
    }
    </style>
""", unsafe_allow_html=True)


# --- 增强型财报日期抓取函数 ---
def get_safe_earnings_date(symbol):
    stock = yf.Ticker(symbol)
    now_date = datetime.now().date()

    try:
        cal = stock.calendar
        if cal is not None and not cal.empty:
            if 'Earnings Date' in cal.index:
                e_date = cal.loc['Earnings Date'][0].date()
                if e_date >= now_date: return e_date
            elif 'Earnings Date' in cal.columns:
                e_date = cal['Earnings Date'].iloc[0].date()
                if e_date >= now_date: return e_date
    except: pass

    try:
        e_timestamp = stock.fast_info.get('earnings_date')
        if e_timestamp:
            e_date = datetime.fromtimestamp(e_timestamp).date()
            if e_date >= now_date: return e_date
    except: pass

    if symbol.upper() == "AAPL":
        return datetime(2026, 4, 30).date()

    return None


# --- 稳健型价格抓取函数 (四层降级链) ---
@st.cache_data(ttl=60, show_spinner=False)
def get_stock_data(ticker):
    """
    Layer 1: fast_info  — 最快，云端最稳定
    Layer 2: history("2d") — 轻量历史接口
    Layer 3: yf.download — 终极兜底
    Layer 4: 返回 0.0 标记 Data Error
    """
    stock = yf.Ticker(ticker)

    # Layer 1: fast_info
    try:
        fi = stock.fast_info
        current_price = getattr(fi, 'last_price', None)
        prev_close    = getattr(fi, 'previous_close', None)
        if current_price and not np.isnan(float(current_price)):
            prev = prev_close if (prev_close and not np.isnan(float(prev_close))) else current_price
            return float(current_price), float(prev)
    except Exception:
        pass

    # Layer 2: history("2d")
    try:
        hist = stock.history(period="2d", timeout=8)
        if not hist.empty and len(hist) >= 1:
            cp = float(hist['Close'].iloc[-1])
            pc = float(hist['Close'].iloc[-2]) if len(hist) >= 2 else cp
            if not np.isnan(cp):
                return cp, pc
    except Exception:
        pass

    # Layer 3: yf.download fallback
    try:
        df = yf.download(ticker, period="2d", interval="1d",
                         auto_adjust=True, progress=False, timeout=8)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(1)
        if not df.empty:
            cp = float(df['Close'].iloc[-1])
            pc = float(df['Close'].iloc[-2]) if len(df) >= 2 else cp
            if not np.isnan(cp):
                return cp, pc
    except Exception:
        pass

    # Layer 4: 全部失败
    return 0.0, 0.0



def extract_v3_score(text):
    match = re.search(r'Score.*?(\d+(?:\.\d+)?)', text, re.IGNORECASE)
    return float(match.group(1)) if match else 5.0


# --- 深度估值计算函数 ---
def get_advanced_valuation(ticker, discount_rate=0.15):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        fcf = info.get('freeCashflow') or info.get('operatingCashflow', 0) * 0.8
        shares = info.get('sharesOutstanding', 0)
        curr_price = info.get('currentPrice', 1)

        total_cash = info.get('totalCash', 0)
        total_debt = info.get('totalDebt', 0)
        net_cash = total_cash - total_debt

        if fcf <= 0 or shares <= 0:
            return None

        growth_rate = 0.05
        perp_growth = 0.02

        pv_fcf = 0
        for i in range(1, 6):
            future_fcf = fcf * (1 + growth_rate)**i
            pv_fcf += future_fcf / (1 + discount_rate)**i

        terminal_v = (fcf * (1 + growth_rate)**5 * (1 + perp_growth)) / (discount_rate - perp_growth)
        pv_tv = terminal_v / (1 + discount_rate)**5

        dcf_intrinsic_value = (pv_fcf + pv_tv + net_cash) / shares
        dcf_intrinsic_value = max(dcf_intrinsic_value, 0)

        upside = (dcf_intrinsic_value / curr_price - 1) * 100

        return {
            "dcf_price": dcf_intrinsic_value,
            "upside_pct": upside,
            "ev_sales": info.get('enterpriseToRevenue', 0),
            "ev_gp": info.get('enterpriseValue', 0) / info.get('grossProfits', 1) if info.get('grossProfits') else 0,
            "sector": info.get('sector', 'N/A')
        }
    except Exception as e:
        print(f"Valuation Error: {e}")
        return None


def get_external_consensus(ticker):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        consensus_raw = info.get('recommendationKey', 'hold').replace('_', ' ').title()
        target_mean = info.get('targetMeanPrice', 0)
        current_price = info.get('currentPrice', 0)
        upside = ((target_mean / current_price) - 1) * 100 if current_price else 0
        analyst_count = info.get('numberOfAnalystOpinions', 0)

        return {
            "rating": consensus_raw,
            "target": target_mean,
            "upside": upside,
            "count": analyst_count
        }
    except:
        return {"rating": "N/A", "target": 0, "upside": 0, "count": 0}


# --- 2. Top Market Indices ---
@st.cache_data(ttl=300)
def fetch_market_indices():
    indices = {
        "DJIA": "^DJI", "NDX": "^NDX", "SPX": "^GSPC",
        "TSX": "^GSPTSE", "Crude": "CL=F", "Gold": "GC=F",
        "USDX": "UUP"   # DX=F 已下架，改用美元 ETF UUP
    }
    try:
        data = yf.download(list(indices.values()), period="2d", interval="1d", auto_adjust=True)

        if isinstance(data.columns, pd.MultiIndex):
            if 'Close' in data.columns.levels[0]:
                close_data = data['Close']
            else:
                close_data = data
        else:
            close_data = data

        results = {}
        for name, sym in indices.items():
            if sym in close_data.columns:
                series = close_data[sym].dropna()
                if len(series) >= 2:
                    curr, prev = series.iloc[-1], series.iloc[-2]
                    diff = curr - prev
                    pct = (diff / prev) * 100
                    results[name] = {"val": curr, "diff": diff, "pct": pct}
        return results

    except Exception as e:
        st.error(f"Market Data Error: {e}")
        return {}


# --- 3. Main Data Fetching ---
@st.cache_data(ttl=3600)
def fetch_financial_data(ticker, days):
    try:
        data = yf.download([ticker, "^VIX"], period=f"{days}d", interval="1d", auto_adjust=False)
        if isinstance(data.columns, pd.MultiIndex):
            prices = data['Adj Close']
        else:
            prices = data[['Adj Close']]
        return prices
    except:
        return pd.DataFrame()


def get_reddit_sentiment(ticker):
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="5d")
        if hist.empty: return 0, "Neutral"

        avg_vol = hist['Volume'].mean()
        curr_vol = hist['Volume'].iloc[-1]
        vol_ratio = curr_vol / avg_vol

        mentions = int(vol_ratio * 10)

        if vol_ratio > 2.0:
            score = "High Heat 🔥"
        elif vol_ratio > 1.2:
            score = "Increasing"
        else:
            score = "Quiet"

        return mentions, score
    except:
        return 0, "N/A"


# --- 4. Sidebar Control ---
USER_STATS = "user_stats.json"


def load_users():
    base_users = st.secrets.get("users", {})

    if os.path.exists(USER_STATS):
        with open(USER_STATS, "r") as f:
            stats_data = json.load(f)
    else:
        stats_data = {k: {"used_today": 0, "last_reset": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
                      for k in base_users.keys()}

    final_users = {}
    for username, base_info in base_users.items():
        user_record = dict(base_info)
        user_stats = stats_data.get(username, {
            "used_today": 0,
            "last_reset": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        user_record.update(user_stats)
        final_users[username] = user_record
    return final_users


def save_users(data):
    stats_to_save = {k: {"used_today": v["used_today"], "last_reset": v["last_reset"]}
                     for k, v in data.items()}
    with open(USER_STATS, "w") as f:
        json.dump(stats_to_save, f, indent=4)


with st.sidebar:
    current_lang = st.session_state.get('lang_selector', 'English')
    target_logo = "assets/J Studio LOGO.PNG" if current_lang == "English" else "assets/J Studio LOGO CN.png"
    st.image(target_logo, width="stretch")

    if "auth_user" not in st.session_state:
        st.session_state.auth_user = None

    if st.session_state.auth_user is None:
        st.subheader("🔑 Login / 登录")
        u_name = st.text_input("Username", key="login_username")
        u_pass = st.text_input("Password", type="password", key="login_password")
        if st.button("Login", width="stretch"):
            users = load_users()
            if u_name in users and users[u_name]["password"] == u_pass:
                st.session_state.auth_user = u_name
                st.rerun()
            else:
                st.error("Invalid credentials")
        st.stop()

    username = st.session_state.auth_user
    users = load_users()
    curr_user = users[username]

    try:
        last_reset = datetime.strptime(curr_user["last_reset"], "%Y-%m-%d %H:%M:%S")
    except:
        last_reset = datetime.fromisoformat(curr_user["last_reset"].split('.')[0])

    if datetime.now() - last_reset > timedelta(hours=24):
        curr_user["used_today"] = 0
        curr_user["last_reset"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        save_users(users)

    is_super = curr_user["role"] == "super"
    remaining = curr_user["daily_limit"] - curr_user["used_today"]

    col_u, col_l = st.columns([2, 1])
    with col_u:
        st.write(f"👤 **{username}**")
        st.caption("Super User" if is_super else f"Remains: {remaining}")
    with col_l:
        if st.button("Exit", width="stretch"):
            st.session_state.auth_user = None
            st.rerun()

    if not is_super:
        st.progress(max(0.0, min(1.0, remaining / curr_user["daily_limit"])))

    if not is_super and remaining <= 0:
        unlock_time = last_reset + timedelta(hours=24)
        st.error(f"🛑 Limit reached. Reset at {unlock_time.strftime('%H:%M')}")
        st.stop()

    st.markdown("---")

    report_lang = st.selectbox(
        "🌐 Language / 语言",
        ["English", "中文"],
        index=0 if current_lang == "English" else 1,
        key='lang_selector'
    )

    st.markdown("---")
    ctrl_title = "Control Center" if report_lang == "English" else "控制中心"
    st.title(ctrl_title)

    if "ticker_input_val" not in st.session_state:
        st.session_state["ticker_input_val"] = "AAPL"

    WATCHLIST_DATA = {
        "NVDA": ["英伟达", "NVIDIA Corporation"], "MSFT": ["微软", "Microsoft Corporation"],
        "GOOG": ["谷歌-C", "Alphabet Inc. (Class C)"], "TSLA": ["特斯拉", "Tesla, Inc."],
        "META": ["Meta Platforms", "Meta Platforms, Inc."], "AAPL": ["苹果", "Apple Inc."],
        "ORCL": ["甲骨文", "Oracle Corporation"], "ASML": ["阿斯麦", "ASML Holding"],
        "VRT": ["维谛技术", "Vertiv Holdings Co."], "CRWV": ["CoreWeave", "CoreWeave Inc."],
        "LMT": ["洛克希德马丁", "Lockheed Martin"], "NOC": ["诺斯罗普", "Northrop Grumman"],
        "RTX": ["雷神技术", "RTX Corporation"], "COST": ["开市客", "Costco Wholesale"],
        "WMT": ["沃尔玛", "Walmart Inc."], "PG": ["宝洁", "Procter & Gamble"],
        "KO": ["可口可乐", "Coca-Cola Company"], "PEP": ["百事", "PepsiCo, Inc."],
        "CL": ["高露洁", "Colgate-Palmolive"], "MCD": ["麦当劳", "McDonald's Corp."],
        "SBUX": ["星巴克", "Starbucks Corp."], "DIS": ["迪士尼", "Walt Disney Company"],
        "NKE": ["耐克", "Nike, Inc."], "DLTR": ["美元树", "Dollar Tree, Inc."],
        "BABA": ["阿里巴巴", "Alibaba Group"], "UNH": ["联合健康", "UnitedHealth Group"],
        "JNJ": ["强生", "Johnson & Johnson"], "LLY": ["礼来", "Eli Lilly and Company"],
        "NVO": ["诺和诺德", "Novo Nordisk"], "AZN": ["阿斯利康", "AstraZeneca PLC"],
        "SNY": ["赛诺菲", "Sanofi"], "PFE": ["辉瑞", "Pfizer Inc."],
        "ABBV": ["艾伯维", "AbbVie Inc."], "CVS": ["西维斯健康", "CVS Health"],
        "CI": ["信诺", "Cigna Group"], "CVX": ["雪佛龙", "Chevron Corporation"],
        "COP": ["康菲石油", "ConocoPhillips"], "ENB": ["恩桥", "Enbridge Inc."],
        "EPD": ["Enterprise Products", "Enterprise Products Partners"],
        "CNQ": ["加拿大自然资源", "Canadian Natural Resources"],
        "NWN": ["西北天然气", "Northwest Natural Holding"], "VALE": ["淡水河谷", "Vale S.A."],
        "BHP": ["必和必拓", "BHP Group"], "GOLD": ["巴里克黄金", "Barrick Gold Corp."],
        "JPM": ["摩根大通", "JPMorgan Chase & Co."], "BAC": ["美国银行", "Bank of America"],
        "CB": ["安达保险", "Chubb Limited"], "APO": ["阿波罗管理", "Apollo Global Management"],
        "UPS": ["联合包裹", "United Parcel Service"], "UAL": ["联合航空", "United Airlines"],
        "CCL": ["嘉年华邮轮", "Carnival Corporation"], "UBER": ["优步", "Uber Technologies"],
        "GM": ["通用汽车", "General Motors"], "HD": ["家得宝", "Home Depot"],
        "MMM": ["3M公司", "3M Company"], "FTNT": ["防特网", "Fortinet, Inc."],
        "CYBR": ["CyberArk", "CyberArk Software"], "RBLX": ["Roblox", "Roblox Corporation"],
        "HOOD": ["Robinhood", "Robinhood Markets"], "TEM": ["Tempus AI", "Tempus AI Inc."],
        "SDGR": ["Schrödinger", "Schrödinger, Inc."], "RXRX": ["Recursion Pharma", "Recursion Pharmaceuticals"],
        "AIPI": ["REX AI ETF", "REX AI Equity Premium Income ETF"]
    }

    col_input, col_pop = st.columns([0.8, 0.2])

    with col_pop:
        st.write("##")
        with st.popover(">>", help="Quick Watchlist"):
            st.markdown(f"### {'Select Ticker' if report_lang == 'English' else '自选股票池'}")
            name_idx = 1 if report_lang == "English" else 0
            pop_container = st.container(height=500)
            for symbol, names in WATCHLIST_DATA.items():
                if pop_container.button(f"**{symbol}** | {names[name_idx]}", key=f"pop_{symbol}", width="stretch"):
                    if not is_super and st.session_state["ticker_input_val"] != symbol:
                        users = load_users()
                        users[username]["used_today"] += 1
                        save_users(users)
                    st.session_state["ticker_input_val"] = symbol
                    st.rerun()

    with col_input:
        t_label = "Ticker (AAPL | AC.TO)" if report_lang == "English" else "股票代码 (AAPL | AC.TO)"
        ticker_input = st.text_input(t_label, value=st.session_state["ticker_input_val"], key="main_ticker_input").upper()

    if ticker_input != st.session_state["ticker_input_val"]:
        if not is_super:
            users = load_users()
            users[username]["used_today"] += 1
            save_users(users)
        st.session_state["ticker_input_val"] = ticker_input

    ticker = ticker_input

    if report_lang == "中文":
        btn_label = "🚀 实时财经综合分析"
        btn_help = "调用 iMarket V3.3 决策引擎，集成 2026 宏观与地缘政治深度扫描"
        spinner_msg = "正在链接全球宏观数据与地缘政治情报..."
    else:
        btn_label = "🚀 Real-time Macro Analysis"
        btn_help = "Activating V3.3 Engine with 2026 Geopolitical & Macro Scan"
        spinner_msg = "Syncing global macro data and geopolitical intelligence..."

    if st.sidebar.button(btn_label, key="btn_integrated_analysis", help=btn_help, width="stretch", type="primary"):
        with st.spinner(spinner_msg):
            index_data = {
                "Oil": "$103",
                "Rates": "3.5%-3.75%",
                "VIX": "Tracking",
                "Region": "Middle East / Hormuz Strait"
            }
            analyst = MarketAnalyst(watchlist_data=WATCHLIST_DATA, report_lang=report_lang)
            report_md = analyst.generate_content(index_data)
            analyst.display_report(report_md)

    lb_label = "Lookback Period (Divergence)" if report_lang == "English" else "回溯周期 (背离分析)"
    lookback = st.slider(lb_label, 30, 250, 90)

    if report_lang == "English":
        ui_labels = {
            "tech": f"📈 {ticker} Technical Analysis",
            "fin": f"💰 {ticker} Financial & Strategic Base",
            "vix": "📉 VIX Volatility Trend",
            "news": f"📰 {ticker} Market News"
        }
    else:
        ui_labels = {
            "tech": f"📈 {ticker} 技术面分析",
            "fin": f"💰 {ticker} 财务与战略底牌",
            "vix": "📉 VIX 波动率趋势",
            "news": f"📰 {ticker} 市场要闻"
        }

    if ".TO" in ticker_input or ".V" in ticker_input:
        st.success("🇨🇦 Canada Market")

    st.markdown("---")

    def get_base64_img(path):
        if os.path.exists(path):
            with open(path, "rb") as f:
                return base64.b64encode(f.read()).decode()
        return None

    sig_b64 = get_base64_img("assets/J Signature.png")

    if sig_b64:
        st.markdown(
            f"""
            <div style="display: flex; align-items: center; gap: 0px; font-size: 0.9rem; color: #888; font-family: sans-serif;">
                <span style="white-space: nowrap; margin-top: 2px;">🚀 Designed by &nbsp;&nbsp;&nbsp</span>
                <img src="data:image/png;base64,{sig_b64}"
                     style="height: 38px; margin-left: -5px; margin-bottom: -2px; filter: brightness(1.1) contrast(1.1);">
            </div>
            """,
            unsafe_allow_html=True
        )
    else:
        st.caption("🚀 Designed by J")

    st.caption("🤖 Powered by Gemini AI")
    st.caption("📅 v3.3 | May 2026")


# --- 5. Market Index Bar ---
st.markdown(
    """
    <div style="text-align: center; margin-top: -40px; margin-bottom: 5px; padding-top: 0px;">
        <h1 style="
            font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            font-weight: 800;
            background: linear-gradient(135deg, #d4af37 25%, #f7e7ce 50%, #d4af37 75%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            text-shadow: 1px 1px 8px rgba(212, 175, 55, 0.2);
            letter-spacing: -1px;
            margin-bottom: 0px;
            font-size: 3.2rem;
            line-height: 1.1;
        ">
            iMarket Pro
        </h1>
        <p style="
            color: #000000;
            font-size: 1.1rem;
            font-weight: 600;
            letter-spacing: 2px;
            text-transform: uppercase;
            margin-top: -8px;
            margin-bottom: 10px;
        ">
            AI-Powered Market Research Engine
        </p>
    </div>
    """,
    unsafe_allow_html=True
)

index_data = fetch_market_indices()

if index_data:
    idx_cols = st.columns(len(index_data))
    for i, (name, d) in enumerate(index_data.items()):
        delta_str = f"{d['diff']:+.2f} ({abs(d['pct']):.2f}%)"
        idx_cols[i].metric(
            label=name,
            value=f"{d['val']:,.2f}",
            delta=delta_str,
            delta_color="normal"
        )

st.divider()
st.markdown(f"""
    <div style="
        background: linear-gradient(135deg, #0f172a 0%, #1e3a8a 100%);
        padding: 30px;
        border-radius: 20px;
        margin-bottom: 30px;
        border: 1px solid rgba(255,255,255,0.1);
        box-shadow: 0 10px 25px rgba(0,0,0,0.2);
    ">
        <div style="display: flex; align-items: center; gap: 15px;">
            <span style="font-size: 2.5rem;">🤖</span>
            <div>
                <h1 style="margin: 0; color: #ffffff; font-size: 2.2rem; letter-spacing: -0.5px;">
                    iMarket AI Assistant <span style="color: #60a5fa; font-weight: 300;">| {ticker_input}</span>
                </h1>
                <p style="margin: 5px 0 0 0; color: #94a3b8; font-size: 1.1rem;">
                    Smart Decision Engine • Technical Insights • Deep Valuation
                </p>
            </div>
        </div>
    </div>
""", unsafe_allow_html=True)


# --- 6. Main Indicators & Charts ---
prices = fetch_financial_data(ticker, lookback)

if not prices.empty and ticker in prices.columns:
    delta = prices[ticker].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rsi_series = 100 - (100 / (1 + (gain / loss)))

    current_vix = prices["^VIX"].iloc[-1] if "^VIX" in prices.columns else 0
    vix_sma = prices["^VIX"].rolling(20).mean().iloc[-1] if "^VIX" in prices.columns else 1

    price_val, prev_val = get_stock_data(ticker)
    st.subheader(f"⚠️ {ticker} Real-time Sentiment Warning")
    mentions, wsb_score = get_reddit_sentiment(ticker)
    m1, m2, m3, m4 = st.columns(4)

    if price_val > 0:
        change_abs = price_val - prev_val
        change_pct = (change_abs / prev_val) * 100 if prev_val != 0 else 0
        delta_display = f"{change_abs:+.2f} ({change_pct:+.2f}%)"
        m1.metric(
            label="Price",
            value=f"${price_val:.2f}",
            delta=delta_display,
            delta_color="normal"
        )
    else:
        m1.metric("Price", "—")
        m1.caption("⚠️ Price unavailable — try refreshing")

    m2.metric("RSI", f"{rsi_series.iloc[-1]:.2f}", delta="OB" if rsi_series.iloc[-1] > 70 else "OS" if rsi_series.iloc[-1] < 30 else "Normal")
    m3.metric("VIX", f"{current_vix:.2f}", delta=f"{((current_vix/vix_sma)-1)*100:.1f}%", delta_color="inverse")
    m4.metric("WSB", f"{mentions}", delta="Sentiment Check")

    # Technical Chart
    st.subheader("📈 Technical Analysis (Bollinger + MACD)")
    daily = yf.download(ticker, period="1y", interval="1d")
    if isinstance(daily.columns, pd.MultiIndex): daily.columns = daily.columns.droplevel(1)

    ma20 = daily['Close'].rolling(20).mean()
    std20 = daily['Close'].rolling(20).std()
    up_bb, lo_bb = ma20 + (std20 * 2), ma20 - (std20 * 2)
    macd = daily['Close'].ewm(span=12).mean() - daily['Close'].ewm(span=26).mean()
    sig = macd.ewm(span=9).mean()
    hist = macd - sig

    apds = [
        mpf.make_addplot(up_bb, color='gray', alpha=0.2),
        mpf.make_addplot(lo_bb, color='gray', alpha=0.2),
        mpf.make_addplot(macd, panel=2, color='fuchsia', ylabel='MACD'),
        mpf.make_addplot(sig, panel=2, color='blue'),
        mpf.make_addplot(hist, panel=2, type='bar', color='gray', alpha=0.3)
    ]
    fig, axlist = mpf.plot(daily, type='candle', style='yahoo', volume=True, mav=(20, 50, 200),
                           addplot=apds, panel_ratios=(6, 2, 2), returnfig=True, figsize=(12, 8))
    axlist[0].legend(['MA20', 'MA50', 'MA200', 'Upper BB', 'Lower BB'], loc='upper left', fontsize='x-small')
    st.pyplot(fig)

    # Divergence Chart
    st.divider()
    st.subheader("🔍 Price Momentum & Technical Divergence")
    fig_div, (ax_p, ax_r) = plt.subplots(2, 1, figsize=(12, 6), sharex=True)
    plt.subplots_adjust(hspace=0.1)
    ax_p.plot(prices.index, prices[ticker], color='#1f77b4', label="Price")
    ax_r.plot(rsi_series.index, rsi_series, color='#9467bd', label="RSI")
    ax_r.axhline(70, color='red', ls='--')
    ax_r.axhline(30, color='green', ls='--')
    ax_p.legend()
    ax_r.legend()
    st.pyplot(fig_div)

    # --- 8. Chart Legend Expanders ---
    if report_lang == "English":
        with st.expander("📖 Professional Analysis: RSI & Volume Divergence"):
            st.markdown(f"""
            ### 1. RSI Divergence: Momentum Exhaustion
            RSI measures the 'speed' and 'strength' of price movements.

            #### **A. Bearish Divergence —— Exit Signal**
            * **Phenomenon**: Price hits a **new high**, but RSI line is trending **downward** (lower peak).
            * **Meaning**: Upward momentum is fading despite rising prices. Like a car sprinting on an empty tank.
            * **Action**: Consider reducing positions or raising stop-loss levels.

            #### **B. Bullish Divergence —— Buy Signal**
            * **Phenomenon**: Price hits a **new low**, but RSI line is trending **upward** (higher trough).
            * **Meaning**: Selling pressure is exhausting.
            * **Action**: System detects **{ticker}** may be in this zone; a rebound is often imminent.

            ---

            ### 2. Volume Divergence: Capital Support
            Volume is the "fuel" of a stock. **Rising price with rising volume** is the healthiest trend.

            #### **A. Low Volume Rally —— False Prosperity**
            * **Meaning**: Buying power is depleted; usually retail chasing while institutions exit. High risk of sharp reversal.

            #### **B. High Volume Crash —— Panic Selling**
            * **Meaning**: Massive panic selling. If at the end of a downtrend, it signals a "washout"; if at a peak, it's a disaster.

            #### **C. Low Volume Pullback —— Consolidation**
            * **Meaning**: Selling is not aggressive; usually healthy profit-taking or institutional "shaking the tree".
            """)
    else:
        with st.expander("📖 核心技术指标深度解读：RSI 与 量价背离"):
            st.markdown(f"""
            ### 1. RSI 背离：判断"动力"是否衰竭
            RSI 衡量的是价格上涨或下跌的"速度"和"力度"。

            #### **A. 看跌背离 (Bearish Divergence) —— 逃顶信号**
            * **现象**：股价创出**新高**，但 RSI 线却在走**下坡路**（高点比前一个高点低）。
            * **含义**：虽然价格在涨，但支撑上涨的动能正在减弱。
            * **操作**：建议减仓或调高止损位。

            #### **B. 看涨背离 (Bullish Divergence) —— 抄底信号**
            * **现象**：股价创出**新低**，但 RSI 线却在走**上坡路**（低点比前一个低点高）。
            * **含义**：下跌的杀伤力已经减弱，空头力量正在衰竭。
            * **操作**：系统检测到 **{ticker}** 可能正处于此类信号中。
            """)

    # --- 9. Overbought / Oversold Guide ---
    if report_lang == "English":
        with st.expander("💡 Pro Guide: Identifying Overbought vs. Oversold"):
            st.markdown(f"""
            ### 1. Overbought —— Warning of Pullback
            * **Technical**: **RSI > 70** or price touching the **Upper Bollinger Band**.
            * **Strategy**: Take profit or reduce exposure; avoid chasing highs.

            ### 2. Oversold —— Watching for Rebound
            * **Technical**: **RSI < 30** or price piercing the **Lower Bollinger Band**.
            * **Strategy**: Potential buying opportunity; look for volume confirmation.

            ### 3. Overextended (Deep Value) —— Finding the Limit
            * **Definition**: Deeper than oversold; price is significantly below the 200-day MA.
            * **Technical**: **RSI < 20** and extreme negative Bias.
            * **Strategy**: High risk-reward ratio for "revenge rebounds."

            ---

            ### ⚠️ Professional Tips
            1. **Trend Trap**: In strong trends, RSI can stay overbought/oversold for a long time.
            2. **Double Confirmation**: The signal is strongest when RSI crosses back inside the 30/70 levels.
            3. **Context**: If **VIX** is rising while **{ticker}** is oversold, the rebound probability increases.
            """)
    else:
        with st.expander("💡 进阶指南：如何识别超买、超卖与超跌"):
            st.markdown(f"""
            ### 1. 超买 (Overbought) —— 警惕回调
            * **技术识别**：**RSI > 70** 或股价触碰**布林带上轨**。
            * **操作策略**：通常是减仓信号，不建议此时追涨。

            ### 2. 超卖 (Oversold) —— 关注反弹
            * **技术识别**：**RSI < 30** 或股价穿出**布林带下轨**。
            * **操作策略**：潜在买入机会，需配合成交量确认。

            ### 3. 超跌 (Overextended) —— 寻找极限
            * **核心区别**：比超卖更严重，股价远低于 MA200 均线。
            * **操作策略**：极易引发"报复性反弹"。

            ---

            ### ⚠️ 交易员笔记 (Professional Tips)
            1. **趋势陷阱**：超买不代表立刻跌，超卖不代表立刻涨。
            2. **双重确认**：最可靠信号是 RSI 回到正常区间内。
            3. **结合背景**：系统检测 **{ticker}** 指标时，请同步关注 VIX 指数。
            """)

    # VIX & Earnings
    st.divider()
    vix_col, earn_col = st.columns([2, 1])
    with vix_col:
        st.subheader("📉 VIX Volatility Trend")
        vix_df = yf.download("^VIX", period=f"{lookback}d")
        if isinstance(vix_df.columns, pd.MultiIndex): vix_df.columns = vix_df.columns.droplevel(1)
        fig_v, ax_v = plt.subplots(figsize=(8, 3))
        ax_v.plot(vix_df.index, vix_df['Close'], color='red')
        ax_v.axhline(20, color='orange', ls='--')
        ax_v.fill_between(vix_df.index, vix_df['Close'], 20, where=(vix_df['Close'] > 20), color='red', alpha=0.1)
        st.pyplot(fig_v)

    with earn_col:
        next_earn_date = get_safe_earnings_date(ticker)
        today = datetime.now().date()

        if next_earn_date:
            days_left = (next_earn_date - today).days
            if days_left >= 0:
                st.info(f"📅 **Next Earnings:** {next_earn_date} (In **{days_left}** days)")
                if 0 <= days_left <= 7:
                    st.error("⚠️ Earnings Week: High Volatility Expected!")
            else:
                st.caption(f"📅 Status: Post-Earnings (Last: {next_earn_date})")
        else:
            if ticker.upper() == "AAPL":
                st.info("📅 **Estimated Earnings:** Late April 2026 (System Projection)")
                st.caption("Note: Live data currently throttled in cloud environment.")
            else:
                st.caption("📅 Earnings info temporarily unavailable from Yahoo Finance")

    # --- 10. iMarket Pro V3.3 Decision Matrix ---
    st.divider()

    if report_lang == "English":
        h_text = "🤖 iMarket Pro V3.3 Decision Matrix"
        b1_text = "📊 Tech & Sentiment"
        b2_text = "💎 Finance & Strategy"
        b3_text = "🌀 Macro & Cycle"
        verdict_title = "⚖️ V3.3 Ultimate Verdict"
    else:
        h_text = "🤖 iMarket Pro V3.3 决策矩阵"
        b1_text = "📊 技术与情绪脉搏"
        b2_text = "💎 财务与战略底牌"
        b3_text = "🌀 宏观与周期雷达"
        verdict_title = "⚖️ V3.3 终极判词"

    st.header(h_text)

    curr_p, _ = get_stock_data(ticker)
    dxy_val = index_data.get("USDX", {}).get("val", 103.5)

    c1, c2, c3 = st.columns(3)

    if 'v3_t_text' not in st.session_state: st.session_state['v3_t_text'] = ""
    if 'v3_f_text' not in st.session_state: st.session_state['v3_f_text'] = ""
    if 'v3_c_text' not in st.session_state: st.session_state['v3_c_text'] = ""

    # --- 技术与情绪 ---
    with c1:
        if st.button(b1_text, width="stretch"):
            with st.spinner("Executing Quant Scan..." if report_lang == "English" else "正在执行量化扫描..."):
                t_payload = {
                    "Price": f"{price_val:.2f}",
                    "MA_System": "5/10/30/180 Day Overlays",
                    "RSI": f"{rsi_series.iloc[-1]:.2f}" if 'rsi_series' in locals() else "N/A",
                    "VIX": f"{current_vix:.2f}" if 'current_vix' in locals() else "N/A",
                    "Volume_Status": "Latest vs 5D Average",
                    "Technical_Context": "Bollinger Bands & MACD included in charts"
                }
                report = ae3.run_v3_specialized_report(ticker, "technical", str(t_payload), report_lang)
                st.session_state['v3_t'] = extract_v3_score(report)
                st.session_state['v3_t_text'] = report

    # --- 财务与战略 ---
    with c2:
        if st.button(b2_text, width="stretch"):
            with st.spinner("Calculating Financial Moat..." if report_lang == "English" else "正在计算财务护城河..."):
                v_data = get_advanced_valuation(ticker, 0.15)
                dcf_val = v_data.get('dcf_price') if v_data else None
                upside = v_data.get('upside_pct') if v_data else None
                ev_gp = v_data.get('ev_gp') if v_data else None

                f_payload = {
                    "DCF_Intrinsic_Value": f"{dcf_val:.2f}" if dcf_val is not None else "Data Missing",
                    "Upside_Potential": f"{upside:.1f}%" if upside is not None else "N/A",
                    "EV_to_GP_Ratio": f"{ev_gp:.2f}" if ev_gp is not None else "N/A",
                    "Fundamental_Metrics": "Revenue Growth, Net Margin, P/E, P/B, Dividend Yield",
                    "Cash_Position": "Free Cash Flow & Net Cash Adjustment included"
                }
                report = ae3.run_v3_specialized_report(ticker, "financial", str(f_payload), report_lang)
                st.session_state['v3_f'] = extract_v3_score(report)
                st.session_state['v3_f_text'] = report

    # --- 宏观与周期 ---
    with c3:
        if st.button(b3_text, width="stretch"):
            with st.spinner("Scanning Global Macro Radar..." if report_lang == "English" else "正在扫描全球宏观雷达..."):
                m_payload = {
                    "Ticker": ticker,
                    "VIX_Level": f"{current_vix:.2f}" if 'current_vix' in locals() else "N/A",
                    "DXY_Index": f"{dxy_val:.2f}" if 'dxy_val' in locals() else "N/A",
                    "Sector_Context": f"Analysis based on {ticker}'s industry specific cycle",
                    "Geopolitical_Risk_Level": "Medium-High (Supply Chain Focus)"
                }
                report = ae3.run_v3_specialized_report(ticker, "macro", str(m_payload), report_lang)
                st.session_state['v3_c'] = extract_v3_score(report)
                st.session_state['v3_c_text'] = report

    # --- 统一渲染展示区 ---
    if st.session_state['v3_t_text']:
        tech_title = f"### 📈 {ticker} Technical & Sentiment Analysis" if report_lang == "English" else f"### 📈 {ticker} 技术与情绪分析"
        st.markdown(tech_title)
        st.markdown(st.session_state['v3_t_text'])

    if st.session_state['v3_f_text']:
        fin_title = f"### 💰 {ticker} Financial & Strategic Base" if report_lang == "English" else f"### 💰 {ticker} 财务与战略底牌"
        st.markdown(fin_title)
        st.markdown(st.session_state['v3_f_text'])

    if st.session_state['v3_c_text']:
        macro_title = f"### 🌐 {ticker} Macro & Cycle Radar" if report_lang == "English" else f"### 🌐 {ticker} 宏观与周期雷达报告"
        st.markdown(macro_title)
        st.markdown(st.session_state['v3_c_text'])

    # --- 自动判词合成 ---
    if all(k in st.session_state for k in ['v3_t', 'v3_f', 'v3_c']):
        st.divider()
        t, f, c = st.session_state['v3_t'], st.session_state['v3_f'], st.session_state['v3_c']
        st.info(f"### {verdict_title} (Score: T:{t} | F:{f} | C:{c})")

        if report_lang == "中文":
            if f >= 8 and c >= 7 and t <= 4:
                st.success("**🔥 黄金坑**: 财务底牌厚且周期顺风，技术性恐慌提供了绝佳入场机会。")
            elif f >= 7 and c <= 4:
                st.warning("**⚠️ 估值陷阱**: 虽然便宜但处于周期下行期，警惕长期阴跌。")
            elif t >= 8 and f <= 5:
                st.error("**🚨 逻辑见顶**: 情绪过热且估值严重透支，建议逢高止盈。")
            else:
                st.write("**⚖️ 中性观察**: 各维度逻辑暂无共振，建议继续观望。")
        else:
            if f >= 8 and c >= 7 and t <= 4:
                st.success("**🔥 Golden Pit**: Strong financials & macro tailwinds. Technical panic offers a prime entry.")
            elif f >= 7 and c <= 4:
                st.warning("**⚠️ Value Trap**: Cheap on paper but facing macro headwinds. Beware of the 'bleed'.")
            elif t >= 8 and f <= 5:
                st.error("**🚨 Peak Logic**: Overheated sentiment & overstretched valuation. Consider profit-taking.")
            else:
                st.write("**⚖️ Neutral**: No convergence in logic; maintain observation.")

    # --- 综合决策看板 ---
    st.markdown("---")
    board_title = "🎯 综合决策与市场交叉参考" if report_lang == "中文" else "🎯 Consensus & Market Cross-Ref"
    st.subheader(board_title)

    t_score = st.session_state.get('v3_t', 5.0)
    f_score = st.session_state.get('v3_f', 5.0)
    m_score = st.session_state.get('v3_c', 5.0)
    avg_score = (t_score + f_score + m_score) / 3

    ratings_map = {
        "Strong Buy":  {"cn": "强烈推荐", "en": "Strong Buy",  "color": "#16a34a"},
        "Buy":         {"cn": "推荐买入", "en": "Buy",         "color": "#22c55e"},
        "Hold":        {"cn": "维持中性", "en": "Hold",        "color": "#eab308"},
        "Sell":        {"cn": "推荐卖出", "en": "Sell",        "color": "#ef4444"},
        "Strong Sell": {"cn": "强烈卖出", "en": "Strong Sell", "color": "#b91c1c"},
    }

    if avg_score >= 8.5:   res = ratings_map["Strong Buy"]
    elif avg_score >= 7.0: res = ratings_map["Buy"]
    elif avg_score >= 4.5: res = ratings_map["Hold"]
    elif avg_score >= 3.0: res = ratings_map["Sell"]
    else:                  res = ratings_map["Strong Sell"]

    final_rating_text = res["cn"] if report_lang == "中文" else res["en"]
    sub_text = f"AI Score: {avg_score:.1f}/10.0" if report_lang != "中文" else f"AI 综合评分: {avg_score:.1f}"

    market_ref = get_external_consensus(ticker)

    col_ai, col_mkt = st.columns(2)

    with col_ai:
        st.markdown(f"""
            <div style="background: linear-gradient(90deg, {res['color']} 0%, {res['color']}cc 100%);
                        padding: 12px 20px; border-radius: 8px; color: white; min-height: 80px;
                        display: flex; justify-content: space-between; align-items: center;">
                <div style="font-weight: 800; font-size: 1.4rem;">{final_rating_text}</div>
                <div style="font-size: 0.9rem; opacity: 0.9;">{sub_text}</div>
            </div>
        """, unsafe_allow_html=True)

    with col_mkt:
        m_color = "#16a34a" if "Buy" in market_ref['rating'] else "#eab308"
        m_rating_label = "MARKET CONSENSUS" if report_lang != "中文" else "华尔街市场共识"
        st.markdown(f"""
            <div style="border: 2px solid {m_color}; padding: 10px 20px; border-radius: 8px;
                        min-height: 80px; display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <div style="font-size: 0.7rem; color: #64748b;">{m_rating_label}</div>
                    <div style="font-weight: 800; font-size: 1.2rem; color: {m_color};">{market_ref['rating'].upper()}</div>
                </div>
                <div style="text-align: right; font-size: 0.85rem; color: #475569;">
                    Target: ${market_ref['target']:.2f}<br>
                    <span style="color:{m_color};">{market_ref['upside']:+.1f}% Upside</span>
                </div>
            </div>
        """, unsafe_allow_html=True)

    # --- FIX 2: 导出中心 — 与 col_ai/col_mkt 同级，正确缩进 ---
    st.markdown("---")
    export_title = "📥 报告导出中心" if report_lang == "中文" else "📥 Report Export Center"
    st.subheader(export_title)

    def create_markdown_report():
        date_now = datetime.now().strftime("%Y-%m-%d %H:%M")
        t_content = st.session_state.get('v3_t_text', "Analysis not performed / 未执行分析")
        f_content = st.session_state.get('v3_f_text', "Analysis not performed / 未执行分析")
        m_content = st.session_state.get('v3_c_text', "Analysis not performed / 未执行分析")

        if report_lang == "English":
            md = f"""# iMarket Pro Investment Brief: {ticker}
**Generation Time**: {date_now}
**Final Rating**: {final_rating_text} | **Consensus Score**: {avg_score:.1f}/10.0
**Market Target**: ${market_ref['target']:.2f} ({market_ref['upside']:+.1f}% Potential)

---
## 📈 Technical & Sentiment Analysis
{t_content}

---
## 💰 Financial & Strategic Base
{f_content}

---
## 🌐 Macro & Cycle Radar
{m_content}

---
*Disclaimer: Generated by iMarket Pro AI Engine. For research purposes only.*
"""
        else:
            md = f"""# iMarket Pro 投资研报：{ticker}
**生成时间**: {date_now}
**最终评级**: {final_rating_text} | **综合评分**: {avg_score:.1f}/10.0
**华尔街目标价**: ${market_ref['target']:.2f} (预期空间: {market_ref['upside']:+.1f}%)

---
## 📈 技术与情绪分析
{t_content}

---
## 💰 财务与战略底牌
{f_content}

---
## 🌐 宏观与周期雷达
{m_content}

---
*免责声明：由 iMarket Pro AI 引擎生成，仅供研究参考，不构成投资建议。*
"""
        return md

    full_report_md = create_markdown_report()
    file_name = f"iMarket_{ticker}_{datetime.now().strftime('%Y%m%d_%H%M')}.md"

    st.download_button(
        label="⬇️ 点击导出完整研究简报 (Markdown)" if report_lang == "中文" else "⬇️ Download Full Brief (MD)",
        data=full_report_md,
        file_name=file_name,
        mime="text/markdown",
        width="stretch"
    )

    if report_lang == "中文":
        st.caption("💡 提示：下载前先运行上面 3 个报告，Markdown 文件可使用 Typora, Obsidian 或 VS Code 打开，也可在浏览器中打印存为 PDF。")
    else:
        st.caption("💡 Hint: Run above 3 reports before download. Open MD files with Typora, Obsidian, or VS Code; or use 'Print to PDF' in your browser.")

    # --- 估值模型解读 ---
    with st.expander("📖 核心估值模型深度解读：DCF 与 企业价值倍数" if report_lang == "中文" else "📖 Deep Dive: DCF & Valuation Multiples"):
        if report_lang == "中文":
            st.markdown("""
            ### 1. DCF (贴现现金流) - 寻找内在价值
            * **原理**：DCF 认为公司现在的价值等于它未来能赚到的所有钱"折现"到今天的总和。
            * **高折现率策略**：本系统默认采用 **15% 折现率**。这是一个极度保守的"滤网"，只有当股价远低于这个标准时，才具有真正的**安全边际**。

            ### 2. EV/Sales (企业价值/销售额) - 规模与定价权
            * **逻辑**：相比 P/S，EV 考虑了公司的负债。
            * **判读**：如果该指标显著低于行业平均，可能存在**低估**；如果极高且缺乏增长支撑，则是**估值泡沫**。

            ### 3. EV/Gross Profit (企业价值/毛利) - 护城河指标
            * **核心**：这是衡量 AI 与软件公司最硬核的指标。它反映了公司每 1 元毛利在市场上被赋予的溢价。
            * **百分位意义**：查看当前倍数在过去 5 年的位置。处于 **20% 分位以下** 通常意味着处于"历史性底部"。
            """)
        else:
            st.markdown("""
            ### 1. DCF (Discounted Cash Flow) - The Intrinsic Value
            * **Principle**: DCF posits that a company is worth the sum of all its future cash flows, brought back to present value.
            * **High Discount Rate**: We use a **15% Discount Rate** by default. This acts as a conservative filter, ensuring a significant **Margin of Safety**.

            ### 2. EV/Sales - Scale & Pricing Power
            * **Logic**: Unlike P/S, EV (Enterprise Value) accounts for the company's debt and cash levels.
            * **Interpretation**: Significantly lower than industry average suggests **undervaluation**; excessively high suggests a **valuation bubble**.

            ### 3. EV/Gross Profit - The Moat Metric
            * **Core**: The ultimate metric for AI & SaaS firms. It shows the premium the market pays for every $1 of gross profit.
            * **Percentile**: Metrics below the **20th percentile** over 5 years often indicate a "Historical Floor."
            """)

    with st.expander("💡 进阶指南：如何区分"黄金坑"与"估值陷阱"" if report_lang == "中文" else "💡 Advanced Guide: Golden Pit vs. Value Trap"):
        if report_lang == "中文":
            st.info("""
            **🔍 识别黄金坑 (Golden Pit)**
            - **指标**：DCF 空间 > 20% 且 EV/GP 处于历史低位。
            - **信号**：AI 报告中提到"利空出尽"、"基本面改善"或"机构暗中吸筹"。

            **⚠️ 警惕估值陷阱 (Value Trap)**
            - **指标**：估值看起来极低，但 DCF 计算显示未来现金流正在萎缩。
            - **信号**：新闻中频繁出现"裁员"、"核心技术流失"或"法律诉讼"。
            """)
        else:
            st.info("""
            **🔍 Identifying a Golden Pit**
            - **Metrics**: DCF Upside > 20% and EV/GP at historical lows.
            - **Signals**: AI report mentions "Negative news priced in" or "Fundamental turnaround."

            **⚠️ Beware of Value Traps**
            - **Metrics**: Ratios look cheap, but DCF reveals shrinking future cash flows.
            - **Signals**: Frequent news regarding "Layoffs," "Loss of key talent," or "Litigation."
            """)

    # --- News Module ---
    st.divider()
    st.subheader(f"📰 {ticker} English Market News")

    @st.cache_data(ttl=600)
    def fetch_2026_news(symbol):
        news_items = []
        try:
            raw_yf = yf.Ticker(symbol).news
            for item in raw_yf[:5]:
                title = item.get('title') or item.get('headline') or (item.get('content', {}).get('title')) or "News Update"
                link = item.get('link') or item.get('url') or "https://finance.yahoo.com"
                ts = item.get('providerPublishTime') or item.get('pubDate')
                p_time = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M') if isinstance(ts, int) else "Recently"
                news_items.append({'title': title, 'link': link, 'source': item.get('publisher') or "Yahoo", 'time': p_time})
        except: pass

        try:
            # FIX 3: 修复 Google News RSS URL 拼接
            safe_q = urllib.parse.quote(f"{symbol} stock")
            rss_url = f"https://news.google.com/rss/search?q={safe_q}&hl=en-US&gl=US&ceid=US:en"
            feed = feedparser.parse(rss_url)
            for e in feed.entries[:5]:
                news_items.append({
                    'title': e.title,
                    'link': e.link,
                    'source': getattr(e, 'source', {}).get('title', 'Google News'),
                    'time': e.published
                })
        except: pass

        return news_items

    final_news = fetch_2026_news(ticker)
    if final_news:
        for item in final_news:
            with st.container():
                st.markdown(f"**[{item['title']}]({item['link']})**")
                st.caption(f"{item['source']} | {item['time']}")
                st.write("---")
    else:
        st.error("❌ Failed to retrieve news. Run: `pip install -U yfinance`.")

else:
    st.error("❌ Data Fetch Failed. Check connection or Ticker.")
