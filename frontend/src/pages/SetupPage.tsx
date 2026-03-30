import { startTransition, useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowRight, LoaderCircle, RefreshCcw } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

import { api } from '../api'
import { Panel } from '../components/Panel'
import { PositionEditor } from '../components/PositionEditor'
import { formatCurrency } from '../lib/format'
import {
  clearActiveSyncRun,
  clearActiveUserId,
  getActiveSyncRun,
  getActiveUserId,
  setActiveSyncRun,
  setActiveUserId,
  subscribeStorageUpdated,
  type ActiveSyncRun,
} from '../lib/storage'
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

function createSyncRunId(prefix: string) {
  const randomId =
    typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(16).slice(2)}`

  return `${prefix}-${randomId}`
}

function getElapsedSeconds(startedAt: string, finishedAt?: string | null) {
  const startedMs = new Date(startedAt).getTime()
  const endedMs = finishedAt ? new Date(finishedAt).getTime() : Date.now()
  return Math.max(0, Math.floor((endedMs - startedMs) / 1000))
}

function formatElapsedTime(totalSeconds: number) {
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60

  if (minutes <= 0) {
    return `${seconds} 秒`
  }

  return `${minutes} 分 ${String(seconds).padStart(2, '0')} 秒`
}

function getSyncProgressHint(jobName: ActiveSyncRun['job_name'], totalSeconds: number) {
  if (jobName === 'sync-stocks') {
    if (totalSeconds < 8) {
      return '已送出更新股票池請求，正在整理觀察清單與預設同步池。'
    }

    return '後端會逐步更新股票主檔與同步池內容，完成後後續同步就會使用最新標的。'
  }

  if (totalSeconds < 8) {
    return '已送出歷史資料同步請求，正在整理這次要同步的股票名單。'
  }

  if (totalSeconds < 18) {
    return '後端會逐檔查詢資料，查完一檔就立刻寫入資料庫，不會等整批查完才落庫。'
  }

  return '同步仍在進行中。你可以切換到其他頁面，後端會繼續跑，之後回來再看進度即可。'
}

function getProgressTitle(jobName: ActiveSyncRun['job_name']) {
  return jobName === 'sync-stocks' ? '更新股票池' : '同步歷史區間'
}

function getProgressStatusLabel(status?: 'running' | 'completed' | 'failed') {
  if (status === 'completed') {
    return '已完成'
  }

  if (status === 'failed') {
    return '失敗'
  }

  return '進行中'
}

export function SetupPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [activeUserId, setActiveUserIdState] = useState<number | null>(() => getActiveUserId())
  const [activeSyncRun, setActiveSyncRunState] = useState<ActiveSyncRun | null>(() => getActiveSyncRun())
  const [syncElapsedSeconds, setSyncElapsedSeconds] = useState(0)
  const [hydrated, setHydrated] = useState(false)
  const [clearedInvalidWorkspace, setClearedInvalidWorkspace] = useState(false)
  const [positions, setPositions] = useState<ManualPositionInput[]>([])
  const [overrideCodes, setOverrideCodes] = useState('')
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

  useEffect(() => {
    return subscribeStorageUpdated(() => {
      setActiveUserIdState(getActiveUserId())
      setActiveSyncRunState(getActiveSyncRun())
    })
  }, [])

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
    if (!userQuery.data || !positionsQuery.data || hydrated) {
      return
    }

    setHydrated(true)
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
  }, [hydrated, positionsQuery.data, userQuery.data])

  const bootstrapMutation = useMutation({
    mutationFn: api.bootstrapPortfolio,
    onSuccess: (result) => {
      setActiveUserId(result.user_id)
      setActiveUserIdState(result.user_id)
      startTransition(() => navigate('/dashboard'))
    },
  })

  const syncStocksMutation = useMutation({
    mutationFn: (runId: string) => api.syncStocks(runId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['sync-targets', activeUserId] })
    },
  })

  const syncHistoryRangeMutation = useMutation({
    mutationFn: (runId: string) =>
      api.syncHistoryRange({
        user_id: activeUserId ?? undefined,
        codes: manualOverrideCodes,
        start_date: rangeStart,
        end_date: rangeEnd,
        run_id: runId,
      }),
  })

  const syncProgressQuery = useQuery({
    queryKey: ['sync-progress', activeSyncRun?.run_id],
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
    if (!activeSyncRun) {
      setSyncElapsedSeconds(0)
      return
    }

    const updateElapsed = () => {
      setSyncElapsedSeconds(getElapsedSeconds(activeSyncRun.started_at, syncProgressQuery.data?.finished_at))
    }

    updateElapsed()
    if (syncProgressQuery.data?.status !== 'running') {
      return
    }

    const timer = window.setInterval(updateElapsed, 1000)
    return () => window.clearInterval(timer)
  }, [activeSyncRun, syncProgressQuery.data?.finished_at, syncProgressQuery.data?.status])

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
    setClearedInvalidWorkspace(false)
    setHydrated(false)
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
    if (activeUserId === null || clearedInvalidWorkspace) {
      return
    }

    if (!userQuery.error && !positionsQuery.error) {
      return
    }

    setClearedInvalidWorkspace(true)
    resetWorkspace()
  }, [activeUserId, clearedInvalidWorkspace, positionsQuery.error, userQuery.error])

  const previewCodes = manualOverrideCodes ?? syncTargetsQuery.data?.codes ?? []
  const syncTargetCount = previewCodes.length || syncTargetsQuery.data?.codes.length || 0
  const syncSelectionMode = manualOverrideCodes ? 'custom' : 'default'
  const skippedRangeCodes = syncHistoryRangeMutation.data?.skipped_codes ?? syncProgressQuery.data?.skipped_codes ?? []
  const failedRangeCodes = syncHistoryRangeMutation.data?.failed_codes ?? syncProgressQuery.data?.failed_codes ?? []
  const syncedRangeCodes = syncHistoryRangeMutation.data?.codes ?? []
  const syncedRangeSelectionLabel =
    syncHistoryRangeMutation.data?.selection_mode === 'custom' ? '手動清單' : '預設同步池'
  const syncedRangeCodeSummary =
    syncedRangeCodes.length > 8
      ? `${syncedRangeCodes.slice(0, 8).join('、')} 等 ${syncedRangeCodes.length} 檔`
      : syncedRangeCodes.join('、')

  const syncProgress = syncProgressQuery.data
  const syncStatus = syncProgress?.status ?? (activeSyncRun ? 'running' : undefined)
  const isSyncBusy = syncStatus === 'running' || syncStocksMutation.isPending || syncHistoryRangeMutation.isPending
  const syncProgressTotal =
    syncProgress?.total_codes ??
    (activeSyncRun?.job_name === 'sync-history-range' ? syncTargetCount : syncTargetsQuery.data?.codes.length ?? 0)
  const syncProgressCompleted = syncProgress?.completed_codes ?? 0
  const syncProgressSuccessful = syncProgress?.synced_codes ?? 0
  const syncProgressSkipped = syncProgress?.skipped_codes.length ?? 0
  const syncProgressFailed = syncProgress?.failed_codes.length ?? 0
  const syncProgressPercent =
    syncProgressTotal > 0 ? Math.round((syncProgressCompleted / syncProgressTotal) * 100) : undefined
  const syncProgressSummaryText =
    syncProgressTotal > 0 ? `${syncProgressCompleted} / ${syncProgressTotal}` : '準備中'
  const syncProgressSummary =
    activeSyncRun?.job_name === 'sync-stocks'
      ? '更新股票池與後續同步目標，完成後新的預設同步池會立即生效。'
      : `同步 ${rangeStart} 到 ${rangeEnd} 的歷史資料。這次預計處理 ${syncTargetCount} 檔標的。`
  const syncProgressCaption = syncProgress?.current_code
    ? `目前正在同步 ${syncProgress.current_code}，已完成 ${syncProgressSummaryText}。`
    : activeSyncRun
      ? getSyncProgressHint(activeSyncRun.job_name, syncElapsedSeconds)
      : ''

  const startSyncStocks = () => {
    const run = {
      run_id: createSyncRunId('sync-stocks'),
      job_name: 'sync-stocks' as const,
      label: '更新股票池',
      started_at: new Date().toISOString(),
    }

    setActiveSyncRun(run)
    setActiveSyncRunState(run)
    syncStocksMutation.mutate(run.run_id)
  }

  const startSyncHistoryRange = () => {
    const run = {
      run_id: createSyncRunId('sync-history-range'),
      job_name: 'sync-history-range' as const,
      label: '同步歷史區間',
      started_at: new Date().toISOString(),
    }

    setActiveSyncRun(run)
    setActiveSyncRunState(run)
    syncHistoryRangeMutation.mutate(run.run_id)
  }

  return (
    <div className="page-grid page-grid--setup">
      <section className="hero-strip setup-hero">
        <div className="setup-hero-layout">
          <div className="setup-hero-copy">
            <p className="hero-kicker">Workspace Setup</p>
            <h2>建立工作區並管理同步流程</h2>
            <p>在同一頁完成資金、持股、預設同步池與歷史資料更新，整個準備流程會更順手。</p>
          </div>

          <div className="setup-hero-highlights">
            <article className="setup-highlight-card">
              <span>可用現金</span>
              <strong>{formatCurrency(form.available_cash)}</strong>
              <p>作為目前工作區的可用資金餘額。</p>
            </article>
            <article className="setup-highlight-card">
              <span>已設定持倉</span>
              <strong>{configuredPositions}</strong>
              <p>這裡輸入的部位會一併帶入工作區。</p>
            </article>
            <article className="setup-highlight-card">
              <span>同步目標</span>
              <strong>{syncTargetsQuery.data?.codes.length ?? 0}</strong>
              <p>目前預設同步池的標的數量預覽。</p>
            </article>
          </div>
        </div>
      </section>

      <Panel
        title="工作區"
        subtitle="基礎設定"
        action={
          activeUserId ? (
            <button className="ghost-button" type="button" onClick={resetWorkspace}>
              <RefreshCcw size={16} />
              重設工作區
            </button>
          ) : null
        }
      >
        <div className="setup-summary-grid">
          <article className="setup-summary-card">
            <span>目前狀態</span>
            <strong>{activeUserId ? '工作區已啟用' : '尚未建立工作區'}</strong>
            <p>{activeUserId ? '你可以繼續編輯目前工作區內容。' : '先建立工作區，才能使用同步與策略功能。'}</p>
          </article>
          <article className="setup-summary-card">
            <span>初始資金</span>
            <strong>{formatCurrency(form.initial_cash)}</strong>
            <p>這是帳戶快照使用的起始資金。</p>
          </article>
          <article className="setup-summary-card">
            <span>本次同步範圍</span>
            <strong>{previewCodes.length}</strong>
            <p>{manualOverrideCodes ? '目前以手動輸入代碼為主。' : '目前會使用預設同步池。'}</p>
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
              電子郵件
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
                <h3>手動持倉</h3>
                <p>把目前部位輸入進來，之後工作區、回測與策略執行都能沿用這份快照。</p>
              </div>
              <span className="setup-badge">{configuredPositions}</span>
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

      <Panel title="資料同步" subtitle="Market Data">
        <div className="stack-form">
          {activeSyncRun ? (
            <div className="setup-progress-card" aria-live="polite">
              <div className="setup-progress-head">
                <div>
                  <p className="setup-progress-kicker">同步狀態</p>
                  <strong>{getProgressTitle(activeSyncRun.job_name)}</strong>
                </div>
                <span className="setup-progress-badge">
                  {syncStatus === 'running' ? <LoaderCircle className="spinning-icon" size={14} /> : null}
                  {getProgressStatusLabel(syncStatus)}
                </span>
              </div>

              <p className="muted-text">{syncProgressSummary}</p>

              <div
                className={`setup-progress-bar ${syncProgressPercent !== undefined ? 'setup-progress-bar--determinate' : ''}`}
                aria-hidden="true"
              >
                <span style={syncProgressPercent !== undefined ? { width: `${syncProgressPercent}%` } : undefined} />
              </div>

              <div className="setup-progress-meta">
                <span>耗時 {formatElapsedTime(syncElapsedSeconds)}</span>
                <span>完成 {syncProgressSummaryText}</span>
                <span>成功 {syncProgressSuccessful}</span>
                <span>跳過 {syncProgressSkipped}</span>
                <span>失敗 {syncProgressFailed}</span>
              </div>

              <p className="setup-progress-caption">{syncProgressCaption}</p>

              {syncProgress?.error_message ? <p className="error-text">{syncProgress.error_message}</p> : null}

              {syncStatus !== 'running' ? (
                <div className="inline-actions">
                  <button className="ghost-button" type="button" onClick={clearActiveSyncRun}>
                    清除同步狀態
                  </button>
                </div>
              ) : null}
            </div>
          ) : null}

          <div className="setup-sync-card setup-sync-card--feature">
            <div className="setup-sync-header">
              <div>
                <h3>同步池總覽</h3>
                <p className="muted-text">先確認觀察清單、預設同步池與本次實際會跑的標的範圍。</p>
              </div>
              <span className={`setup-mode-pill ${syncSelectionMode === 'custom' ? 'setup-mode-pill--custom' : ''}`}>
                {syncSelectionMode === 'custom' ? '手動模式' : '預設模式'}
              </span>
            </div>

            <div className="setup-summary-grid">
              <article className="setup-summary-card">
                <span>觀察清單</span>
                <strong>{syncTargetsQuery.data?.watchlist_codes.length ?? 0}</strong>
                <p>來自目前工作區觀察清單的標的。</p>
              </article>
              <article className="setup-summary-card">
                <span>預設同步池</span>
                <strong>{syncTargetsQuery.data?.default_pool_codes.length ?? 0}</strong>
                <p>依預設篩選條件組成的同步名單。</p>
              </article>
              <article className="setup-summary-card">
                <span>本次有效範圍</span>
                <strong>{syncTargetCount}</strong>
                <p>{manualOverrideCodes ? '這次會以手動代碼清單為主。' : '這次會以預設同步池為主。'}</p>
              </article>
            </div>

            <div className="setup-sync-overview">
              <div className="setup-chip-panel">
                <div className="setup-chip-panel-head">
                  <strong>{manualOverrideCodes ? '本次手動同步代碼' : '預設同步池預覽'}</strong>
                  <span>{syncTargetCount}</span>
                </div>
                <p className="setup-chip-panel-note">
                  {manualOverrideCodes ? '本次只會同步你下方輸入的股票代碼。' : '預覽清單會合併觀察清單與目前預設同步池。'}
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
                  <p className="muted-text">目前沒有可同步標的，建議先更新一次股票池。</p>
                )}
              </div>

              <div className="setup-action-stack">
                <div className="setup-meta-row">
                  <span>預設同步池 {syncTargetsQuery.data?.default_pool_codes.length ?? 0}</span>
                  <span>產業數 {syncTargetsQuery.data?.default_pool_industries.length ?? 0}</span>
                </div>
                <button className="ghost-button" type="button" onClick={startSyncStocks} disabled={isSyncBusy}>
                  {syncStocksMutation.isPending ? '更新中...' : '更新股票池'}
                </button>
                <p className="muted-text">
                  更新股票池後，後續的歷史資料同步與策略資料來源都會跟著採用最新範圍。
                </p>
              </div>
            </div>
          </div>

          <div className="setup-sync-grid">
            <div className="setup-sync-card">
              <h3>手動指定代碼</h3>
              <label>
                覆蓋同步標的
                <input
                  value={overrideCodes}
                  disabled={isSyncBusy}
                  onChange={(event) => setOverrideCodes(event.target.value)}
                  placeholder="2330, 2317, 2454"
                />
              </label>
              <p className="muted-text">可用空白或逗號分隔。留白時就會使用預設同步池。</p>
              <div className="inline-actions">
                <button
                  className="ghost-button"
                  type="button"
                  onClick={() => setOverrideCodes('')}
                  disabled={isSyncBusy || !overrideCodes.trim()}
                >
                  清空
                </button>
              </div>
            </div>

            <div className="setup-sync-card">
              <h3>同步計畫</h3>
              <p className="muted-text">在送出前先確認模式與預估批次大小，避免跑到不是你想同步的範圍。</p>
              <div className="setup-summary-grid setup-summary-grid--compact">
                <article className="setup-summary-card">
                  <span>模式</span>
                  <strong>{syncSelectionMode === 'custom' ? '手動' : '預設'}</strong>
                  <p>{syncSelectionMode === 'custom' ? '只同步手動輸入的代碼。' : '同步目前預設同步池。'}</p>
                </article>
                <article className="setup-summary-card">
                  <span>標的數</span>
                  <strong>{syncTargetCount}</strong>
                  <p>下一次歷史資料同步預估會處理的檔數。</p>
                </article>
              </div>
            </div>

            <div className="setup-sync-card setup-sync-card--wide setup-sync-card--accent">
              <h3>歷史資料區間</h3>
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
              <button className="primary-button" type="button" onClick={startSyncHistoryRange} disabled={isSyncBusy}>
                {syncHistoryRangeMutation.isPending ? '同步中...' : '同步歷史資料'}
              </button>
            </div>
          </div>

          {syncTargetsQuery.error ? <p className="error-text">{syncTargetsQuery.error.message}</p> : null}
          {syncStocksMutation.data ? <p className="success-text">股票池已更新，共整理 {syncStocksMutation.data.synced_count} 檔標的。</p> : null}
          {syncHistoryRangeMutation.data ? (
            <p className="success-text">
              已同步 {syncHistoryRangeMutation.data.synced_rows} 筆資料，涵蓋 {syncHistoryRangeMutation.data.synced_codes} 檔標的。
              已跳過 {syncHistoryRangeMutation.data.skipped_codes.length} 檔已存在區間資料的標的。
              模式：{syncedRangeSelectionLabel}。股票：{syncedRangeCodeSummary || '無'}。
            </p>
          ) : null}
          {skippedRangeCodes.length > 0 ? <p className="muted-text">已跳過標的：{skippedRangeCodes.join('、')}</p> : null}
          {failedRangeCodes.length > 0 ? <p className="error-text">失敗標的：{failedRangeCodes.join('、')}</p> : null}
          {syncStocksMutation.error ? <p className="error-text">{syncStocksMutation.error.message}</p> : null}
          {syncHistoryRangeMutation.error ? <p className="error-text">{syncHistoryRangeMutation.error.message}</p> : null}
        </div>
      </Panel>
    </div>
  )
}
