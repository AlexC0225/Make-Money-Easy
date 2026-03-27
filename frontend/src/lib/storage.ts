const ACTIVE_USER_KEY = 'mme-active-user-id'
const AUTO_TRADE_STRATEGY_KEY = 'mme-auto-trade-strategy'
const BACKTEST_STRATEGY_KEY = 'mme-backtest-strategy'

export function getActiveUserId(): number | null {
  const raw = window.localStorage.getItem(ACTIVE_USER_KEY)
  if (!raw) {
    return null
  }

  const parsed = Number(raw)
  return Number.isFinite(parsed) ? parsed : null
}

export function setActiveUserId(userId: number) {
  window.localStorage.setItem(ACTIVE_USER_KEY, String(userId))
}

export function clearActiveUserId() {
  window.localStorage.removeItem(ACTIVE_USER_KEY)
}

export function getBacktestStrategy(): string | null {
  const raw = window.localStorage.getItem(BACKTEST_STRATEGY_KEY)
  return raw?.trim() ? raw : null
}

export function setBacktestStrategy(strategyName: string) {
  window.localStorage.setItem(BACKTEST_STRATEGY_KEY, strategyName)
}

export function getAutoTradeStrategy(): string | null {
  const raw = window.localStorage.getItem(AUTO_TRADE_STRATEGY_KEY)
  return raw?.trim() ? raw : null
}

export function setAutoTradeStrategy(strategyName: string) {
  window.localStorage.setItem(AUTO_TRADE_STRATEGY_KEY, strategyName)
}
