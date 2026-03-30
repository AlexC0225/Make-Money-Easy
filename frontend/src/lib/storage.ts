const ACTIVE_USER_KEY = 'mme-active-user-id'
const AUTO_TRADE_STRATEGY_KEY = 'mme-auto-trade-strategy'
const BACKTEST_STRATEGY_KEY = 'mme-backtest-strategy'
const ACTIVE_SYNC_RUN_KEY = 'mme-active-sync-run'
const STORAGE_UPDATED_EVENT = 'mme-storage-updated'

export type ActiveSyncRun = {
  run_id: string
  job_name: 'sync-stocks' | 'sync-history-range'
  label: string
  started_at: string
}

function emitStorageUpdated(key: string) {
  window.dispatchEvent(new CustomEvent(STORAGE_UPDATED_EVENT, { detail: { key } }))
}

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
  emitStorageUpdated(ACTIVE_USER_KEY)
}

export function clearActiveUserId() {
  window.localStorage.removeItem(ACTIVE_USER_KEY)
  emitStorageUpdated(ACTIVE_USER_KEY)
}

export function getBacktestStrategy(): string | null {
  const raw = window.localStorage.getItem(BACKTEST_STRATEGY_KEY)
  return raw?.trim() ? raw : null
}

export function setBacktestStrategy(strategyName: string) {
  window.localStorage.setItem(BACKTEST_STRATEGY_KEY, strategyName)
  emitStorageUpdated(BACKTEST_STRATEGY_KEY)
}

export function getAutoTradeStrategy(): string | null {
  const raw = window.localStorage.getItem(AUTO_TRADE_STRATEGY_KEY)
  return raw?.trim() ? raw : null
}

export function setAutoTradeStrategy(strategyName: string) {
  window.localStorage.setItem(AUTO_TRADE_STRATEGY_KEY, strategyName)
  emitStorageUpdated(AUTO_TRADE_STRATEGY_KEY)
}

export function getActiveSyncRun(): ActiveSyncRun | null {
  const raw = window.localStorage.getItem(ACTIVE_SYNC_RUN_KEY)
  if (!raw) {
    return null
  }

  try {
    const parsed = JSON.parse(raw) as Partial<ActiveSyncRun>
    if (
      typeof parsed.run_id === 'string' &&
      typeof parsed.job_name === 'string' &&
      typeof parsed.label === 'string' &&
      typeof parsed.started_at === 'string'
    ) {
      return {
        run_id: parsed.run_id,
        job_name: parsed.job_name as ActiveSyncRun['job_name'],
        label: parsed.label,
        started_at: parsed.started_at,
      }
    }
  } catch {
    return null
  }

  return null
}

export function setActiveSyncRun(run: ActiveSyncRun) {
  window.localStorage.setItem(ACTIVE_SYNC_RUN_KEY, JSON.stringify(run))
  emitStorageUpdated(ACTIVE_SYNC_RUN_KEY)
}

export function clearActiveSyncRun() {
  window.localStorage.removeItem(ACTIVE_SYNC_RUN_KEY)
  emitStorageUpdated(ACTIVE_SYNC_RUN_KEY)
}

export function subscribeStorageUpdated(listener: () => void) {
  const handleStorageUpdated = () => listener()
  const handleNativeStorage = () => listener()

  window.addEventListener(STORAGE_UPDATED_EVENT, handleStorageUpdated)
  window.addEventListener('storage', handleNativeStorage)

  return () => {
    window.removeEventListener(STORAGE_UPDATED_EVENT, handleStorageUpdated)
    window.removeEventListener('storage', handleNativeStorage)
  }
}
