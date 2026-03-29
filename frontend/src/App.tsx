import type { ReactElement } from 'react'
import { Activity, BriefcaseBusiness, LineChart, ListChecks, LogOut } from 'lucide-react'
import { Navigate, NavLink, Route, Routes, useNavigate } from 'react-router-dom'

import { clearActiveUserId, getActiveUserId } from './lib/storage'
import { DashboardPage } from './pages/DashboardPage'
import { LoginPage } from './pages/LoginPage'
import { LogsPage } from './pages/LogsPage'
import { MarketPage } from './pages/MarketPage'
import { SetupPage } from './pages/SetupPage'
import './App.css'

const navigation = [
  { to: '/dashboard', label: '工作臺', icon: BriefcaseBusiness },
  { to: '/market', label: '關注清單', icon: Activity },
  { to: '/logs', label: '策略計畫', icon: LineChart },
  { to: '/setup', label: '工作區設定', icon: ListChecks },
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
              把工作臺、關注清單、手動回測與資料同步整理在同一個節奏裡，讓台股研究和模擬交易更容易維持一致。
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
            <div className="sidebar-session">
              <p>目前工作區已啟用，可以直接維護自選股票、查看持倉，並執行手動回測。</p>
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
            </div>
          ) : null}
        </div>

        <div className="sidebar-footnote">
          <p>預設同步範圍會以自選關注清單與科技、金融產業股票池為核心，重複股票只會同步一次。</p>
          <p>策略選擇會跟著手動回測流程走，不再混在其他頁面的日常操作裡。</p>
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
            path="/logs"
            element={
              <RequireSession>
                <LogsPage />
              </RequireSession>
            }
          />
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
