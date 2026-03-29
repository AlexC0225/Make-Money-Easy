import { request } from './client'
import type {
  AutomationConfig,
  AutomationConfigUpdatePayload,
  BacktestResult,
  BacktestRunPayload,
  HistoricalRange,
  HistoryRangeSyncPayload,
  HistoryRangeSyncResult,
  LoginPayload,
  LoginResponse,
  MarketOverview,
  PortfolioBootstrapPayload,
  PortfolioBootstrapResponse,
  PortfolioSummary,
  Position,
  Quote,
  StockUniverseSyncResult,
  StockLookupItem,
  StrategyDefinition,
  StrategyRunPayload,
  StrategySignal,
  SyncTargetPreview,
  UserProfile,
  WatchlistItem,
} from '../types/api'

export const api = {
  bootstrapPortfolio: (payload: PortfolioBootstrapPayload) =>
    request<PortfolioBootstrapResponse>('/portfolio/bootstrap', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  loginUser: (payload: LoginPayload) =>
    request<LoginResponse>('/users/login', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  getUser: (userId: number) => request<UserProfile>(`/users/${userId}`),
  getPortfolioSummary: (userId: number) =>
    request<PortfolioSummary>('/portfolio', { params: { user_id: userId } }),
  getPositions: (userId: number) =>
    request<Position[]>('/portfolio/positions', {
      params: { user_id: userId, include_closed: false },
    }),
  searchStocks: (query: string, limit = 10) =>
    request<StockLookupItem[]>('/stocks/search', {
      params: { q: query, limit },
    }),
  getQuote: (code: string) => request<Quote>(`/stocks/${code}/quote`),
  getHistoryRange: (code: string, startDate: string, endDate: string) =>
    request<HistoricalRange>(`/stocks/${code}/history-range`, {
      params: { start_date: startDate, end_date: endDate },
    }),
  listStrategies: () => request<StrategyDefinition[]>('/strategies/catalog'),
  getAutomationConfig: (userId: number) => request<AutomationConfig>(`/strategies/automation/${userId}`),
  updateAutomationConfig: (userId: number, payload: AutomationConfigUpdatePayload) =>
    request<AutomationConfig>(`/strategies/automation/${userId}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
  runStrategy: (payload: StrategyRunPayload) =>
    request<StrategySignal>('/strategies/run', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  listSignals: (limit = 8, strategyName?: string) =>
    request<StrategySignal[]>('/strategies/signals', { params: { limit, strategy_name: strategyName } }),
  listBacktests: (limit = 8) =>
    request<BacktestResult[]>('/backtests', { params: { limit } }),
  runBacktest: (payload: BacktestRunPayload) =>
    request<BacktestResult>('/backtests/run', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  syncStocks: () =>
    request<StockUniverseSyncResult>('/jobs/sync/stocks', { method: 'POST' }),
  getSyncTargets: (userId?: number) =>
    request<SyncTargetPreview>('/jobs/sync/targets', {
      params: { user_id: userId },
    }),
  syncHistoryRange: (payload: HistoryRangeSyncPayload) =>
    request<HistoryRangeSyncResult>('/jobs/sync/history-range', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  getMarketOverview: (limit = 10) =>
    request<MarketOverview>('/market/overview', { params: { limit } }),
  getWatchlist: (userId: number) =>
    request<WatchlistItem[]>('/watchlist', { params: { user_id: userId } }),
  addWatchlist: (userId: number, code: string, note?: string) =>
    request<WatchlistItem>('/watchlist', {
      method: 'POST',
      body: JSON.stringify({ user_id: userId, code, note }),
    }),
  removeWatchlist: (userId: number, code: string) =>
    request<void>(`/watchlist/${code}`, {
      method: 'DELETE',
      params: { user_id: userId },
    }),
}
