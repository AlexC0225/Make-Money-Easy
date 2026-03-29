import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { ArrowRight, ShieldCheck, Sparkles } from 'lucide-react'
import { Link, Navigate, useNavigate } from 'react-router-dom'

import { api } from '../api'
import { getActiveUserId, setActiveUserId } from '../lib/storage'

export function LoginPage() {
  const navigate = useNavigate()
  const activeUserId = getActiveUserId()
  const [form, setForm] = useState({
    login: '',
  })

  const loginMutation = useMutation({
    mutationFn: api.loginUser,
    onSuccess: (result) => {
      setActiveUserId(result.active_user_id)
      navigate('/dashboard')
    },
  })

  if (activeUserId !== null) {
    return <Navigate to="/dashboard" replace />
  }

  return (
    <div className="auth-shell">
      <section className="auth-hero">
        <div className="auth-hero-copy">
          <p className="hero-kicker">Operator Login</p>
          <h1>登入你的自動交易工作區</h1>
          <p>
            進入後可以直接查看資產配置、watchlist、預設同步股票池與策略執行紀錄，維持整個研究與交易流程一致。
          </p>
        </div>

        <div className="auth-highlight-grid">
          <article className="auth-highlight-card">
            <ShieldCheck size={18} />
            <strong>固定工作區入口</strong>
            <p>使用同一個帳號登入，保留 watchlist、資產設定與同步節奏。</p>
          </article>
          <article className="auth-highlight-card">
            <Sparkles size={18} />
            <strong>同步範圍透明</strong>
            <p>預設同步會清楚顯示 watchlist 與科技、金融產業股票池的組成，不再是黑盒子。</p>
          </article>
        </div>
      </section>

      <section className="auth-panel">
        <div className="auth-card">
          <div className="auth-card-head">
            <p className="panel-kicker">Workspace Access</p>
            <h2>登入</h2>
            <p>輸入使用者名稱或 Email 即可進入工作區。</p>
          </div>

          <form
            className="stack-form"
            onSubmit={(event) => {
              event.preventDefault()
              loginMutation.mutate(form)
            }}
          >
            <label>
              帳號
              <input
                value={form.login}
                onChange={(event) => setForm((current) => ({ ...current, login: event.target.value }))}
                placeholder="alex 或 alex@example.com"
                autoComplete="username"
                required
              />
            </label>

            {loginMutation.error ? <p className="error-text">{loginMutation.error.message}</p> : null}

            <div className="inline-actions">
              <button className="primary-button" type="submit" disabled={loginMutation.isPending}>
                <ArrowRight size={16} />
                進入工作台
              </button>
              <Link to="/setup" className="ghost-button">
                建立新工作區
              </Link>
            </div>
          </form>
        </div>

        <div className="auth-note">
          <strong>第一次使用</strong>
          <p>先建立工作區與初始資產，之後就能用帳號直接登入，不需要再手動指定使用者 ID。</p>
        </div>
      </section>
    </div>
  )
}
