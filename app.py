import sqlite3
from datetime import datetime
import feedparser
import pandas as pd
from pykrx import stock
import yfinance as yf
import streamlit as st

# ---------------------------------------------------------
# 1. 백엔드: 데이터 수집 및 DB 관리 기능
# ---------------------------------------------------------
DB_PATH = "market_data.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stock_prices (
            ticker TEXT, name TEXT, market TEXT, price REAL, change_pct REAL, updated_at TEXT,
            PRIMARY KEY (ticker, updated_at)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS earnings_calendar (
            ticker TEXT, name TEXT, earnings_date TEXT, eps_estimate REAL,
            PRIMARY KEY (ticker, earnings_date)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS market_news (
            title TEXT UNIQUE, link TEXT, published TEXT, source TEXT
        )
    """)
    conn.commit()
    conn.close()

def update_us_stocks(tickers=["AAPL", "MSFT", "NVDA", "TSLA", "GOOGL", "AMD"]):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for sym in tickers:
        try:
            t = yf.Ticker(sym)
            info = t.fast_info
            price = info.last_price
            prev_close = info.previous_close
            change_pct = (((price - prev_close) / prev_close * 100) if prev_close else 0.0)
            
            cursor.execute(
                "INSERT OR REPLACE INTO stock_prices (ticker, name, market, price, change_pct, updated_at) VALUES (?, ?, 'US', ?, ?, ?)",
                (sym, sym, round(price, 2), round(change_pct, 2), now_str)
            )

            cal = t.calendar
            if cal is not None and not cal.empty and "Earnings Date" in cal.index:
                dates = cal.loc["Earnings Date"].dropna().tolist()
                if dates:
                    e_date = str(dates[0]).split(" ")[0]
                    cursor.execute(
                        "INSERT OR REPLACE INTO earnings_calendar (ticker, name, earnings_date, eps_estimate) VALUES (?, ?, ?, NULL)",
                        (sym, sym, e_date)
                    )
        except Exception:
            pass
    conn.commit()
    conn.close()

def update_kr_stocks(tickers={"005930": "삼성전자", "000660": "SK하이닉스", "035420": "NAVER", "005380": "현대차"}):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    today = datetime.now().strftime("%Y%m%d")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for code, name in tickers.items():
        try:
            df = stock.get_market_ohlcv_by_date(today, today, code)
            if df.empty: 
                df = stock.get_market_ohlcv_by_date((datetime.now() - pd.Timedelta(days=5)).strftime("%Y%m%d"), today, code)
            if not df.empty:
                latest = df.iloc[-1]
                price = float(latest["종가"])
                change_pct = float(latest["등락률"])
                cursor.execute(
                    "INSERT OR REPLACE INTO stock_prices (ticker, name, market, price, change_pct, updated_at) VALUES (?, ?, 'KR', ?, ?, ?)",
                    (code, name, price, change_pct, now_str)
                )
        except Exception:
            pass
    conn.commit()
    conn.close()

def update_news():
    rss_urls = [
        ("https://news.google.com/rss/search?q=증시+OR+실적발표&hl=ko&gl=KR&ceid=KR:ko", "국내증시"),
        ("https://finance.yahoo.com/news/rssindex", "Yahoo Finance US"),
    ]
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    for url, source in rss_urls:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:10]:
                title = entry.title
                link = entry.link
                published = getattr(entry, "published", datetime.now().strftime("%Y-%m-%d"))
                cursor.execute(
                    "INSERT OR IGNORE INTO market_news (title, link, published, source) VALUES (?, ?, ?, ?)",
                    (title, link, published, source)
                )
        except Exception:
            pass
    conn.commit()
    conn.close()

def run_full_update():
    init_db()
    update_us_stocks()
    update_kr_stocks()
    update_news()

def load_data(query):
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql_query(query, conn)
    except Exception:
        df = pd.DataFrame()
    conn.close()
    return df

# ---------------------------------------------------------
# 2. 프론트엔드: Streamlit UI
# ---------------------------------------------------------
st.set_page_config(page_title="글로벌 증시 & 실적 모니터", layout="wide", page_icon="📈")
st.title("🌐 글로벌 증시 실시간 대시보드")

# 최초 접속 시 DB가 없으면 자동 생성 및 수집 (추적 모드)
try:
    load_data("SELECT 1 FROM stock_prices")
except Exception:
    st.error("🚀 최초 데이터 수집을 시작합니다. 화면에서 어느 구간이 멈추는지 확인해 주세요!")
    
    st.write("👉 1/4: 데이터베이스 세팅 중...")
    init_db()
    st.success("✅ DB 세팅 완료")
    
    st.write("👉 2/4: 🇺🇸 미국 주식 데이터 가져오는 중... (여기서 멈추면 야후 차단)")
    update_us_stocks()
    st.success("✅ 미국 주식 완료")
    
    st.write("👉 3/4: 🇰🇷 한국 주식 데이터 가져오는 중... (여기서 멈추면 한국거래소 차단)")
    update_kr_stocks()
    st.success("✅ 한국 주식 완료")
    
    st.write("👉 4/4: 📰 실시간 뉴스 가져오는 중...")
    update_news()
    st.success("✅ 뉴스 완료")
    
    st.info("🎉 모든 수집이 완료되었습니다! 화면을 새로고침(F5) 해주세요.")
    st.stop()

# 새로고침 버튼
if st.sidebar.button("🔄 지금 즉각 데이터 갱신"):
    with st.spinner("최신 데이터를 가져오는 중입니다..."):
        run_full_update()
    st.rerun()

# 시세 섹션
st.subheader("📊 주요 종목 현황")
stocks_df = load_data("""
    SELECT ticker, name, market, price, change_pct, updated_at 
    FROM stock_prices 
    WHERE updated_at = (SELECT MAX(updated_at) FROM stock_prices)
""")

if not stocks_df.empty:
    cols = st.columns(min(len(stocks_df), 5))
    for idx, row in stocks_df.head(5).iterrows():
        with cols[idx % 5]:
            unit = "$" if row["market"] == "US" else "원"
            st.metric(
                label=f"{row['name']}",
                value=f"{row['price']:,} {unit}",
                delta=f"{row['change_pct']}%",
            )
    
    tab_us, tab_kr = st.tabs(["🇺🇸 미국 증시", "🇰🇷 한국 증시"])
    with tab_us:
        st.dataframe(stocks_df[stocks_df["market"] == "US"], use_container_width=True)
    with tab_kr:
        st.dataframe(stocks_df[stocks_df["market"] == "KR"], use_container_width=True)
else:
    st.info("시세 데이터가 없습니다. 좌측 메뉴에서 데이터 갱신을 눌러주세요.")

st.divider()

# 실적 캘린더 & 뉴스 섹션
col_cal, col_news = st.columns([1, 1])

with col_cal:
    st.subheader("📅 주요 기업 실적 발표일")
    cal_df = load_data("SELECT ticker, name, earnings_date FROM earnings_calendar ORDER BY earnings_date ASC")
    if not cal_df.empty:
        st.dataframe(cal_df.rename(columns={"ticker": "티커", "name": "종목명", "earnings_date": "발표예정일"}), use_container_width=True)

with col_news:
    st.subheader("📰 실시간 시장 뉴스 피드")
    news_df = load_data("SELECT title, link, published, source FROM market_news ORDER BY rowid DESC LIMIT 10")
    if not news_df.empty:
        for _, row in news_df.iterrows():
            st.markdown(f"**[{row['source']}]** [{row['title']}]({row['link']})")
