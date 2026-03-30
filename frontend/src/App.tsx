import type { ReactElement } from 'react'
import { Activity, BriefcaseBusiness, LineChart, ListChecks, LogOut } from 'lucide-react'
import { Navigate, NavLink, Route, Routes, useNavigate } from 'react-router-dom'

import { clearActiveUserId, getActiveUserId } from './lib/storage'
import { BacktestsPage } from './pages/BacktestsPage'
import { DashboardPage } from './pages/DashboardPage'
import { LoginPage } from './pages/LoginPage'
import { MarketPage } from './pages/MarketPage'
import { SetupPage } from './pages/SetupPage'
import { StrategySignalsPage } from './pages/StrategySignalsPage'
import './App.css'

const navigation = [
  { to: '/dashboard', label: '工作台', icon: BriefcaseBusiness },
  { to: '/market', label: '行情觀察', icon: Activity },
  { to: '/backtests', label: '回測分析', icon: LineChart },
  { to: '/signals', label: '策略訊號', icon: ListChecks },
  { to: '/setup', label: '工作台設定', icon: ListChecks },
]

function RequireSession({ children }: { children: ReactElement }) {
  return getActiveUserId() === null ? <Navigate to="/login" replace /> : children
}

function AppShell() {
  const navigate = useNavigate()
  const activeUserId = getActiveUserId()

  return (
    <div className="app-shell">
      <aside className="app-sidebar">
        <div className="sidebar-content">
          <div className="brand-block">
            <p className="brand-kicker">Taiwan Paper Trading</p>
            <h1>Make Money Easy</h1>
            <p className="brand-copy">
              用同一個工作台把持倉、策略訊號、回測結果與市場觀察拆開管理，讓日常判讀更清楚。
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
