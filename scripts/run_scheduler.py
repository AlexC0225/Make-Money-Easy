import time

from app.jobs.scheduler import build_scheduler


if __name__ == "__main__":
    scheduler = build_scheduler()
    scheduler.start()
    print("Scheduler started. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        scheduler.shutdown(wait=False)
        print("Scheduler stopped.")
