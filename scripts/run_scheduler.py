import time

from app.db.session import create_db_and_tables
from app.jobs.scheduler import build_scheduler


def main() -> None:
    create_db_and_tables()
    scheduler = build_scheduler()
    scheduler.start()
    print("Scheduler started. Registered jobs:", flush=True)
    for job in scheduler.get_jobs():
        next_run_time = job.next_run_time.isoformat() if job.next_run_time else "n/a"
        print(f"- {job.id}: next run at {next_run_time}", flush=True)

    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        scheduler.shutdown(wait=False)
        print("Scheduler stopped.", flush=True)


if __name__ == "__main__":
    main()
