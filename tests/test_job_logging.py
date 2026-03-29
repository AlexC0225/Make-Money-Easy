import json
from datetime import date, timedelta

from app.config import get_settings
from app.db.models.market_data import DailyPrice
from app.db.models.stock import Stock
from app.db.session import get_session_factory
from app.jobs.run_automation import run_daily_workspace_automation_job
from app.jobs.sync_workspace_data import run_close_sync_workspace_data_job
from tests.test_stocks import FakeTwStockClient


def _read_daily_job_records(log_dir):
    log_files = sorted(log_dir.glob("jobs-*.log"))
    assert log_files
    return [json.loads(line) for line in log_files[0].read_text(encoding="utf-8").splitlines() if line.strip()]


def _seed_automation_stock() -> None:
    session = get_session_factory()()
    try:
        stock = Stock(code="2330", name="TSMC", market="TSEC", industry="半導體業", is_active=True)
        session.add(stock)
        session.flush()

        start_date = date(2025, 1, 1)
        for offset in range(240):
            trade_date = start_date + timedelta(days=offset)
            close_price = 800.0 + (offset * 1.5)
            session.add(
                DailyPrice(
                    stock_id=stock.id,
                    trade_date=trade_date,
                    open_price=close_price - 2,
                    high_price=close_price + 6,
                    low_price=close_price - 6,
                    close_price=close_price,
                    volume=100_000 + (offset * 100),
                    turnover=close_price * (100_000 + (offset * 100)),
                    transaction_count=1_000 + offset,
                )
            )

        session.commit()
    finally:
        session.close()


def test_sync_workspace_job_writes_daily_log_when_skipped(client, tmp_path, monkeypatch):
    log_dir = tmp_path / "job-logs"
    monkeypatch.setenv("MME_JOB_LOG_DIR", str(log_dir))
    get_settings.cache_clear()
    monkeypatch.setattr("app.jobs.sync_workspace_data.TradingCalendarService.is_trading_day", lambda self, target_date=None: False)

    result = run_close_sync_workspace_data_job()

    assert result["skipped"] is True
    records = _read_daily_job_records(log_dir)
    assert records[0]["job_name"] == "sync-workspace-close-data"
    assert records[0]["status"] == "RUNNING"
    assert records[1]["job_name"] == "sync-workspace-close-data"
    assert records[1]["status"] == "SKIPPED"
    assert records[1]["payload"]["reason"] == "non_trading_day"
    get_settings.cache_clear()


def test_automation_job_writes_execution_status_details(client, tmp_path, monkeypatch):
    log_dir = tmp_path / "job-logs"
    monkeypatch.setenv("MME_JOB_LOG_DIR", str(log_dir))
    get_settings.cache_clear()
    _seed_automation_stock()

    bootstrap_response = client.post(
        "/api/v1/portfolio/bootstrap",
        json={
            "username": "logger",
            "email": "logger@example.com",
            "initial_cash": 1_000_000,
            "available_cash": 1_000_000,
            "positions": [],
        },
    )
    assert bootstrap_response.status_code == 200
    user_id = bootstrap_response.json()["user_id"]

    config_response = client.get(f"/api/v1/strategies/automation/{user_id}")
    assert config_response.status_code == 200

    watchlist_response = client.post(
        "/api/v1/watchlist",
        json={"user_id": user_id, "code": "2330", "note": "daily-check"},
    )
    assert watchlist_response.status_code == 201

    monkeypatch.setattr("app.jobs.run_automation.TradingCalendarService.is_trading_day", lambda self: True)
    monkeypatch.setattr("app.jobs.run_automation.TwStockClient", FakeTwStockClient)

    result = run_daily_workspace_automation_job()

    assert result["skipped"] is False
    assert result["processed_users"] == 1
    assert len(result["execution_details"]) == 1
    assert result["execution_details"][0]["code"] == "2330"
    assert result["execution_details"][0]["execution"]["status"] == "SKIPPED"

    records = _read_daily_job_records(log_dir)
    assert records[0]["job_name"] == "run-daily-workspace-automation"
    assert records[0]["status"] == "RUNNING"
    assert records[1]["job_name"] == "run-daily-workspace-automation"
    assert records[1]["status"] == "SUCCESS"
    assert records[1]["payload"]["execution_details"][0]["code"] == "2330"
    assert records[1]["payload"]["execution_details"][0]["execution"]["status"] == "SKIPPED"
    get_settings.cache_clear()
