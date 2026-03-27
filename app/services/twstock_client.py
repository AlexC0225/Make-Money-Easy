from collections import deque
from datetime import date, datetime, time, timedelta
from threading import Lock
from time import monotonic, sleep
from zoneinfo import ZoneInfo

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
    YAHOO_SYMBOL_SUFFIX = {
        "TSEC": "TW",
        "OTC": "TWO",
        "TIB": "TWO",
    }
    YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    YAHOO_HEADERS = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
    }
    QUOTE_CACHE_TTL_SECONDS = 10.0
    REALTIME_LIMIT_WINDOW_SECONDS = 5.0
    REALTIME_LIMIT_MAX_REQUESTS = 3

    _quote_cache: dict[str, tuple[float, RealtimeQuoteRead]] = {}
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
            stock = twstock.Stock(code)
            self._acquire_twse_slot()
            records = stock.fetch(year, month)
        except Exception as exc:  # pragma: no cover
            raise TwStockClientError(f"Failed to fetch history for {code}: {exc}") from exc

        return self._to_history(records)

    def get_history_range(self, code: str, start_date: date, end_date: date) -> list[HistoricalPriceRead]:
        try:
            stock = twstock.Stock(code)
            records = []
            for year, month in self._iter_months(start_date, end_date):
                self._acquire_twse_slot()
                records.extend(stock.fetch(year, month))
        except Exception as exc:  # pragma: no cover
            raise TwStockClientError(f"Failed to fetch history range for {code}: {exc}") from exc

        history = self._to_history(records)
        return [item for item in history if start_date <= item.trade_date <= end_date]

    def get_realtime_quote(self, code: str) -> RealtimeQuoteRead:
        cached_quote = self._get_cached_quote(code)
        if cached_quote is not None:
            return cached_quote

        try:
            self._acquire_twse_slot()
            payload = twstock.realtime.get(code)
        except Exception as exc:  # pragma: no cover
            return self._fallback_quote(code, f"Failed to fetch realtime quote for {code}: {exc}")

        if not payload.get("success"):
            return self._fallback_quote(
                code,
                payload.get("rtmessage") or f"Failed to fetch realtime quote for {code}",
            )

        realtime = payload.get("realtime", {}) or {}
        info = payload.get("info", {}) or {}
        quote = RealtimeQuoteRead(
            code=code,
            name=info.get("name"),
            quote_time=self._parse_quote_time(info),
            latest_trade_price=self._to_float(realtime.get("latest_trade_price")),
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
    def _to_float(value: object) -> float | None:
        if value in (None, "", "-"):
            return None
        return float(value)

    @staticmethod
    def _to_int(value: object) -> int | None:
        if value in (None, "", "-"):
            return None
        return int(float(value))

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

    def _fallback_quote(self, code: str, original_error: str) -> RealtimeQuoteRead:
        for resolver in (self._get_yahoo_quote, self._get_latest_history_quote):
            try:
                quote = resolver(code)
            except TwStockClientError:
                continue

            self._cache_quote(code, quote)
            return quote

        raise TwStockClientError(original_error)

    def _get_yahoo_quote(self, code: str) -> RealtimeQuoteRead:
        metadata = self.get_stock_metadata(code)
        errors: list[str] = []
        for symbol in self._candidate_yahoo_symbols(code, metadata.get("market")):
            try:
                response = requests.get(
                    self.YAHOO_CHART_URL.format(symbol=symbol),
                    params={"interval": "1m", "range": "1d", "includePrePost": "false"},
                    headers=self.YAHOO_HEADERS,
                    timeout=10,
                )
                response.raise_for_status()
                payload = response.json()
                return self._parse_yahoo_quote_payload(code, payload, metadata)
            except (requests.RequestException, ValueError, TwStockClientError) as exc:
                errors.append(f"{symbol}: {exc}")

        raise TwStockClientError("; ".join(errors) or f"Failed to fetch Yahoo quote for {code}")

    def _candidate_yahoo_symbols(self, code: str, market: object) -> list[str]:
        candidates: list[str] = []
        mapped_suffix = self.YAHOO_SYMBOL_SUFFIX.get(str(market))
        if mapped_suffix:
            candidates.append(f"{code}.{mapped_suffix}")

        for suffix in ("TW", "TWO"):
            symbol = f"{code}.{suffix}"
            if symbol not in candidates:
                candidates.append(symbol)
        return candidates

    def _parse_yahoo_quote_payload(
        self,
        code: str,
        payload: dict,
        metadata: dict[str, str | bool | None],
    ) -> RealtimeQuoteRead:
        chart = payload.get("chart", {}) or {}
        results = chart.get("result") or []
        if not results:
            raise TwStockClientError(chart.get("error", {}).get("description") or "Yahoo quote result is empty")

        result = results[0]
        meta = result.get("meta", {}) or {}
        quote_rows = ((result.get("indicators", {}) or {}).get("quote") or [{}])[0]
        latest_trade_price = self._to_float(meta.get("regularMarketPrice")) or self._last_valid_float(
            quote_rows.get("close")
        )
        reference_price = self._to_float(meta.get("previousClose")) or self._to_float(meta.get("chartPreviousClose"))
        open_price = self._first_valid_float(quote_rows.get("open"))
        high_price = self._to_float(meta.get("regularMarketDayHigh")) or self._max_valid_float(quote_rows.get("high"))
        low_price = self._to_float(meta.get("regularMarketDayLow")) or self._min_valid_float(quote_rows.get("low"))
        volume = self._to_int(meta.get("regularMarketVolume")) or self._last_valid_int(quote_rows.get("volume"))

        if all(candidate is None for candidate in (latest_trade_price, reference_price, open_price, high_price, low_price)):
            raise TwStockClientError("Yahoo quote payload does not contain price data")

        market_timestamp = meta.get("regularMarketTime")
        if market_timestamp:
            quote_time = datetime.fromtimestamp(market_timestamp, tz=ZoneInfo("Asia/Taipei")).replace(tzinfo=None)
        else:
            quote_time = datetime.utcnow()

        name = meta.get("longName") or meta.get("shortName") or metadata.get("name") or code
        return RealtimeQuoteRead(
            code=code,
            name=str(name),
            quote_time=quote_time,
            latest_trade_price=latest_trade_price,
            reference_price=reference_price or latest_trade_price,
            open_price=open_price,
            high_price=high_price,
            low_price=low_price,
            accumulate_trade_volume=volume,
            best_bid_price=[],
            best_ask_price=[],
            best_bid_volume=[],
            best_ask_volume=[],
        )

    def _get_latest_history_quote(self, code: str) -> RealtimeQuoteRead:
        anchor = date.today().replace(day=1)
        for _ in range(3):
            rows = self.get_history(code, anchor.year, anchor.month)
            if rows:
                latest = rows[-1]
                metadata = self.get_stock_metadata(code)
                return RealtimeQuoteRead(
                    code=code,
                    name=str(metadata.get("name") or code),
                    quote_time=datetime.combine(latest.trade_date, time(hour=13, minute=30)),
                    latest_trade_price=latest.close_price,
                    reference_price=latest.close_price,
                    open_price=latest.open_price,
                    high_price=latest.high_price,
                    low_price=latest.low_price,
                    accumulate_trade_volume=latest.volume,
                    best_bid_price=[],
                    best_ask_price=[],
                    best_bid_volume=[],
                    best_ask_volume=[],
                )
            anchor = (anchor - timedelta(days=1)).replace(day=1)

        raise TwStockClientError(f"No recent historical prices available for {code}")

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
