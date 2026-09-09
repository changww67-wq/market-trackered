import time
from apscheduler.schedulers.background import BackgroundScheduler
from collector import run_full_update

if __name__ == "__main__":
  # 최초 1회 즉각 실행
  run_full_update()

  scheduler = BackgroundScheduler()
  # 매일 한국 장 시작 전(08:30) 및 미국 장 마감 후(06:30) 자동 실행 등록
  scheduler.add_job(run_full_update, "cron", hour=6, minute=30)
  scheduler.add_job(run_full_update, "cron", hour=8, minute=30)
  scheduler.add_job(run_full_update, "cron", hour=16, minute=0)  # 국장 마감 후

  # 1시간마다 실시간 뉴스 갱신
  scheduler.add_job(run_full_update, "interval", hours=1)

  scheduler.start()
  print("Scheduler active. Press Ctrl+C to exit.")

  try:
    while True:
      time.sleep(60)
  except (KeyboardInterrupt, SystemExit):
    scheduler.shutdown()