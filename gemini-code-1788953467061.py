import sqlite3
from collector import DB_PATH, run_full_update
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="글로벌 증시 & 실적 모니터", layout="wide", page_icon="📈"
)

st.title("🌐 글로벌 증시 실시간 대시보드")
st.caption("미국/한국 주요 기업 시세, 어닝 캘린더, 실시간 금융 뉴스 통합 피드")

# 수동 새로고침 버튼
if st.sidebar.button("🔄 지금 즉각 데이터 갱신"):
  with st.spinner("최신 데이터를 가져오는 중입니다..."):
    run_full_update()
  st.sidebar.success("갱신 완료!")


def load_data(query):
  conn = sqlite3.connect(DB_PATH)
  df = pd.read_sql_query(query, conn)
  conn.close()
  return df


# 1. 시세 요약 카드
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
          label=f"{row['name']} ({row['ticker']})",
          value=f"{row['price']:,} {unit}",
          delta=f"{row['change_pct']}%",
      )

  # 전체 종목 표 탭 분리
  tab_us, tab_kr = st.tabs(["🇺🇸 미국 증시", "🇰🇷 한국 증시"])
  with tab_us:
    st.dataframe(
        stocks_df[stocks_df["market"] == "US"], use_container_width=True
    )
  with tab_kr:
    st.dataframe(
        stocks_df[stocks_df["market"] == "KR"], use_container_width=True
    )
else:
  st.info(
      "시세 데이터가 비어 있습니다. 사이드바의 갱신 버튼을 눌러주세요."
  )

st.divider()

# 2. 기업 실적 발표일(Earnings Calendar) & 뉴스 2분할 레이아웃
col_cal, col_news = st.columns([1, 1])

with col_cal:
  st.subheader("📅 주요 기업 실적 발표 캘린더")
  cal_df = load_data(
      "SELECT ticker, name, earnings_date FROM earnings_calendar ORDER BY"
      " earnings_date ASC"
  )
  if not cal_df.empty:
    st.dataframe(
        cal_df.rename(
            columns={
                "ticker": "티커",
                "name": "종목명",
                "earnings_date": "실적 발표 예정일",
            }
        ),
        use_container_width=True,
    )
  else:
    st.info("예정된 실적 발표 일정 데이터가 없습니다.")

with col_news:
  st.subheader("📰 실시간 시장 뉴스 피드")
  news_df = load_data(
      "SELECT title, link, published, source FROM market_news ORDER BY rowid"
      " DESC LIMIT 15"
  )
  if not news_df.empty:
    for _, row in news_df.iterrows():
      st.markdown(
          f"**[{row['source']}]** [{row['title']}]({row['link']})  \n"
          f"<span style='color:gray; font-size:0.8em;'>{row['published']}</span>",
          unsafe_allow_html=True,
      )
      st.write("")
  else:
    st.info("최신 뉴스를 불러오는 중입니다.")