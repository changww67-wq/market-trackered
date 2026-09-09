import sqlite3
import pandas as pd
import yfinance as yf
import feedparser
from datetime import datetime
import streamlit as st

# 1. 화면 렌더링 최우선 
st.set_page_config(page_title="글로벌 증시 모니터", layout="wide", page_icon="📈")
st.title("🌐 글로벌 증시 실시간 대시보드")
st.caption("미국/한국 주요 기업 시세, 환율 및 뉴스 통합 피드")

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

    # 0. 실시간 원/달러 환율 수집
    try:
        t = yf.Ticker("KRW=X")
        p = t.fast_info.last_price
        prev = t.fast_info.previous_close
        pct = ((p - prev) / prev * 100) if prev else 0.0
        c.execute("INSERT INTO stock_prices VALUES (?, ?, 'FX', ?, ?, ?)", ("USD/KRW", "원/달러 환율", p, round(pct, 2), now))
    except: pass

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
            
            cal = t.calendar
            if cal is not None and not cal.empty and "Earnings Date" in cal.index:
                dates = cal.loc["Earnings Date"].dropna().tolist()
                if dates:
                    c.execute("INSERT INTO earnings VALUES (?, ?, ?)", (sym, name, str(dates[0]).split(" ")[0]))
        except: pass

    # 2. 암호화폐 (CRYPTO)
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

# DB 불러오기 함수
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

    # 맨 위에 환율 정보 표시
    fx_df = current_stocks[current_stocks['market'] == 'FX']
    fx_rate = 1350.0  # 환율 데이터를 못 가져왔을 때의 기본값
    if not fx_df.empty:
        fx_row = fx_df.iloc[0]
        fx_rate = fx_row['price']
        st.metric(label="💵 현재 원/달러 환율", value=f"{fx_rate:,.2f} 원", delta=f"{fx_row['change_pct']}%")
        st.divider()

    st.subheader("📊 주요 기업 시세")
    
    # ---------------------------------------------------------
    # [수정됨] 표 데이터 정리 (한글화 및 원화 환산가 추가)
    # ---------------------------------------------------------
    def format_table(df, market_type):
        tmp = df[df['market'] == market_type].copy()
        prices = []
        krw_prices = []
        
        for _, row in tmp.iterrows():
            if market_type in ['US', 'CRYPTO']:
                prices.append(f"${row['price']:,.2f}")
                krw_prices.append(f"{row['price'] * fx_rate:,.0f} 원")
            else:
                prices.append(f"{row['price']:,.0f} 원")
                krw_prices.append(f"{row['price']:,.0f} 원")
                
        tmp['현재가'] = prices
        tmp['원화 환산가'] = krw_prices
        
        # 영어 컬럼명을 한글로 변경
        tmp = tmp[['ticker', 'name', '현재가', '원화 환산가', 'change_pct']]
        tmp = tmp.rename(columns={
            'ticker': '티커',
            'name': '종목명',
            'change_pct': '등락률(%)'
        })
        return tmp

    t1, t2, t3 = st.tabs(["🇺🇸 미국 증시", "🇰🇷 한국 증시", "🪙 암호화폐"])
    with t1: st.dataframe(format_table(current_stocks, 'US'), use_container_width=True)
    with t2: st.dataframe(format_table(current_stocks, 'KR'), use_container_width=True)
    with t3: st.dataframe(format_table(current_stocks, 'CRYPTO'), use_container_width=True)
    
    st.divider()

    # ---------------------------------------------------------
    # [새로 추가됨] 종목별 상세 차트 뷰어 (이동평균선 포함)
    # ---------------------------------------------------------
    st.subheader("📈 실시간 차트 뷰어 (이동평균선)")
    
    # 환율(FX)을 제외한 모든 종목을 선택창에 표시
    chart_options = [f"{row['name']} ({row['ticker']})" for _, row in current_stocks.iterrows() if row['market'] != 'FX']
    
    if chart_options:
        c1, c2 = st.columns([2, 1])
        with c1:
            selected_option = st.selectbox("차트를 분석할 종목을 선택하세요", chart_options)
        with c2:
            chart_type = st.radio("차트 주기", ["일봉 (Daily)", "월봉 (Monthly)"], horizontal=True)

        # 선택된 종목의 티커(Ticker)만 추출
        selected_ticker = selected_option.split("(")[-1].replace(")", "")
        market_type = current_stocks[current_stocks['ticker'] == selected_ticker]['market'].values[0]
        
        # 한국 주식은 야후 파이낸스 조회를 위해 '.KS'를 붙여줌
        yf_ticker = selected_ticker + ".KS" if market_type == 'KR' else selected_ticker

        with st.spinner("차트 데이터를 계산하는 중입니다..."):
            try:
                t = yf.Ticker(yf_ticker)
                
                # 180일/월선을 계산하기 위해 데이터를 넉넉히 가져옵니다
                if chart_type == "일봉 (Daily)":
                    hist = t.history(period="2y", interval="1d")
                    ma_label = "일선"
                else:
                    hist = t.history(period="15y", interval="1mo")
                    ma_label = "월선"

                if not hist.empty:
                    # 5, 20, 60, 180 이동평균선 계산
                    hist[f'5{ma_label}'] = hist['Close'].rolling(5).mean()
                    hist[f'20{ma_label}'] = hist['Close'].rolling(20).mean()
                    hist[f'60{ma_label}'] = hist['Close'].rolling(60).mean()
                    hist[f'180{ma_label}'] = hist['Close'].rolling(180).mean()
                    
                    # 보여줄 때는 최근 1년(일봉) / 최근 5년(월봉) 치만 자름
                    if chart_type == "일봉 (Daily)":
                        hist = hist.tail(250)
                    else:
                        hist = hist.tail(60)

                    # 차트에 그릴 데이터만 추려서 이름 변경
                    chart_data = hist[['Close', f'5{ma_label}', f'20{ma_label}', f'60{ma_label}', f'180{ma_label}']].copy()
                    chart_data.rename(columns={'Close': '종가'}, inplace=True)
                    
                    # 선 굵기와 색상 자동 최적화
                    st.line_chart(chart_data)
                else:
                    st.warning("차트 데이터를 불러올 수 없습니다.")
            except Exception as e:
                st.error("차트 생성 중 오류가 발생했습니다.")
                
    st.divider()

    # 실적 & 뉴스
    c1, c2 = st.columns([1, 1])
    with c1:
        st.subheader("📅 실적 발표일")
        ear_df = load_df("SELECT DISTINCT ticker, name, date FROM earnings ORDER BY date ASC")
        if not ear_df.empty: 
            ear_df = ear_df.rename(columns={'ticker': '티커', 'name': '종목명', 'date': '발표예정일'})
            st.dataframe(ear_df, use_container_width=True)
    with c2:
        st.subheader("📰 최신 뉴스")
        news_df = load_df("SELECT DISTINCT title, link, source FROM market_news LIMIT 10")
        for _, r in news_df.iterrows():
            st.markdown(f"**[{r['source']}]** [{r['title']}]({r['link']})")
