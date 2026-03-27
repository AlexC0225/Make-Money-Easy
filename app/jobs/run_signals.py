from app.db.session import get_session_factory
from app.services.strategy_service import StrategyService


def run_strategy_batch_job(strategy_name: str = "hybrid_tw_strategy", codes: list[str] | None = None) -> dict[str, object]:
    session = get_session_factory()()
    try:
        service = StrategyService(session)
        processed, saved_signals, failed_codes = service.run_strategy_batch(
            strategy_name=strategy_name,
            codes=codes,
        )
        session.commit()
        return {
            "processed": processed,
            "saved_signals": saved_signals,
            "failed_codes": failed_codes,
        }
    finally:
        session.close()
