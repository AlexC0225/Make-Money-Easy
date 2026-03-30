import argparse
from datetime import date

from app.db.session import get_session_factory
from app.services.market_data_service import MarketDataService
from app.services.twstock_client import TwStockClient


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync twstock history for a date range.")
    parser.add_argument("--codes", nargs="+", required=True, help="Stock codes to sync")
    parser.add_argument("--start-date", required=True, help="Start date in YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="End date in YYYY-MM-DD")
    args = parser.parse_args()

    session = get_session_factory()()
    try:
        service = MarketDataService(session, TwStockClient())
        _, synced_codes, synced_rows, skipped_codes, failed_codes = service.sync_history_range_batch(
            codes=args.codes,
            start_date=date.fromisoformat(args.start_date),
            end_date=date.fromisoformat(args.end_date),
        )
        print(
            {
                "synced_codes": synced_codes,
                "synced_rows": synced_rows,
                "skipped_codes": skipped_codes,
                "failed_codes": failed_codes,
            }
        )
    finally:
        session.close()


if __name__ == "__main__":
    main()
