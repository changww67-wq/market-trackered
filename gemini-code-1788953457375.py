import sqlite3
from datetime import datetime
import feedparser
import pandas as pd
from pykrx import stock
import yfinance as yf

DB_PATH = "market_data.db"


def init_db():
  """데이터 저장을 위한 테이블 생성"""
  conn = sqlite3.connect(DB_PATH)
  cursor = conn.cursor()

  # 1. 주식 시세 테이블
  cursor.execute("""
    CREATE TABLE IF NOT EXISTS stock_prices (
        ticker TEXT,
        name TEXT,
        market TEXT,
        price REAL,
        change_pct REAL,
        updated_at TEXT,
        PRIMARY KEY (ticker, updated_at)
    )
    """)

  # 2. 실적 발표 일정 테이블
  cursor.execute("""
    CREATE TABLE IF NOT EXISTS earnings_calendar (
        ticker TEXT,
        name TEXT,
        earnings_date TEXT,
        eps_estimate REAL,
        PRIMARY KEY (ticker, earnings_date)
    )
    """)

  # 3. 증시 뉴스 테이블
  cursor.execute("""
    CREATE TABLE IF NOT EXISTS market_news (
        title TEXT UNIQUE,
        link TEXT,
        published TEXT,
        source TEXT
    )
    """)
  conn.commit()
  conn.close()


def update_us_stocks(tickers=["AAPL", "MSFT", "NVDA", "TSLA", "GOOGL"]):
  """미국 주식 시세 및 실적 발표일 수집"""
  conn = sqlite3.connect(DB_PATH)
  cursor = conn.cursor()
  now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

  for sym in tickers:
    try:
      t = yf.Ticker(sym)
      info = t.fast_info
      price = info.last_price
      prev_close = info.previous_close
      change_pct = (
          ((price - prev_close) / prev_close * 100) if prev_close else 0.0
      )
      name = sym

      cursor.execute(
          """
            INSERT OR REPLACE INTO stock_prices (ticker, name, market, price, change_pct, updated_at)
            VALUES (?, ?, 'US', ?, ?, ?)
            """,
          (sym, name, round(price, 2), round(change_pct, 2), now_str),
      )

      # 실적 발표 캘린더 수집
      cal = t.calendar
      if cal is not None and not cal.empty:
        # yfinance 반환 포맷에 맞춘 날짜 추출
        if "Earnings Date" in cal.index:
          dates = cal.loc["Earnings Date"].dropna().tolist()
          if dates:
            e_date = str(dates[0]).split(" ")[0]
            cursor.execute(
                """
                        INSERT OR REPLACE INTO earnings_calendar (ticker, name, earnings_date, eps_estimate)
                        VALUES (?, ?, ?, NULL)
                        """,
                (sym, name, e_date),
            )
    except Exception as e:
      print(f"US Data Error ({sym}): {e}")

  conn.commit()
  conn.close()


def update_kr_stocks(
    tickers={"005930": "삼성전자", "000660": "SK하이닉스", "035420": "NAVER"}
):
  """한국 주식 시세 수집 (pykrx)"""
  conn = sqlite3.connect(DB_PATH)
  cursor = conn.cursor()
  today = datetime.now().strftime("%Y%m%d")
  now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

  for code, name in tickers.items():
    try:
      df = stock.get_market_ohlcv_by_date(today, today, code)
      if df.empty:
        # 장 시작 전이거나 휴일이면 최근 5일 데이터 조회
        df = stock.get_market_ohlcv_by_date(
            (datetime.now() - pd.Timedelta(days=5)).strftime("%Y%m%d"),
            today,
            code,
        )

      if not df.empty:
        latest = df.iloc[-1]
        price = float(latest["종가"])
        change_pct = float(latest["등락률"])

        cursor.execute(
            """
                INSERT OR REPLACE INTO stock_prices (ticker, name, market, price, change_pct, updated_at)
                VALUES (?, ?, 'KR', ?, ?, ?)
                """,
            (code, name, price, change_pct, now_str),
        )
    except Exception as e:
      print(f"KR Data Error ({code}): {e}")

  conn.commit()
  conn.close()


def update_news():
  """글로벌/국내 증시 실시간 RSS 뉴스 수집"""
  rss_urls = [
      (
          "https://news.google.com/rss/search?q=증시+OR+실적발표&hl=ko&gl=KR&ceid=KR:ko",
          "국내증시",
      ),
      ("https://finance.yahoo.com/news/rssindex", "Yahoo Finance US"),
  ]

  conn = sqlite3.connect(DB_PATH)
  cursor = conn.cursor()

  for url, source in rss_urls:
    feed = feedparser.parse(url)
    for entry in feed.entries[:10]:  # 최신 10건씩
      title = entry.title
      link = entry.link
      published = getattr(
          entry, "published", datetime.now().strftime("%Y-%m-%d")
      )

      cursor.execute(
          """
            INSERT OR IGNORE INTO market_news (title, link, published, source)
            VALUES (?, ?, ?, ?)
            """,
          (title, link, published, source),
      )

  conn.commit()
  conn.close()


def run_full_update():
  """전체 데이터 일괄 갱신"""
  print(f"[{datetime.now()}] Updating market data...")
  init_db()
  update_us_stocks()
  update_kr_stocks()
  update_news()
  print("Update complete.")


if __name__ == "__main__":
  run_full_update()