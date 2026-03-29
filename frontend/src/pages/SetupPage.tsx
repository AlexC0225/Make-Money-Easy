import { startTransition, useEffect, useRef, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { ArrowRight, LoaderCircle, RefreshCcw } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

import { api } from '../api'
import { Panel } from '../components/Panel'
import { PositionEditor } from '../components/PositionEditor'
import { formatCurrency } from '../lib/format'
import { clearActiveUserId, getActiveUserId, setActiveUserId } from '../lib/storage'
import type { ManualPositionInput, PortfolioBootstrapPayload } from '../types/api'

const emptyPosition: ManualPositionInput = {
  code: '',
  quantity: 1000,
  avg_cost: 0,
  market_price: 0,
}

function countConfiguredPositions(positions: ManualPositionInput[]) {
  return positions.filter((position) => position.code.trim().length > 0 && position.quantity > 0).length
}

function parseCodeInput(input: string) {
  const parsed = input
    .split(/[\s,，]+/)
    .map((code) => code.trim())
    .filter(Boolean)

  return parsed.length > 0 ? parsed : undefined
}

function toDateInputValue(input: Date) {
  const year = input.getFullYear()
  const month = String(input.getMonth() + 1).padStart(2, '0')
  const day = String(input.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function formatElapsedTime(totalSeconds: number) {
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60

  if (minutes <= 0) {
    return `${seconds} 秒`
  }

  return `${minutes} 分 ${String(seconds).padStart(2, '0')} 秒`
}

function getProgressHint(totalSeconds: number) {
  if (totalSeconds < 6) {
    return '已送出請求，正在整理同步目標與檢查條件。'
  }

  if (totalSeconds < 16) {
    return '伺服器正在抓取遠端資料，依股票數量與日期區間不同，等待時間可能略有差異。'
  }

  return '目前多半正在寫入與整理資料庫，請先不要重複送出同步請求。'
}

export function SetupPage() {
  const navigate = useNavigate()
  const [activeUserId, setActiveUserIdState] = useState<number | null>(() => getActiveUserId())
  const hydrated = useRef(false)
  const clearedInvalidWorkspace = useRef(false)
  const [positions, setPositions] = useState<ManualPositionInput[]>([])
  const [overrideCodes, setOverrideCodes] = useState('')
  const [syncElapsedSeconds, setSyncElapsedSeconds] = useState(0)
  const [rangeStart, setRangeStart] = useState(() => {
    const start = new Date()
    start.setMonth(start.getMonth() - 6)
    return toDateInputValue(start)
  })
  const [rangeEnd, setRangeEnd] = useState(() => toDateInputValue(new Date()))
  const [form, setForm] = useState<PortfolioBootstrapPayload>({
    username: '',
    email: '',
    initial_cash: 1_000_000,
    available_cash: 1_000_000,
    positions: [],
  })

  const configuredPositions = countConfiguredPositions(positions)
  const manualOverrideCodes = parseCodeInput(overrideCodes)

  const userQuery = useQuery({
    queryKey: ['user', activeUserId],
    queryFn: () => api.getUser(activeUserId!),
    enabled: activeUserId !== null,
    retry: false,
  })

  const positionsQuery = useQuery({
    queryKey: ['positions', activeUserId],
    queryFn: () => api.getPositions(activeUserId!),
    enabled: activeUserId !== null,
    retry: false,
  })

  const syncTargetsQuery = useQuery({
    queryKey: ['sync-targets', activeUserId],
    queryFn: () => api.getSyncTargets(activeUserId ?? undefined),
    retry: false,
    staleTime: 60_000,
  })

  useEffect(() => {
    if (!userQuery.data || !positionsQuery.data || hydrated.current) {
      return
    }

    hydrated.current = true
    setForm({
      user_id: userQuery.data.id,
      username: userQuery.data.username,
      email: userQuery.data.email,
      initial_cash: userQuery.data.account.initial_cash,
      available_cash: userQuery.data.account.available_cash,
      positions: positionsQuery.data.map((position) => ({
        code: position.stock_code,
        quantity: position.quantity,
        avg_cost: position.avg_cost,
        market_price: position.market_price,
      })),
    })
    setPositions(
      positionsQuery.data.map((position) => ({
        code: position.stock_code,
        quantity: position.quantity,
        avg_cost: position.avg_cost,
        market_price: position.market_price,
      })),
    )
  }, [positionsQuery.data, userQuery.data])

  const bootstrapMutation = useMutation({
    mutationFn: api.bootstrapPortfolio,
    onSuccess: (result) => {
      setActiveUserId(result.user_id)
      setActiveUserIdState(result.user_id)
      startTransition(() => navigate('/dashboard'))
    },
  })

  const syncStocksMutation = useMutation({ mutationFn: api.syncStocks })

  const syncHistoryRangeMutation = useMutation({
    mutationFn: () =>
      api.syncHistoryRange({
        user_id: activeUserId ?? undefined,
        codes: manualOverrideCodes,
        start_date: rangeStart,
        end_date: rangeEnd,
      }),
  })

  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    bootstrapMutation.mutate({
      ...form,
      positions: positions.filter((position) => position.code.trim().length > 0),
    })
  }

  const resetWorkspace = () => {
    clearActiveUserId()
    setActiveUserIdState(null)
    clearedInvalidWorkspace.current = false
    hydrated.current = false
    setPositions([])
    setOverrideCodes('')
    setForm({
      username: '',
      email: '',
      initial_cash: 1_000_000,
      available_cash: 1_000_000,
      positions: [],
    })
  }

  useEffect(() => {
    if (activeUserId === null || clearedInvalidWorkspace.current) {
      return
    }

    if (!userQuery.error && !positionsQuery.error) {
      return
    }

    clearedInvalidWorkspace.current = true
    resetWorkspace()
  }, [activeUserId, positionsQuery.error, userQuery.error])

  const previewCodes = manualOverrideCodes ?? syncTargetsQuery.data?.codes ?? []
  const isSyncBusy = syncStocksMutation.isPending || syncHistoryRangeMutation.isPending
  const syncTargetCount = previewCodes.length || syncTargetsQuery.data?.codes.length || 0
  const syncSelectionMode = manualOverrideCodes ? 'custom' : 'default'
  const syncProgressTitle = syncStocksMutation.isPending ? '正在更新股票主檔' : '正在同步指定區間'
  const syncProgressSummary = syncStocksMutation.isPending
    ? `正在更新股票主檔與預設同步池，完成後會套用到目前 ${syncTargetsQuery.data?.codes.length ?? 0} 檔預設同步股票。`
    : `正在同步 ${syncTargetCount} 檔股票，區間為 ${rangeStart} 至 ${rangeEnd}。`
  const failedRangeCodes = syncHistoryRangeMutation.data?.failed_codes ?? []

  useEffect(() => {
    if (!isSyncBusy) {
      setSyncElapsedSeconds(0)
      return
    }

    setSyncElapsedSeconds(0)
    const timer = window.setInterval(() => {
      setSyncElapsedSeconds((current) => current + 1)
    }, 1000)

    return () => window.clearInterval(timer)
  }, [isSyncBusy])

  return (
    <div className="page-grid page-grid--setup">
      <section className="hero-strip setup-hero">
        <div className="setup-hero-layout">
          <div className="setup-hero-copy">
            <p className="hero-kicker">Workspace Setup</p>
            <h2>設定工作區與同步範圍</h2>
            <p>工作區設定只保留資產、持倉與資料同步三件事，讓日常維護更單純。</p>
          </div>

          <div className="setup-hero-highlights">
            <article className="setup-highlight-card">
              <span>可用現金</span>
              <strong>{formatCurrency(form.available_cash)}</strong>
              <p>會作為目前工作區的帳戶基礎。</p>
            </article>
            <article className="setup-highlight-card">
              <span>已設定持倉</span>
              <strong>{configuredPositions}</strong>
              <p>建立完成後會同步寫進投資組合。</p>
            </article>
            <article className="setup-highlight-card">
              <span>預設同步股票</span>
              <strong>{syncTargetsQuery.data?.codes.length ?? 0}</strong>
              <p>預設來自自選關注清單與科技、金融產業股票池。</p>
            </article>
          </div>
        </div>
      </section>

      <Panel
        title="工作區設定"
        subtitle="Workspace"
        action={
          activeUserId ? (
            <button className="ghost-button" type="button" onClick={resetWorkspace}>
              <RefreshCcw size={16} />
              清除工作區
            </button>
          ) : null
        }
      >
        <div className="setup-summary-grid">
          <article className="setup-summary-card">
            <span>工作區狀態</span>
            <strong>{activeUserId ? '已啟用' : '尚未建立'}</strong>
            <p>{activeUserId ? '目前可以直接維護持倉與同步資料。' : '先建立工作區，後續頁面才會有完整資料。'}</p>
          </article>
          <article className="setup-summary-card">
            <span>初始資金</span>
            <strong>{formatCurrency(form.initial_cash)}</strong>
            <p>可作為帳戶基準與後續績效參考。</p>
          </article>
          <article className="setup-summary-card">
            <span>同步預覽</span>
            <strong>{previewCodes.length} 檔</strong>
            <p>{manualOverrideCodes ? '這次同步會改用你手動指定的股票。' : '未指定代碼時，會沿用預設同步股票池。'}</p>
          </article>
        </div>

        <form className="setup-form" onSubmit={handleSubmit}>
          <div className="form-grid">
            <label>
              使用者名稱
              <input
                value={form.username}
                onChange={(event) => setForm((current) => ({ ...current, username: event.target.value }))}
                placeholder="alex"
                required
              />
            </label>
            <label>
              Email
              <input
                type="email"
                value={form.email}
                onChange={(event) => setForm((current) => ({ ...current, email: event.target.value }))}
                placeholder="alex@example.com"
                required
              />
            </label>
            <label>
              初始資金
              <input
                type="number"
                min={1}
                inputMode="numeric"
                value={form.initial_cash}
                onWheel={(event) => event.currentTarget.blur()}
                onChange={(event) => setForm((current) => ({ ...current, initial_cash: Number(event.target.value) }))}
                required
              />
            </label>
            <label>
              可用現金
              <input
                type="number"
                min={0}
                inputMode="numeric"
                value={form.available_cash}
                onWheel={(event) => event.currentTarget.blur()}
                onChange={(event) => setForm((current) => ({ ...current, available_cash: Number(event.target.value) }))}
                required
              />
            </label>
          </div>

          <div className="setup-subsection">
            <div className="setup-subsection-head">
              <div>
                <h3>持倉設定</h3>
                <p>把你已經持有的股票與成本放在這裡，後續工作臺和投資組合會直接沿用。</p>
              </div>
              <span className="setup-badge">{configuredPositions} 檔</span>
            </div>
            <PositionEditor positions={positions} onChange={setPositions} />
          </div>

          {bootstrapMutation.error ? <p className="error-text">{bootstrapMutation.error.message}</p> : null}

          <div className="inline-actions">
            <button className="primary-button" type="submit" disabled={bootstrapMutation.isPending}>
              <ArrowRight size={16} />
              {activeUserId ? '更新工作區' : '建立工作區'}
            </button>
            <button className="ghost-button" type="button" onClick={() => setPositions((current) => [...current, emptyPosition])}>
              新增持倉
            </button>
          </div>
        </form>
      </Panel>

      <Panel title="資料同步" subtitle="Data Sync">
        <div className="stack-form">
          {isSyncBusy ? (
            <div className="setup-progress-card" aria-live="polite">
              <div className="setup-progress-head">
                <div>
                  <p className="setup-progress-kicker">Sync In Progress</p>
                  <strong>{syncProgressTitle}</strong>
                </div>
                <span className="setup-progress-badge">
                  <LoaderCircle className="spinning-icon" size={14} />
                  處理中
                </span>
              </div>

              <p className="muted-text">{syncProgressSummary}</p>

              <div className="setup-progress-bar" aria-hidden="true">
                <span />
              </div>

              <div className="setup-progress-meta">
                <span>已等待 {formatElapsedTime(syncElapsedSeconds)}</span>
                <span>{syncTargetCount} 檔股票</span>
              </div>

              <p className="setup-progress-caption">{getProgressHint(syncElapsedSeconds)}</p>
            </div>
          ) : null}

          <div className="setup-sync-card setup-sync-card--feature">
            <div className="setup-sync-header">
              <div>
                <h3>同步規則總覽</h3>
                <p className="muted-text">
                  沒有填入股票代碼時，會使用預設同步池；只要填入代碼，這次同步就只處理你指定的股票。
                </p>
              </div>
              <span className={`setup-mode-pill ${syncSelectionMode === 'custom' ? 'setup-mode-pill--custom' : ''}`}>
                {syncSelectionMode === 'custom' ? '手動指定' : '預設同步池'}
              </span>
            </div>

            <div className="setup-summary-grid">
              <article className="setup-summary-card">
                <span>自選股票</span>
                <strong>{syncTargetsQuery.data?.watchlist_codes.length ?? 0}</strong>
                <p>來自關注清單頁的自選股票。</p>
              </article>
              <article className="setup-summary-card">
                <span>預設股票池</span>
                <strong>{syncTargetsQuery.data?.default_pool_codes.length ?? 0}</strong>
                <p>來自 stocks 表的科技與金融產業篩選。</p>
              </article>
              <article className="setup-summary-card">
                <span>本次同步</span>
                <strong>{syncTargetCount}</strong>
                <p>{manualOverrideCodes ? '已切換成手動指定代碼。' : '未指定代碼時會使用預設同步池。'}</p>
              </article>
            </div>

            <div className="setup-sync-overview">
              <div className="setup-chip-panel">
                <div className="setup-chip-panel-head">
                  <strong>{manualOverrideCodes ? '本次實際會同步的股票' : '預設同步股票池'}</strong>
                  <span>{syncTargetCount} 檔</span>
                </div>
                <p className="setup-chip-panel-note">
                  {manualOverrideCodes
                    ? '這次會忽略預設同步池，只針對下方輸入的代碼同步歷史資料。'
                    : '預設會合併自選關注清單與科技、金融產業股票池，重複股票只會處理一次。'}
                </p>

                {previewCodes.length > 0 ? (
                  <div className="chip-row">
                    {previewCodes.slice(0, 30).map((code) => (
                      <span className="setup-chip" key={code}>
                        {code}
                      </span>
                    ))}
                  </div>
                ) : (
                  <p className="muted-text">目前還沒有可同步的股票，請先更新股票主檔或檢查來源設定。</p>
                )}
              </div>

              <div className="setup-action-stack">
                <div className="setup-meta-row">
                  <span>預設池 {syncTargetsQuery.data?.default_pool_codes.length ?? 0} 檔</span>
                  <span>產業 {syncTargetsQuery.data?.default_pool_industries.length ?? 0} 類</span>
                </div>
                <button className="ghost-button" type="button" onClick={() => syncStocksMutation.mutate()} disabled={isSyncBusy}>
                  {syncStocksMutation.isPending ? '更新中...' : '更新股票主檔'}
                </button>
                <p className="muted-text">
                  更新股票主檔後，預設同步池會重新依 `stocks` 表中的產業欄位篩出科技與金融股。
                </p>
              </div>
            </div>
          </div>

          <div className="setup-sync-grid">
            <div className="setup-sync-card">
              <h3>本次同步指定代碼</h3>
              <label>
                只同步這些股票
                <input
                  value={overrideCodes}
                  disabled={isSyncBusy}
                  onChange={(event) => setOverrideCodes(event.target.value)}
                  placeholder="例如：2330, 2317, 2454"
                />
              </label>
              <p className="muted-text">支援逗號、空白或換行分隔。只要有填入代碼，這次同步就不會使用預設同步池。</p>
              <div className="inline-actions">
                <button
                  className="ghost-button"
                  type="button"
                  onClick={() => setOverrideCodes('')}
                  disabled={isSyncBusy || !overrideCodes.trim()}
                >
                  清除指定代碼
                </button>
              </div>
            </div>

            <div className="setup-sync-card">
              <h3>同步前提醒</h3>
              <p className="muted-text">如果你要跑完整預設池，這裡保持空白即可。若只想補幾檔股票歷史資料，再填入代碼就好。</p>
              <div className="setup-summary-grid setup-summary-grid--compact">
                <article className="setup-summary-card">
                  <span>同步模式</span>
                  <strong>{syncSelectionMode === 'custom' ? '手動指定' : '預設池'}</strong>
                  <p>{syncSelectionMode === 'custom' ? '只同步輸入代碼。' : '同步關注清單加科技、金融產業股票池。'}</p>
                </article>
                <article className="setup-summary-card">
                  <span>同步檔數</span>
                  <strong>{syncTargetCount}</strong>
                  <p>目前依畫面設定估算的本次同步目標。</p>
                </article>
              </div>
            </div>

            <div className="setup-sync-card setup-sync-card--wide setup-sync-card--accent">
              <h3>同步指定區間</h3>
              <div className="form-grid">
                <label>
                  開始日期
                  <input type="date" value={rangeStart} disabled={isSyncBusy} onChange={(event) => setRangeStart(event.target.value)} />
                </label>
                <label>
                  結束日期
                  <input type="date" value={rangeEnd} disabled={isSyncBusy} onChange={(event) => setRangeEnd(event.target.value)} />
                </label>
              </div>
              <button className="primary-button" type="button" onClick={() => syncHistoryRangeMutation.mutate()} disabled={isSyncBusy}>
                {syncHistoryRangeMutation.isPending ? '同步中...' : '同步區間資料'}
              </button>
            </div>
          </div>

          {syncTargetsQuery.error ? <p className="error-text">{syncTargetsQuery.error.message}</p> : null}
          {syncStocksMutation.data ? <p className="success-text">已更新 {syncStocksMutation.data.synced_count} 檔股票主檔。</p> : null}
          {syncHistoryRangeMutation.data ? (
            <p className="success-text">
              已同步 {syncHistoryRangeMutation.data.synced_rows} 筆區間資料，涵蓋 {syncHistoryRangeMutation.data.synced_codes} 檔股票。
            </p>
          ) : null}
          {failedRangeCodes.length > 0 ? <p className="error-text">同步失敗的股票：{failedRangeCodes.join(', ')}</p> : null}
          {syncStocksMutation.error ? <p className="error-text">{syncStocksMutation.error.message}</p> : null}
          {syncHistoryRangeMutation.error ? <p className="error-text">{syncHistoryRangeMutation.error.message}</p> : null}
        </div>
      </Panel>
    </div>
  )
}
