import { useEffect, useState, type ReactElement } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Activity,
  BriefcaseBusiness,
  LineChart,
  ListChecks,
  LoaderCircle,
  LogOut,
  X,
} from 'lucide-react'
import { Link, Navigate, NavLink, Route, Routes, useNavigate } from 'react-router-dom'

import { api } from './api'
import { isApiError } from './api/client'
import {
  clearActiveSyncRun,
  clearActiveUserId,
  getActiveSyncRun,
  getActiveUserId,
  subscribeStorageUpdated,
  type ActiveSyncRun,
} from './lib/storage'
import { BacktestsPage } from './pages/BacktestsPage'
import { DashboardPage } from './pages/DashboardPage'
import { LoginPage } from './pages/LoginPage'
import { MarketPage } from './pages/MarketPage'
import { SetupPage } from './pages/SetupPage'
import { StrategySignalsPage } from './pages/StrategySignalsPage'
import './App.css'

const navigation = [
  { to: '/dashboard', label: '工作臺', icon: BriefcaseBusiness },
  { to: '/market', label: '市場總覽', icon: Activity },
  { to: '/backtests', label: '回測實驗室', icon: LineChart },
  { to: '/signals', label: '策略訊號', icon: ListChecks },
  { to: '/setup', label: '工作區設定', icon: ListChecks },
]

function formatElapsedTime(startedAt: string, finishedAt?: string | null) {
  const startedMs = new Date(startedAt).getTime()
  const endedMs = finishedAt ? new Date(finishedAt).getTime() : Date.now()
  const elapsedSeconds = Math.max(0, Math.floor((endedMs - startedMs) / 1000))
  const minutes = Math.floor(elapsedSeconds / 60)
  const seconds = elapsedSeconds % 60

  if (minutes <= 0) {
    return `${seconds} 秒`
  }

  return `${minutes} 分 ${String(seconds).padStart(2, '0')} 秒`
}

function getSyncBannerTitle(activeSyncRun: ActiveSyncRun, status?: 'running' | 'completed' | 'failed') {
  if (status === 'completed') {
    return `${activeSyncRun.label}已完成`
  }

  if (status === 'failed') {
    return `${activeSyncRun.label}失敗`
  }

  return `${activeSyncRun.label}進行中`
}

function isSyncLookupGracePeriod(activeSyncRun: ActiveSyncRun | null) {
  if (!activeSyncRun) {
    return false
  }

  return Date.now() - new Date(activeSyncRun.started_at).getTime() < 15_000
}

function RequireSession({ children }: { children: ReactElement }) {
  return getActiveUserId() === null ? <Navigate to="/login" replace /> : children
}

function AppShell() {
  const navigate = useNavigate()
  const activeUserId = getActiveUserId()
  const [activeSyncRun, setActiveSyncRunState] = useState<ActiveSyncRun | null>(() => getActiveSyncRun())

  useEffect(() => {
    return subscribeStorageUpdated(() => {
      setActiveSyncRunState(getActiveSyncRun())
    })
  }, [])

  const syncProgressQuery = useQuery({
    queryKey: ['app-sync-progress', activeSyncRun?.run_id],
    queryFn: () => api.getSyncProgress(activeSyncRun!.run_id),
    enabled: activeSyncRun !== null,
    retry: false,
    staleTime: 0,
    refetchOnWindowFocus: true,
    refetchInterval: (query) => {
      if (!activeSyncRun) {
        return false
      }

      const status = query.state.data?.status
      return status === 'completed' || status === 'failed' ? false : 1000
    },
    refetchIntervalInBackground: true,
  })

  useEffect(() => {
    if (!activeSyncRun || !syncProgressQuery.error) {
      return
    }

    if (
      isApiError(syncProgressQuery.error) &&
      syncProgressQuery.error.status === 404 &&
      !isSyncLookupGracePeriod(activeSyncRun)
    ) {
      clearActiveSyncRun()
    }
  }, [activeSyncRun, syncProgressQuery.error])

  const syncProgress = syncProgressQuery.data
  const syncStatus = syncProgress?.status ?? (syncProgressQuery.isPending ? 'running' : undefined)
  const syncFinishedAt = syncProgress?.finished_at
  const syncErrorMessage = syncProgress?.error_message
  const syncCurrentCode = syncProgress?.current_code
  const showSyncBanner =
    activeSyncRun !== null &&
    (syncProgress !== undefined ||
      syncProgressQuery.isPending ||
      (syncProgressQuery.error && isSyncLookupGracePeriod(activeSyncRun)))
  const syncProgressPercent =
    syncProgress && syncProgress.total_codes > 0
      ? Math.round((syncProgress.completed_codes / syncProgress.total_codes) * 100)
      : undefined
  const syncSummary =
    syncProgress && syncProgress.total_codes > 0
      ? `已完成 ${syncProgress.completed_codes} / ${syncProgress.total_codes}，成功 ${syncProgress.synced_codes}，失敗 ${syncProgress.failed_codes.length}`
      : '正在向後端建立同步狀態，切換頁面不會中斷更新。'
  const syncCaption = syncCurrentCode
    ? `目前正在同步 ${syncCurrentCode}。`
    : syncStatus === 'completed'
      ? `總耗時 ${formatElapsedTime(activeSyncRun?.started_at ?? new Date().toISOString(), syncFinishedAt)}。`
      : syncStatus === 'failed'
        ? syncErrorMessage ?? '同步未完成，請到工作區設定頁確認錯誤訊息。'
        : '同步由後端持續執行中，離開設定頁後仍可稍後回來查看進度。'

  return (
    <div className="app-shell">
      <aside className="app-sidebar">
        <div className="sidebar-content">
          <div className="brand-block">
            <p className="brand-kicker">Taiwan Paper Trading</p>
            <h1>Make Money Easy</h1>
            <p className="brand-copy">
              把工作區、同步資料、回測與策略執行集中在同一個介面裡，讓你可以用更穩定的節奏管理台股交易流程。
            </p>
          </div>

          <nav className="main-nav">
            {navigation.map(({ to, label, icon: Icon }) => (
              <NavLink key={to} to={to} className="nav-link">
                <Icon size={18} />
                {label}
              </NavLink>
            ))}
          </nav>

          {activeUserId !== null ? (
            <button
              className="ghost-button ghost-button--sidebar"
              type="button"
              onClick={() => {
                clearActiveUserId()
                clearActiveSyncRun()
                navigate('/login')
              }}
            >
              <LogOut size={16} />
              登出
            </button>
          ) : null}
        </div>
      </aside>

      <main className="app-main">
        {showSyncBanner ? (
          <div className={`global-sync-banner ${syncStatus === 'failed' ? 'global-sync-banner--failed' : ''}`}>
            <div className="global-sync-banner__copy">
              <div className="global-sync-banner__head">
                <span className="global-sync-banner__kicker">同步狀態</span>
                <strong>{getSyncBannerTitle(activeSyncRun!, syncStatus)}</strong>
              </div>

              <p>{syncSummary}</p>
              <p className="global-sync-banner__caption">{syncCaption}</p>

              {syncProgress ? (
                <div className="global-sync-banner__meta">
                  <span>耗時 {formatElapsedTime(activeSyncRun!.started_at, syncFinishedAt)}</span>
                  {syncProgressPercent !== undefined ? <span>進度 {syncProgressPercent}%</span> : null}
                </div>
              ) : null}
            </div>

            <div className="global-sync-banner__actions">
              {syncStatus === 'running' || syncStatus === undefined ? (
                <span className="setup-progress-badge">
                  <LoaderCircle className="spinning-icon" size={14} />
                  同步中
                </span>
              ) : null}
              <Link className="ghost-button" to="/setup">
                前往同步頁
              </Link>
              {syncStatus === 'completed' || syncStatus === 'failed' ? (
                <button className="icon-button" type="button" onClick={clearActiveSyncRun} aria-label="清除同步狀態">
                  <X size={16} />
                </button>
              ) : null}
            </div>
          </div>
        ) : null}

        <div className="app-main-content">
          <Routes>
            <Route path="/" element={<Navigate to={activeUserId ? '/dashboard' : '/login'} replace />} />
            <Route
              path="/dashboard"
              element={
                <RequireSession>
                  <DashboardPage />
                </RequireSession>
              }
            />
            <Route
              path="/market"
              element={
                <RequireSession>
                  <MarketPage />
                </RequireSession>
              }
            />
            <Route
              path="/backtests"
              element={
                <RequireSession>
                  <BacktestsPage />
                </RequireSession>
              }
            />
            <Route
              path="/signals"
              element={
                <RequireSession>
                  <StrategySignalsPage />
                </RequireSession>
              }
            />
            <Route path="/logs" element={<Navigate to="/backtests" replace />} />
            <Route path="/setup" element={<SetupPage />} />
            <Route path="*" element={<Navigate to={activeUserId ? '/dashboard' : '/login'} replace />} />
          </Routes>
        </div>
      </main>
    </div>
  )
}

function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/*" element={<AppShell />} />
    </Routes>
  )
}

export default App
