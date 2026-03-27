from fastapi import APIRouter

from app.api.routes import backtests, jobs, market, portfolio, stocks, strategies, users, watchlist

api_router = APIRouter()
api_router.include_router(users.router)
api_router.include_router(stocks.router)
api_router.include_router(portfolio.router)
api_router.include_router(strategies.router)
api_router.include_router(backtests.router)
api_router.include_router(jobs.router)
api_router.include_router(market.router)
api_router.include_router(watchlist.router)
