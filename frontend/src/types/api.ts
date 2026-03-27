export type Position = {
  stock_code: string
  stock_name: string
  quantity: number
  avg_cost: number
  market_price: number
  unrealized_pnl: number
  realized_pnl: number
  updated_at: string
}

export type PortfolioSummary = {
  user_id: number
  available_cash: number
  frozen_cash: number
  market_value: number
  total_equity: number
  unrealized_pnl: number
  realized_pnl: number
}

export type UserAccount = {
  id: number
  user_id: number
  initial_cash: number
  available_cash: number
  frozen_cash: number
  market_value: number
  total_equity: number
}

export type UserProfile = {
  id: number
  username: string
  email: string
  created_at: string
  account: UserAccount
}

export type LoginPayload = {
  login: string
}

export type LoginResponse = {
  user: UserProfile
  active_user_id: number
}

export type StockLookupItem = {
  code: string
  name: string
  market: string
  industry?: string | null
  latest_price?: number | null
}

export type ManualPositionInput = {
  code: string
  quantity: number
  avg_cost: number
  market_price?: number
}

export type PortfolioBootstrapPayload = {
  user_id?: number
  username: string
  email: string
  initial_cash: number
  available_cash: number
  positions: ManualPositionInput[]
}

export type PortfolioBootstrapResponse = {
  user_id: number
  username: string
  email: string
  initial_cash: number
  available_cash: number
  market_value: number
  total_equity: number
  positions: Position[]
}

export type Quote = {
  code: string
  name?: string
  quote_time: string
  latest_trade_price?: number
  reference_price?: number
  open_price?: number
  high_price?: number
  low_price?: number
  accumulate_trade_volume?: number
  best_bid_price: number[]
  best_ask_price: number[]
  best_bid_volume: number[]
  best_ask_volume: number[]
}

export type HistoricalPrice = {
  trade_date: string
  open_price: number | null
  high_price: number | null
  low_price: number | null
  close_price: number | null
  volume: number | null
  turnover: number | null
  transaction_count: number | null
}

export type HistoricalRange = {
  code: string
  start_date: string
  end_date: string
  prices: HistoricalPrice[]
}

export type StrategyDefinition = {
  name: string
  title: string
  description: string
  trade_frequency: string
  execution_timing: string
  is_long_only: boolean
}

export type StrategySignal = {
  id: number
  strategy_name: string
  stock_code: string
  stock_name: string
  signal: string
  signal_reason?: string
  signal_time: string
  snapshot: Record<string, number | string>
  execution?: {
    applied: boolean
    action: string
    quantity: number
    status: string
    message: string
    available_cash?: number
    market_value?: number
    total_equity?: number
  } | null
}

export type StrategyRunPayload = {
  user_id: number
  code: string
  strategy_name: string
  execute_trade?: boolean
  buy_quantity?: number
}

export type AutomationConfig = {
  user_id: number
  enabled: boolean
  strategy_name: string
  buy_quantity: number
  updated_at?: string | null
}

export type AutomationConfigUpdatePayload = {
  enabled: boolean
  strategy_name: string
  buy_quantity: number
}

export type BacktestResult = {
  id: number
  strategy_name: string
  stock_code: string
  stock_name: string
  start_date: string
  end_date: string
  total_return: number
  max_drawdown: number
  win_rate: number
  profit_factor: number
  sharpe_ratio: number
  result: {
    initial_cash: number
    final_equity: number
    realized_pnl: number
    open_position_quantity: number
    trade_count: number
    closed_trade_count: number
    equity_curve: Array<{ date: string; equity: number; signal: string; close: number }>
    trades: Array<Record<string, string | number>>
  }
  created_at: string
}

export type BacktestRunPayload = {
  code: string
  strategy_name: string
  start_date: string
  end_date: string
  initial_cash: number
  lot_size: number
}

export type HistorySyncPayload = {
  codes?: string[]
  user_id?: number
  year: number
  month: number
}

export type HistoryRangeSyncPayload = {
  codes?: string[]
  user_id?: number
  start_date: string
  end_date: string
}

export type SyncTargetPreview = {
  selection_mode: string
  codes: string[]
  watchlist_codes: string[]
  benchmark_codes: string[]
  source_url?: string | null
  announce_date?: string | null
  trade_date?: string | null
}

export type StockUniverseSyncResult = {
  synced_count: number
}

export type HistorySyncResult = SyncTargetPreview & {
  year: number
  month: number
  synced_codes: number
  synced_rows: number
  failed_codes: string[]
}

export type HistoryRangeSyncResult = SyncTargetPreview & {
  start_date: string
  end_date: string
  synced_codes: number
  synced_rows: number
  failed_codes: string[]
}

export type MarketLeaderItem = {
  code: string
  name: string
  close_price: number
  change_percent: number
  volume: number
  turnover?: number | null
}

export type MarketOverview = {
  as_of_date: string
  top_gainers: MarketLeaderItem[]
  top_losers: MarketLeaderItem[]
  top_volume: MarketLeaderItem[]
}

export type WatchlistItem = {
  id: number
  user_id: number
  code: string
  name: string
  market: string
  note?: string | null
  created_at: string
}
