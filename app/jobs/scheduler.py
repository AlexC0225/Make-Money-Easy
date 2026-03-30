from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import get_settings
from app.jobs.run_automation import run_daily_workspace_automation_job
from app.jobs.sync_stocks import run_sync_stocks_job
from app.jobs.sync_workspace_data import run_close_sync_workspace_data_job


def build_scheduler() -> BackgroundScheduler:
    settings = get_settings()
    scheduler = BackgroundScheduler(timezone=settings.scheduler_timezone)

    scheduler.add_job(
        run_sync_stocks_job,
        CronTrigger(hour=6, minute=0, timezone=settings.scheduler_timezone),
        id="sync-stock-universe",
        replace_existing=True,
    )
    scheduler.add_job(
        run_close_sync_workspace_data_job,
        CronTrigger(hour=14, minute=10, timezone=settings.scheduler_timezone),
        id="sync-workspace-close-data",
        replace_existing=True,
    )
    scheduler.add_job(
        run_daily_workspace_automation_job,
        CronTrigger(hour=9, minute=30, timezone=settings.scheduler_timezone),
        id="run-daily-workspace-automation",
        replace_existing=True,
    )
    return scheduler


def describe_scheduler_jobs() -> list[dict[str, str]]:
    scheduler = build_scheduler()
    jobs = []
    for job in scheduler.get_jobs():
        next_run_time = job.trigger.get_next_fire_time(None, datetime.now())
        jobs.append(
            {
                "id": job.id,
                "next_run_time": next_run_time.isoformat() if next_run_time else "n/a",
            }
        )
    return jobs
