import { useEffect, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { ArrowRight, LoaderCircle } from 'lucide-react'
import { Link, Navigate, useNavigate } from 'react-router-dom'

import { api } from '../api'
import { getActiveUserId, setActiveUserId } from '../lib/storage'

export function LoginPage() {
  const navigate = useNavigate()
  const activeUserId = getActiveUserId()
  const [form, setForm] = useState({
    login: '',
  })

  const singletonUserQuery = useQuery({
    queryKey: ['singleton-user'],
    queryFn: api.getSingletonUser,
    retry: false,
    staleTime: 60_000,
  })

  const loginMutation = useMutation({
    mutationFn: api.loginUser,
    onSuccess: (result) => {
      setActiveUserId(result.active_user_id)
      navigate('/dashboard', { replace: true })
    },
  })

  useEffect(() => {
    if (activeUserId !== null) {
      return
    }

    const singletonUser = singletonUserQuery.data?.user
    const singletonUserId = singletonUserQuery.data?.active_user_id
    if (!singletonUser || singletonUserId === null || singletonUserId === undefined) {
      return
    }

    setForm((current) => ({
      login: current.login || singletonUser.email,
    }))
    setActiveUserId(singletonUserId)
    navigate('/dashboard', { replace: true })
  }, [activeUserId, navigate, singletonUserQuery.data])

  if (activeUserId !== null) {
    return <Navigate to="/dashboard" replace />
  }

  const requiresSetup = singletonUserQuery.data?.requires_setup ?? false
  const isCheckingSingleton = singletonUserQuery.isPending

  return (
    <div className="auth-shell">
      <section className="auth-hero">
        <div className="auth-hero-copy">
          <p className="hero-kicker">Operator Login</p>
          <h1>登入你的自動交易工作區</h1>
          <p>這個系統預設只服務一位使用者；如果工作區已經存在，系統會自動帶入並直接進入工作台。</p>
        </div>
      </section>

      <section className="auth-panel">
        <div className="auth-card">
          <div className="auth-card-head">
            <p className="panel-kicker">Workspace Access</p>
            <h2>{requiresSetup ? '建立工作區' : '登入'}</h2>
            <p>
              {requiresSetup
                ? '目前還沒有任何使用者，先建立工作區後，之後重新開啟服務就會自動帶入。'
                : '系統啟動時會檢查唯一使用者；若已存在，會自動登入。'}
            </p>
          </div>

          {isCheckingSingleton ? (
            <div className="stack-form">
              <p className="muted-text">正在檢查目前工作區設定...</p>
              <div className="inline-actions">
                <button className="primary-button" type="button" disabled>
                  <LoaderCircle className="spinning-icon" size={16} />
                  載入中
                </button>
              </div>
            </div>
          ) : requiresSetup ? (
            <div className="stack-form">
              <p className="muted-text">第一次使用請先輸入帳號、Email 與初始資金建立唯一工作區。</p>
              <div className="inline-actions">
                <Link to="/setup" className="primary-button">
                  <ArrowRight size={16} />
                  前往建立工作區
                </Link>
              </div>
            </div>
          ) : (
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
                  工作區設定
                </Link>
              </div>
            </form>
          )}
        </div>

        <div className="auth-note">
          <strong>單一使用者模式</strong>
          <p>資料庫只會保留一筆使用者資料；如果這筆資料已存在，登入頁會自動帶入，不需要重複建立帳號。</p>
        </div>
      </section>
    </div>
  )
}
