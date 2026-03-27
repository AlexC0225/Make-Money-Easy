from datetime import date

from app.services.trading_calendar_service import TradingCalendarService


def test_is_trading_day_returns_false_on_weekend():
    service = TradingCalendarService()

    assert service.is_trading_day(date(2026, 3, 28)) is False


def test_is_trading_day_uses_twse_holiday_schedule(monkeypatch):
    service = TradingCalendarService()

    monkeypatch.setattr(
        service,
        "_get_holiday_dates",
        lambda year: {date(2026, 1, 1), date(2026, 2, 16)},
    )

    assert service.is_trading_day(date(2026, 1, 1)) is False
    assert service.is_trading_day(date(2026, 1, 5)) is True
