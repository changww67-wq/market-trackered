import sqlite3
import pandas as pd
import yfinance as yf
import feedparser
from datetime import datetime
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# 1. 화면 렌더링 최우선 
st.set_page_config(page_title="글로벌 증시 모니터", layout="wide", page_icon="📈")
st.title("🌐 글로벌 증시 실시간 대시보드")
st.caption("미국/한국 주요 기업 시세, 환율 및 뉴스 통합 피드")

DB_PATH = "market_data.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS stock_prices (ticker TEXT, name TEXT, market TEXT, price REAL, change_pct REAL, updated_at TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS market_news (title TEXT, link TEXT, source TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS earnings (ticker TEXT, name TEXT, date TEXT)")
    conn.commit()
    conn.close()

def fetch_market_data():
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        t = yf.Ticker("KRW=X")
        p = t.fast_info.last_price
        prev = t.fast_info.previous_close
        pct = ((p - prev) / prev * 100) if prev else 0.0
        c.execute("INSERT INTO stock_prices VALUES (?, ?, 'FX', ?, ?, ?)", ("USD/KRW", "원/달러 환율", p, round(pct, 2), now))
    except: pass

    us_stocks = {"AAPL": "Apple", "MSFT": "Microsoft", "NVDA": "NVIDIA", "TSLA": "Tesla", "AMD": "AMD", "IONQ": "IonQ"}
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
                if dates: c.execute("INSERT INTO earnings VALUES (?, ?, ?)", (sym, name, str(dates[0]).split(" ")[0]))
        except: pass

    crypto_assets = {"BTC-USD": "비트코인", "ETH-USD": "이더리움", "SOL-USD": "솔라나"}
    for sym, name in crypto_assets.items():
        try:
            t = yf.Ticker(sym)
            p = t.fast_info.last_price
            prev = t.fast_info.previous_close
            pct = ((p - prev) / prev * 100) if prev else 0.0
            c.execute("INSERT INTO stock_prices VALUES (?, ?, 'CRYPTO', ?, ?, ?)", (sym, name, p, round(pct, 2), now))
        except: pass

    kr_stocks = {"005930.KS": "삼성전자", "000660.KS": "SK하이닉스", "035420.KS": "NAVER", "005380.KS": "현대차"}
    for sym, name in kr_stocks.items():
        try:
            t = yf.Ticker(sym)
            p = t.fast_info.last_price
            prev = t.fast_info.previous_close
            pct = ((p - prev) / prev * 100) if prev else 0.0
            c.execute("INSERT INTO stock_prices VALUES (?, ?, 'KR', ?, ?, ?)", (sym.replace(".KS", ""), name, p, round(pct, 2), now))
        except: pass

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

st.sidebar.header("⚙️ 컨트롤 패널")
if st.sidebar.button("🔄 즉시 데이터 수집/갱신"):
    with st.spinner("전세계 증시 데이터를 끌어오는 중입니다..."):
        fetch_market_data()
    st.sidebar.success("수집 완료!")
    st.rerun()

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

    fx_df = current_stocks[current_stocks['market'] == 'FX']
    fx_rate = 1350.0  
    if not fx_df.empty:
        fx_row = fx_df.iloc[0]
        fx_rate = fx_row['price']
        st.metric(label="💵 현재 원/달러 환율", value=f"{fx_rate:,.2f} 원", delta=f"{fx_row['change_pct']}%")
        st.divider()

    st.subheader("📊 주요 기업 시세")
    
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
        tmp = tmp[['ticker', 'name', '현재가', '원화 환산가', 'change_pct']]
        tmp = tmp.rename(columns={'ticker': '티커', 'name': '종목명', 'change_pct': '등락률(%)'})
        return tmp

    t1, t2, t3 = st.tabs(["🇺🇸 미국 증시", "🇰🇷 한국 증시", "🪙 암호화폐"])
    with t1: st.dataframe(format_table(current_stocks, 'US'), use_container_width=True)
    with t2: st.dataframe(format_table(current_stocks, 'KR'), use_container_width=True)
    with t3: st.dataframe(format_table(current_stocks, 'CRYPTO'), use_container_width=True)
    
    st.divider()

    # ---------------------------------------------------------
    # [새로 추가됨] 전문가용 비교 차트 뷰어 (캔들스틱 + 이평선 + RSI)
    # ---------------------------------------------------------
    st.subheader("📈 실시간 차트 분석 (캔들스틱 & RSI)")
    
    chart_options = [f"{row['name']} ({row['ticker']})" for _, row in current_stocks.iterrows() if row['market'] != 'FX']
    
    if chart_options:
        chart_type = st.radio("차트 주기", ["일봉 (Daily)", "월봉 (Monthly)"], horizontal=True)
        
        # 화면을 정확히 2개로 나누기 (비교 분석용)
        col1, col2 = st.columns(2)
        
        # RSI 계산 함수 (14일 Wilders EMA 방식)
        def calculate_rsi(series, period=14):
            delta = series.diff()
            up = delta.clip(lower=0)
            down = -1 * delta.clip(upper=0)
            ema_up = up.ewm(com=period-1, adjust=False).mean()
            ema_down = down.ewm(com=period-1, adjust=False).mean()
            rs = ema_up / ema_down
            return 100 - (100 / (1 + rs))

        # 차트 그리기 전문 함수
        def draw_professional_chart(selected_option, container):
            selected_ticker = selected_option.split("(")[-1].replace(")", "")
            market_type = current_stocks[current_stocks['ticker'] == selected_ticker]['market'].values[0]
            yf_ticker = selected_ticker + ".KS" if market_type == 'KR' else selected_ticker

            with container:
                t = yf.Ticker(yf_ticker)
                if chart_type == "일봉 (Daily)":
                    hist = t.history(period="2y", interval="1d")
                    ma_label = "일선"
                    display_tail = 250
                else:
                    hist = t.history(period="15y", interval="1mo")
                    ma_label = "월선"
                    display_tail = 60

                if not hist.empty:
                    # 이평선 및 RSI 계산
                    hist[f'5{ma_label}'] = hist['Close'].rolling(5).mean()
                    hist[f'20{ma_label}'] = hist['Close'].rolling(20).mean()
                    hist[f'60{ma_label}'] = hist['Close'].rolling(60).mean()
                    hist[f'180{ma_label}'] = hist['Close'].rolling(180).mean()
                    hist['RSI'] = calculate_rsi(hist['Close'])
                    
                    hist = hist.tail(display_tail)

                    # 2층 구조 차트 만들기 (위: 캔들 / 아래: RSI)
                    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                                        vertical_spacing=0.05, row_heights=[0.7, 0.3])
                    
                    # 1. 캔들차트 (한국식 빨강/파랑 색상 적용)
                    fig.add_trace(go.Candlestick(x=hist.index, open=hist['Open'], high=hist['High'], low=hist['Low'], close=hist['Close'],
                                                 increasing_line_color='red', decreasing_line_color='blue', name='캔들'), row=1, col=1)
                    
                    # 2. 이동평균선
                    colors = ['orange', 'purple', 'green', 'black']
                    for idx, ma in enumerate(['5', '20', '60', '180']):
                        col_name = f"{ma}{ma_label}"
                        if col_name in hist.columns:
                            fig.add_trace(go.Scatter(x=hist.index, y=hist[col_name], mode='lines', 
                                                     name=col_name, line=dict(width=1.5, color=colors[idx])), row=1, col=1)
                            
                    # 3. RSI 차트
                    fig.add_trace(go.Scatter(x=hist.index, y=hist['RSI'], mode='lines', name='RSI', line=dict(color='magenta')), row=2, col=1)
                    # RSI 기준선 (30, 70)
                    fig.add_hline(y=70, line_dash="dash", line_color="gray", row=2, col=1)
                    fig.add_hline(y=30, line_dash="dash", line_color="gray", row=2, col=1)

                    fig.update_layout(xaxis_rangeslider_visible=False, height=550, margin=dict(l=0, r=0, t=10, b=0), showlegend=False)
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.warning("데이터를 불러올 수 없습니다.")

        # 좌측 차트
        with col1:
            sel1 = st.selectbox("비교 종목 1", chart_options, index=0)
            draw_professional_chart(sel1, st.container())
            
        # 우측 차트
        with col2:
            sel2 = st.selectbox("비교 종목 2", chart_options, index=1 if len(chart_options) > 1 else 0)
            draw_professional_chart(sel2, st.container())

    st.divider()

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
