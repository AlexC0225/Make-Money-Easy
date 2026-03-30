from collections import deque
from datetime import date, datetime
from threading import Lock
from time import monotonic, sleep

import requests
import twstock

from app.schemas.stock import HistoricalPriceRead, RealtimeQuoteRead


class TwStockClientError(Exception):
    pass


class TwStockClient:
    MARKET_MAPPING = {
        "上市": "TSEC",
        "上櫃": "OTC",
        "興櫃": "TIB",
    }
    TPEX_HISTORY_URL = "https://www.tpex.org.tw/www/zh-tw/afterTrading/tradingStock"
    QUOTE_CACHE_TTL_SECONDS = 15.0
    REALTIME_LIMIT_WINDOW_SECONDS = 5.0
    REALTIME_LIMIT_MAX_REQUESTS = 3
    REALTIME_PRICE_RETRY_ATTEMPTS = 4
    REALTIME_PRICE_RETRY_DELAY_SECONDS = 2.0

    _quote_cache: dict[str, tuple[float, RealtimeQuoteRead]] = {}
    _last_priced_quote_cache: dict[str, RealtimeQuoteRead] = {}
    _quote_cache_lock = Lock()
    _realtime_lock = Lock()
    _realtime_request_times: deque[float] = deque()

    def get_stock_metadata(self, code: str) -> dict[str, str | bool | None]:
        code = code.strip()
        stock_info = getattr(twstock, "codes", {}).get(code)
        if stock_info is None:
            return {
                "code": code,
                "name": code,
                "market": "UNKNOWN",
                "industry": None,
                "is_active": True,
            }

        return {
            "code": code,
            "name": getattr(stock_info, "name", code),
            "market": self.MARKET_MAPPING.get(getattr(stock_info, "market", "UNKNOWN"), "UNKNOWN"),
            "industry": getattr(stock_info, "group", None),
            "is_active": True,
        }

    def list_stock_universe(
        self,
        include_types: tuple[str, ...] = ("股票", "ETF"),
    ) -> list[dict[str, str | bool | None]]:
        universe: list[dict[str, str | bool | None]] = []
        for item in twstock.codes.values():
            if getattr(item, "type", None) not in include_types:
                continue

            universe.append(
                {
                    "code": getattr(item, "code"),
                    "name": getattr(item, "name"),
                    "market": self.MARKET_MAPPING.get(getattr(item, "market", "UNKNOWN"), "UNKNOWN"),
                    "industry": getattr(item, "group", None),
                    "is_active": True,
                }
            )
        return universe

    def get_history(self, code: str, year: int, month: int) -> list[HistoricalPriceRead]:
        try:
            return self._fetch_month_history(code=code, year=year, month=month)
        except Exception as exc:  # pragma: no cover
            raise TwStockClientError(f"Failed to fetch history for {code}: {exc}") from exc

    def get_history_range(self, code: str, start_date: date, end_date: date) -> list[HistoricalPriceRead]:
        try:
            history: list[HistoricalPriceRead] = []
            for year, month in self._iter_months(start_date, end_date):
                history.extend(self._fetch_month_history(code=code, year=year, month=month))
        except Exception as exc:  # pragma: no cover
            raise TwStockClientError(f"Failed to fetch history range for {code}: {exc}") from exc

        return [item for item in history if start_date <= item.trade_date <= end_date]

    def _fetch_month_history(self, code: str, year: int, month: int) -> list[HistoricalPriceRead]:
        if self._uses_tpex_history_source(code):
            return self._fetch_tpex_history(code=code, year=year, month=month)

        stock = twstock.Stock(code, initial_fetch=False)
        self._acquire_twse_slot()
        records = stock.fetch(year, month)
        return self._to_history(records)

    def _uses_tpex_history_source(self, code: str) -> bool:
        stock_info = getattr(twstock, "codes", {}).get(code)
        return getattr(stock_info, "data_source", None) == "tpex"

    def _fetch_tpex_history(self, code: str, year: int, month: int) -> list[HistoricalPriceRead]:
        self._acquire_twse_slot()
        response = requests.get(
            self.TPEX_HISTORY_URL,
            params={
                "date": f"{year}/{month:02d}/01",
                "code": code,
                "response": "json",
            },
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
        return self._parse_tpex_history_payload(payload)

    def _parse_tpex_history_payload(self, payload: dict) -> list[HistoricalPriceRead]:
        tables = payload.get("tables") or []
        if not tables:
            return []

        rows = (tables[0] or {}).get("data") or []
        history: list[HistoricalPriceRead] = []
        for row in rows:
            if not isinstance(row, list) or len(row) < 9:
                continue

            trade_date = self._parse_roc_date(str(row[0]).replace("*", ""))
            history.append(
                HistoricalPriceRead(
                    trade_date=trade_date,
                    volume=self._to_int(row[1], multiplier=1000),
                    turnover=self._to_float(row[2], multiplier=1000),
                    open_price=self._to_float(row[3]),
                    high_price=self._to_float(row[4]),
                    low_price=self._to_float(row[5]),
                    close_price=self._to_float(row[6]),
                    transaction_count=self._to_int(row[8]),
                )
            )
        return history

    @staticmethod
    def _parse_roc_date(value: str) -> date:
        year_text, month_text, day_text = value.split("/")
        return date(int(year_text) + 1911, int(month_text), int(day_text))

    def get_realtime_quote(self, code: str, force_refresh: bool = False) -> RealtimeQuoteRead:
        if not force_refresh:
            cached_quote = self._get_cached_quote(code)
            if cached_quote is not None:
                return cached_quote

        last_error: str | None = None
        last_success_payload: tuple[dict, dict] | None = None
        for attempt in range(self.REALTIME_PRICE_RETRY_ATTEMPTS):
            try:
                self._acquire_twse_slot()
                payload = twstock.realtime.get(code)
            except Exception as exc:  # pragma: no cover
                last_error = f"Failed to fetch realtime quote for {code}: {exc}"
            else:
                if not payload.get("success"):
                    last_error = payload.get("rtmessage") or f"Failed to fetch realtime quote for {code}"
                else:
                    realtime = payload.get("realtime", {}) or {}
                    info = payload.get("info", {}) or {}
                    last_success_payload = (info, realtime)
                    latest_trade_price = self._to_float(realtime.get("latest_trade_price"))
                    if latest_trade_price is not None and latest_trade_price > 0:
                        quote = RealtimeQuoteRead(
                            code=code,
                            name=info.get("name"),
                            quote_time=self._parse_quote_time(info),
                            latest_trade_price=latest_trade_price,
                            latest_trade_price_available=True,
                            latest_trade_price_source="realtime",
                            reference_price=self._resolve_reference_price(realtime),
                            open_price=self._to_float(realtime.get("open")),
                            high_price=self._to_float(realtime.get("high")),
                            low_price=self._to_float(realtime.get("low")),
                            accumulate_trade_volume=self._to_int(realtime.get("accumulate_trade_volume")),
                            best_bid_price=self._to_float_list(realtime.get("best_bid_price")),
                            best_ask_price=self._to_float_list(realtime.get("best_ask_price")),
                            best_bid_volume=self._to_int_list(realtime.get("best_bid_volume")),
                            best_ask_volume=self._to_int_list(realtime.get("best_ask_volume")),
                        )
                        self._cache_quote(code, quote)
                        return quote

                    quote_time = info.get("time") or "unknown"
                    last_error = (
                        f"Realtime latest trade price is unavailable for {code} "
                        f"after snapshot {quote_time} (attempt {attempt + 1}/{self.REALTIME_PRICE_RETRY_ATTEMPTS})."
                    )

            if attempt < self.REALTIME_PRICE_RETRY_ATTEMPTS - 1:
                sleep(self.REALTIME_PRICE_RETRY_DELAY_SECONDS)

        if last_success_payload is not None:
            info, realtime = last_success_payload
            cached_priced_quote = self._get_last_priced_quote(code)
            if cached_priced_quote is not None and cached_priced_quote.latest_trade_price is not None:
                quote = RealtimeQuoteRead(
                    code=code,
                    name=info.get("name"),
                    quote_time=self._parse_quote_time(info),
                    latest_trade_price=cached_priced_quote.latest_trade_price,
                    latest_trade_price_available=True,
                    latest_trade_price_source="cache",
                    warning_message=(
                        f"{last_error} Using cached latest trade price from "
                        f"{cached_priced_quote.quote_time.isoformat()}."
                    ),
                    reference_price=self._resolve_reference_price(realtime),
                    open_price=self._to_float(realtime.get("open")),
                    high_price=self._to_float(realtime.get("high")),
                    low_price=self._to_float(realtime.get("low")),
                    accumulate_trade_volume=self._to_int(realtime.get("accumulate_trade_volume")),
                    best_bid_price=self._to_float_list(realtime.get("best_bid_price")),
                    best_ask_price=self._to_float_list(realtime.get("best_ask_price")),
                    best_bid_volume=self._to_int_list(realtime.get("best_bid_volume")),
                    best_ask_volume=self._to_int_list(realtime.get("best_ask_volume")),
                )
                self._cache_quote(code, quote)
                return quote

            quote = RealtimeQuoteRead(
                code=code,
                name=info.get("name"),
                quote_time=self._parse_quote_time(info),
                latest_trade_price=None,
                latest_trade_price_available=False,
                latest_trade_price_source="unavailable",
                warning_message=last_error,
                reference_price=self._resolve_reference_price(realtime),
                open_price=self._to_float(realtime.get("open")),
                high_price=self._to_float(realtime.get("high")),
                low_price=self._to_float(realtime.get("low")),
                accumulate_trade_volume=self._to_int(realtime.get("accumulate_trade_volume")),
                best_bid_price=self._to_float_list(realtime.get("best_bid_price")),
                best_ask_price=self._to_float_list(realtime.get("best_ask_price")),
                best_bid_volume=self._to_int_list(realtime.get("best_bid_volume")),
                best_ask_volume=self._to_int_list(realtime.get("best_ask_volume")),
            )
            self._cache_quote(code, quote)
            return quote

        raise TwStockClientError(last_error or f"Failed to fetch realtime quote for {code}")

    def _parse_quote_time(self, info: dict) -> datetime:
        time_value = info.get("time")
        if time_value:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
                try:
                    return datetime.strptime(time_value, fmt)
                except ValueError:
                    continue
        return datetime.utcnow()

    def _resolve_reference_price(self, realtime: dict) -> float | None:
        latest_trade_price = self._to_float(realtime.get("latest_trade_price"))
        if latest_trade_price is not None:
            return latest_trade_price

        best_bid = self._to_float_list(realtime.get("best_bid_price"))
        best_ask = self._to_float_list(realtime.get("best_ask_price"))
        if best_bid and best_ask:
            return round((best_bid[0] + best_ask[0]) / 2, 4)
        if best_ask:
            return best_ask[0]
        if best_bid:
            return best_bid[0]

        for key in ("open", "high", "low"):
            candidate = self._to_float(realtime.get(key))
            if candidate is not None:
                return candidate
        return None

    def _to_history(self, records: object) -> list[HistoricalPriceRead]:
        history: list[HistoricalPriceRead] = []
        for item in records:
            history.append(
                HistoricalPriceRead(
                    trade_date=getattr(item, "date"),
                    open_price=self._to_float(getattr(item, "open", None)),
                    high_price=self._to_float(getattr(item, "high", None)),
                    low_price=self._to_float(getattr(item, "low", None)),
                    close_price=self._to_float(getattr(item, "close", None)),
                    volume=self._to_int(getattr(item, "capacity", None)),
                    turnover=self._to_float(getattr(item, "turnover", None)),
                    transaction_count=self._to_int(getattr(item, "transaction", None)),
                )
            )
        return history

    @staticmethod
    def _to_float(value: object, multiplier: float = 1.0) -> float | None:
        if value in (None, "", "-"):
            return None
        if isinstance(value, str):
            value = value.replace(",", "").strip()
            if value in ("", "-", "--"):
                return None
        return float(value) * multiplier

    @staticmethod
    def _to_int(value: object, multiplier: float = 1.0) -> int | None:
        if value in (None, "", "-"):
            return None
        if isinstance(value, str):
            value = value.replace(",", "").strip()
            if value in ("", "-", "--"):
                return None
        return int(float(value) * multiplier)

    def _to_float_list(self, values: object) -> list[float]:
        if not values:
            return []
        return [number for number in (self._to_float(value) for value in values) if number is not None]

    def _to_int_list(self, values: object) -> list[int]:
        if not values:
            return []
        return [number for number in (self._to_int(value) for value in values) if number is not None]

    def _get_cached_quote(self, code: str) -> RealtimeQuoteRead | None:
        with self._quote_cache_lock:
            cached_entry = self._quote_cache.get(code)
            if cached_entry is None:
                return None

            cached_at, quote = cached_entry
            if monotonic() - cached_at > self.QUOTE_CACHE_TTL_SECONDS:
                self._quote_cache.pop(code, None)
                return None
            return quote

    def _cache_quote(self, code: str, quote: RealtimeQuoteRead) -> None:
        with self._quote_cache_lock:
            self._quote_cache[code] = (monotonic(), quote)
            if quote.latest_trade_price is not None and quote.latest_trade_price_source == "realtime":
                self._last_priced_quote_cache[code] = quote

    def _get_last_priced_quote(self, code: str) -> RealtimeQuoteRead | None:
        with self._quote_cache_lock:
            return self._last_priced_quote_cache.get(code)

    def _acquire_twse_slot(self) -> None:
        while True:
            wait_seconds = 0.0
            with self._realtime_lock:
                now = monotonic()
                self._prune_realtime_window(now)
                if len(self._realtime_request_times) < self.REALTIME_LIMIT_MAX_REQUESTS:
                    self._realtime_request_times.append(now)
                    return

                oldest = self._realtime_request_times[0]
                wait_seconds = max(0.0, self.REALTIME_LIMIT_WINDOW_SECONDS - (now - oldest)) + 0.1

            if wait_seconds > 0:
                sleep(wait_seconds)

    def _acquire_realtime_slot(self) -> None:
        self._acquire_twse_slot()

    def _prune_realtime_window(self, now: float) -> None:
        while self._realtime_request_times and now - self._realtime_request_times[0] >= self.REALTIME_LIMIT_WINDOW_SECONDS:
            self._realtime_request_times.popleft()

    def _iter_months(self, start_date: date, end_date: date) -> list[tuple[int, int]]:
        if start_date > end_date:
            return []

        months: list[tuple[int, int]] = []
        cursor = date(start_date.year, start_date.month, 1)
        terminal = date(end_date.year, end_date.month, 1)

        while cursor <= terminal:
            months.append((cursor.year, cursor.month))
            if cursor.month == 12:
                cursor = date(cursor.year + 1, 1, 1)
            else:
                cursor = date(cursor.year, cursor.month + 1, 1)

        return months

    def _first_valid_float(self, values: object) -> float | None:
        if not values:
            return None
        for value in values:
            number = self._to_float(value)
            if number is not None:
                return number
        return None

    def _last_valid_float(self, values: object) -> float | None:
        if not values:
            return None
        for value in reversed(values):
            number = self._to_float(value)
            if number is not None:
                return number
        return None

    def _max_valid_float(self, values: object) -> float | None:
        if not values:
            return None
        parsed = [number for number in (self._to_float(value) for value in values) if number is not None]
        return max(parsed) if parsed else None

    def _min_valid_float(self, values: object) -> float | None:
        if not values:
            return None
        parsed = [number for number in (self._to_float(value) for value in values) if number is not None]
        return min(parsed) if parsed else None

    def _last_valid_int(self, values: object) -> int | None:
        if not values:
            return None
        for value in reversed(values):
            number = self._to_int(value)
            if number is not None:
                return number
        return None
