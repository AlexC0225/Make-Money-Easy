from datetime import date, datetime

import requests


class TradingCalendarServiceError(Exception):
    pass


class TradingCalendarService:
    HOLIDAY_API_URL = "https://www.twse.com.tw/holidaySchedule/holidaySchedule"
    REQUEST_TIMEOUT_SECONDS = 20
    _holiday_cache: dict[int, set[date]] = {}

    def is_trading_day(self, target_date: date | None = None) -> bool:
        candidate = target_date or datetime.now().date()
        if candidate.weekday() >= 5:
            return False
        return candidate not in self._get_holiday_dates(candidate.year)

    def _get_holiday_dates(self, year: int) -> set[date]:
        cached = self._holiday_cache.get(year)
        if cached is not None:
            return cached

        roc_year = year - 1911
        try:
            response = requests.get(
                self.HOLIDAY_API_URL,
                params={"response": "json", "queryYear": str(roc_year)},
                timeout=self.REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise TradingCalendarServiceError(f"Unable to fetch TWSE holiday schedule for {year}.") from exc

        rows = payload.get("data", [])
        holidays: set[date] = set()
        for row in rows:
            if not row or not isinstance(row[0], str):
                continue
            try:
                holidays.add(date.fromisoformat(row[0]))
            except ValueError:
                continue

        self._holiday_cache[year] = holidays
        return holidays
