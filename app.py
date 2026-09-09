import sqlite3
import pandas as pd
import yfinance as yf
import feedparser
from datetime import datetime
import streamlit as st

# 1. 화면 렌더링 최우선 
st.set_page_config(page_title="글로벌 증시 모니터", layout="wide", page_icon="📈")
st.title("🌐 글로벌 증시 실시간 대시보드")
st.caption("미국/한국 주요 기업 시세 및 뉴스 통합 피드")

DB_PATH = "market_data.db"

# DB 초기화 세팅
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS stock_prices (ticker TEXT, name TEXT, market TEXT, price REAL, change_pct REAL, updated_at TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS market_news (title TEXT, link TEXT, source TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS earnings (ticker TEXT, name TEXT, date TEXT)")
    conn.commit()
    conn.close()

# 데이터 수집 (야후 파이낸스 통합)
def fetch_market_data():
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 1. 미국 주식 (US)
    us_stocks = {
        "AAPL": "Apple", "MSFT": "Microsoft", "NVDA": "NVIDIA", "TSLA": "Tesla",
        "AMD": "AMD", "IONQ": "IonQ"
    }
    for sym, name in us_stocks.items():
        try:
            t = yf.Ticker(sym)
            p = t.fast_info.last_price
            prev = t.fast_info.previous_close
            pct = ((p - prev) / prev * 100) if prev else 0.0
            c.execute("INSERT INTO stock_prices VALUES (?, ?, 'US', ?, ?, ?)", (sym, name, p, round(pct, 2), now))
        except: pass
            
        try:
            cal = t.calendar
            if cal is not None and not cal.empty and "Earnings Date" in cal.index:
                dates = cal.loc["Earnings Date"].dropna().tolist()
                if dates:
                    c.execute("INSERT INTO earnings VALUES (?, ?, ?)", (sym, name, str(dates[0]).split(" ")[0]))
        except: pass

    # 2. 암호화폐 (CRYPTO) - 완전히 분리된 그룹으로 수집
    crypto_assets = {
        "BTC-USD": "비트코인",
        "ETH-USD": "이더리움", 
        "SOL-USD": "솔라나"
    }
    for sym, name in crypto_assets.items():
        try:
            t = yf.Ticker(sym)
            p = t.fast_info.last_price
            prev = t.fast_info.previous_close
            pct = ((p - prev) / prev * 100) if prev else 0.0
            c.execute("INSERT INTO stock_prices VALUES (?, ?, 'CRYPTO', ?, ?, ?)", (sym, name, p, round(pct, 2), now))
        except: pass

    # 3. 한국 주식 (KR)
    kr_stocks = {"005930.KS": "삼성전자", "000660.KS": "SK하이닉스", "035420.KS": "NAVER", "005380.KS": "현대차"}
    for sym, name in kr_stocks.items():
        try:
            t = yf.Ticker(sym)
            p = t.fast_info.last_price
            prev = t.fast_info.previous_close
            pct = ((p - prev) / prev * 100) if prev else 0.0
            c.execute("INSERT INTO stock_prices VALUES (?, ?, 'KR', ?, ?, ?)", (sym.replace(".KS", ""), name, p, round(pct, 2), now))
        except: pass

    # 4. 뉴스 수집
    urls = [
        ("https://news.google.com/rss/search?q=증시&hl=ko&gl=KR&ceid=KR:ko", "국내증시"),
        ("https://finance.yahoo.com/news/rssindex", "Yahoo US")
    ]
    for url, src in urls:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:5]:
                c.execute("INSERT INTO market_news VALUES (?, ?, ?)", (entry.title, entry.link, src))
        except: pass
        
    conn.commit()
    conn.close()

# 사이드바 컨트롤
st.sidebar.header("⚙️ 컨트롤 패널")
if st.sidebar.button("🔄 즉시 데이터 수집/갱신"):
    with st.spinner("전세계 증시 데이터를 끌어오는 중입니다... (약 10초 소요)"):
        fetch_market_data()
    st.sidebar.success("수집 완료!")
    st.rerun()

# 화면 데이터 표시 로직
def load_df(query):
    try:
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df
    except:
        return pd.DataFrame()

stocks_df = load_df("SELECT * FROM stock_prices ORDER BY updated_at DESC")

if stocks_df.empty:
    st.info("👈 왼쪽 메뉴에서 '즉시 데이터 수집/갱신' 버튼을 눌러주세요. (최초 1회 데이터 수집 필요)")
else:
    latest_time = stocks_df['updated_at'].max()
    current_stocks = stocks_df[stocks_df['updated_at'] == latest_time]

    st.subheader("📊 주요 기업 시세")
    
    # 탭을 3개로 늘리고 데이터 분류 적용
    t1, t2, t3 = st.tabs(["🇺🇸 미국 증시", "🇰🇷 한국 증시", "🪙 암호화폐"])
    with t1: st.dataframe(current_stocks[current_stocks['market'] == 'US'], use_container_width=True)
    with t2: st.dataframe(current_stocks[current_stocks['market'] == 'KR'], use_container_width=True)
    with t3: st.dataframe(current_stocks[current_stocks['market'] == 'CRYPTO'], use_container_width=True)

    st.divider()
    c1, c2 = st.columns([1, 1])
    with c1:
        st.subheader("📅 실적 발표일")
        ear_df = load_df("SELECT DISTINCT ticker, name, date FROM earnings ORDER BY date ASC")
        if not ear_df.empty: st.dataframe(ear_df, use_container_width=True)
    with c2:
        st.subheader("📰 최신 뉴스")
        news_df = load_df("SELECT DISTINCT title, link, source FROM market_news LIMIT 10")
        for _, r in news_df.iterrows():
            st.markdown(f"**[{r['source']}]** [{r['title']}]({r['link']})")
