import { startTransition, useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
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
    return `${seconds}s`
  }

  return `${minutes}m ${String(seconds).padStart(2, '0')}s`
}

function getProgressHint(totalSeconds: number) {
  if (totalSeconds < 6) {
    return 'Request sent. Preparing the sync target list and validating the request.'
  }

  if (totalSeconds < 16) {
    return 'The server is fetching upstream data and writing each completed symbol to the database.'
  }

  return 'The sync is still running. Completed symbols are already being committed as the batch progresses.'
}

function createSyncRunId(prefix: string) {
  const randomId =
    typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(16).slice(2)}`

  return `${prefix}-${randomId}`
}

export function SetupPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [activeUserId, setActiveUserIdState] = useState<number | null>(() => getActiveUserId())
  const hydrated = useRef(false)
  const clearedInvalidWorkspace = useRef(false)
  const syncStartedAtRef = useRef<number | null>(null)
  const [positions, setPositions] = useState<ManualPositionInput[]>([])
  const [overrideCodes, setOverrideCodes] = useState('')
  const [activeSyncRunId, setActiveSyncRunId] = useState<string | null>(null)
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
    setActiveSyncRunId(null)
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

  const syncProgressQuery = useQuery({
    queryKey: ['sync-progress', activeSyncRunId],
    queryFn: () => api.getSyncProgress(activeSyncRunId!),
    enabled: activeSyncRunId !== null,
    retry: false,
    staleTime: 0,
    refetchOnWindowFocus: true,
    refetchInterval: isSyncBusy && activeSyncRunId ? 1000 : false,
    refetchIntervalInBackground: true,
  })

  const syncTargetCount = previewCodes.length || syncTargetsQuery.data?.codes.length || 0
  const syncSelectionMode = manualOverrideCodes ? 'custom' : 'default'
  const syncProgressTitle = syncStocksMutation.isPending ? 'Updating stock universe' : 'Syncing history range'
  const syncProgressSummary = syncStocksMutation.isPending
    ? `Refreshing the stock master and default pool. The latest target count is ${syncTargetsQuery.data?.codes.length ?? 0}.`
    : `Syncing ${syncTargetCount} symbols for ${rangeStart} to ${rangeEnd}.`
  const failedRangeCodes = syncHistoryRangeMutation.data?.failed_codes ?? []
  const syncedRangeCodes = syncHistoryRangeMutation.data?.codes ?? []
  const syncedRangeSelectionLabel =
    syncHistoryRangeMutation.data?.selection_mode === 'custom' ? 'Manual list' : 'Default pool'
  const syncedRangeCodeSummary =
    syncedRangeCodes.length > 8
      ? `${syncedRangeCodes.slice(0, 8).join(', ')} and ${syncedRangeCodes.length - 8} more`
      : syncedRangeCodes.join(', ')

  const syncProgress = syncProgressQuery.data
  const syncProgressTotal =
    syncProgress?.total_codes ?? (syncHistoryRangeMutation.isPending ? syncTargetCount : 0)
  const syncProgressCompleted = syncProgress?.completed_codes ?? 0
  const syncProgressSuccessful = syncProgress?.synced_codes ?? 0
  const syncProgressFailed = syncProgress?.failed_codes.length ?? 0
  const syncProgressPercent =
    syncProgressTotal > 0 ? Math.round((syncProgressCompleted / syncProgressTotal) * 100) : undefined
  const syncProgressSummaryText =
    syncProgressTotal > 0 ? `${syncProgressCompleted} / ${syncProgressTotal}` : 'Preparing...'
  const syncProgressCaption = syncProgress?.current_code
    ? `Now syncing ${syncProgress.current_code}. Completed ${syncProgressSummaryText}.`
    : getProgressHint(syncElapsedSeconds)

  const startSyncStocks = () => {
    const runId = createSyncRunId('sync-stocks')
    setActiveSyncRunId(runId)
    syncStocksMutation.mutate(runId, {
      onSettled: () => {
        setActiveSyncRunId((current) => (current === runId ? null : current))
      },
    })
  }

  const startSyncHistoryRange = () => {
    const runId = createSyncRunId('sync-history-range')
    setActiveSyncRunId(runId)
    syncHistoryRangeMutation.mutate(runId, {
      onSettled: () => {
        setActiveSyncRunId((current) => (current === runId ? null : current))
      },
    })
  }

  useEffect(() => {
    if (!isSyncBusy) {
      syncStartedAtRef.current = null
      setSyncElapsedSeconds(0)
      return
    }

    const startedAt = syncStartedAtRef.current ?? Date.now()
    syncStartedAtRef.current = startedAt

    const updateElapsedSeconds = () => {
      setSyncElapsedSeconds(Math.max(0, Math.floor((Date.now() - startedAt) / 1000)))
    }

    updateElapsedSeconds()
    const timer = window.setInterval(() => {
      updateElapsedSeconds()
    }, 1000)

    const handleVisibilityOrFocus = () => {
      updateElapsedSeconds()
    }

    document.addEventListener('visibilitychange', handleVisibilityOrFocus)
    window.addEventListener('focus', handleVisibilityOrFocus)

    return () => {
      window.clearInterval(timer)
      document.removeEventListener('visibilitychange', handleVisibilityOrFocus)
      window.removeEventListener('focus', handleVisibilityOrFocus)
    }
  }, [isSyncBusy])

  return (
    <div className="page-grid page-grid--setup">
      <section className="hero-strip setup-hero">
        <div className="setup-hero-layout">
          <div className="setup-hero-copy">
            <p className="hero-kicker">Workspace Setup</p>
            <h2>Prepare your workspace and market sync</h2>
            <p>Keep the portfolio workspace, manual positions, and market-data sync controls in one place.</p>
          </div>

          <div className="setup-hero-highlights">
            <article className="setup-highlight-card">
              <span>Available Cash</span>
              <strong>{formatCurrency(form.available_cash)}</strong>
              <p>Used as the current workspace cash balance.</p>
            </article>
            <article className="setup-highlight-card">
              <span>Configured Positions</span>
              <strong>{configuredPositions}</strong>
              <p>Positions entered here are reused in the workspace.</p>
            </article>
            <article className="setup-highlight-card">
              <span>Sync Targets</span>
              <strong>{syncTargetsQuery.data?.codes.length ?? 0}</strong>
              <p>Preview of the current default sync universe.</p>
            </article>
          </div>
        </div>
      </section>

      <Panel
        title="Workspace"
        subtitle="Setup"
        action={
          activeUserId ? (
            <button className="ghost-button" type="button" onClick={resetWorkspace}>
              <RefreshCcw size={16} />
              Reset Workspace
            </button>
          ) : null
        }
      >
        <div className="setup-summary-grid">
          <article className="setup-summary-card">
            <span>Status</span>
            <strong>{activeUserId ? 'Workspace ready' : 'Create a workspace'}</strong>
            <p>{activeUserId ? 'Continue editing the active workspace.' : 'Create the first workspace to unlock sync tools.'}</p>
          </article>
          <article className="setup-summary-card">
            <span>Initial Cash</span>
            <strong>{formatCurrency(form.initial_cash)}</strong>
            <p>Baseline cash for the account snapshot.</p>
          </article>
          <article className="setup-summary-card">
            <span>Current Sync Scope</span>
            <strong>{previewCodes.length}</strong>
            <p>{manualOverrideCodes ? 'Manual codes are overriding the default pool.' : 'The default pool will be used for sync.'}</p>
          </article>
        </div>

        <form className="setup-form" onSubmit={handleSubmit}>
          <div className="form-grid">
            <label>
              Username
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
              Initial Cash
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
              Available Cash
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
                <h3>Manual Positions</h3>
                <p>Enter any positions that should be stored as part of the workspace snapshot.</p>
              </div>
              <span className="setup-badge">{configuredPositions}</span>
            </div>
            <PositionEditor positions={positions} onChange={setPositions} />
          </div>

          {bootstrapMutation.error ? <p className="error-text">{bootstrapMutation.error.message}</p> : null}

          <div className="inline-actions">
            <button className="primary-button" type="submit" disabled={bootstrapMutation.isPending}>
              <ArrowRight size={16} />
              {activeUserId ? 'Update Workspace' : 'Create Workspace'}
            </button>
            <button className="ghost-button" type="button" onClick={() => setPositions((current) => [...current, emptyPosition])}>
              Add Position
            </button>
          </div>
        </form>
      </Panel>

      <Panel title="Data Sync" subtitle="Market Data">
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
                  Running
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
                <span>Elapsed {formatElapsedTime(syncElapsedSeconds)}</span>
                <span>Completed {syncProgressSummaryText}</span>
                <span>Success {syncProgressSuccessful}</span>
                <span>Failed {syncProgressFailed}</span>
              </div>

              <p className="setup-progress-caption">{syncProgressCaption}</p>
            </div>
          ) : null}

          <div className="setup-sync-card setup-sync-card--feature">
            <div className="setup-sync-header">
              <div>
                <h3>Sync Universe Overview</h3>
                <p className="muted-text">
                  Review the current watchlist, default pool, and the effective scope that will be synced.
                </p>
              </div>
              <span className={`setup-mode-pill ${syncSelectionMode === 'custom' ? 'setup-mode-pill--custom' : ''}`}>
                {syncSelectionMode === 'custom' ? 'Manual' : 'Default'}
              </span>
            </div>

            <div className="setup-summary-grid">
              <article className="setup-summary-card">
                <span>Watchlist</span>
                <strong>{syncTargetsQuery.data?.watchlist_codes.length ?? 0}</strong>
                <p>Symbols coming from the active watchlist.</p>
              </article>
              <article className="setup-summary-card">
                <span>Default Pool</span>
                <strong>{syncTargetsQuery.data?.default_pool_codes.length ?? 0}</strong>
                <p>Symbols coming from the default universe filter.</p>
              </article>
              <article className="setup-summary-card">
                <span>Effective Scope</span>
                <strong>{syncTargetCount}</strong>
                <p>{manualOverrideCodes ? 'Manual codes are in effect for this run.' : 'The default pool will be synced.'}</p>
              </article>
            </div>

            <div className="setup-sync-overview">
              <div className="setup-chip-panel">
                <div className="setup-chip-panel-head">
                  <strong>{manualOverrideCodes ? 'Manual codes for this run' : 'Default sync preview'}</strong>
                  <span>{syncTargetCount}</span>
                </div>
                <p className="setup-chip-panel-note">
                  {manualOverrideCodes
                    ? 'Only the codes entered below will be synced in this run.'
                    : 'The preview combines watchlist symbols and the current default pool.'}
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
                  <p className="muted-text">No sync targets are available yet. Refresh the stock universe first.</p>
                )}
              </div>

              <div className="setup-action-stack">
                <div className="setup-meta-row">
                  <span>Default pool {syncTargetsQuery.data?.default_pool_codes.length ?? 0}</span>
                  <span>Industries {syncTargetsQuery.data?.default_pool_industries.length ?? 0}</span>
                </div>
                <button className="ghost-button" type="button" onClick={startSyncStocks} disabled={isSyncBusy}>
                  {syncStocksMutation.isPending ? 'Updating...' : 'Refresh Stock Universe'}
                </button>
                <p className="muted-text">
                  Refreshing the stock universe updates the default sync pool used by future runs.
                </p>
              </div>
            </div>
          </div>

          <div className="setup-sync-grid">
            <div className="setup-sync-card">
              <h3>Manual Codes</h3>
              <label>
                Override symbols
                <input
                  value={overrideCodes}
                  disabled={isSyncBusy}
                  onChange={(event) => setOverrideCodes(event.target.value)}
                  placeholder="2330, 2317, 2454"
                />
              </label>
              <p className="muted-text">Separate symbols with spaces or commas. Leave blank to use the default pool.</p>
              <div className="inline-actions">
                <button
                  className="ghost-button"
                  type="button"
                  onClick={() => setOverrideCodes('')}
                  disabled={isSyncBusy || !overrideCodes.trim()}
                >
                  Clear
                </button>
              </div>
            </div>

            <div className="setup-sync-card">
              <h3>Sync Plan</h3>
              <p className="muted-text">Use the cards below to confirm the current mode and the estimated batch size.</p>
              <div className="setup-summary-grid setup-summary-grid--compact">
                <article className="setup-summary-card">
                  <span>Mode</span>
                  <strong>{syncSelectionMode === 'custom' ? 'Manual' : 'Default'}</strong>
                  <p>{syncSelectionMode === 'custom' ? 'Sync only the entered codes.' : 'Sync the combined default pool.'}</p>
                </article>
                <article className="setup-summary-card">
                  <span>Symbols</span>
                  <strong>{syncTargetCount}</strong>
                  <p>Estimated symbol count for the next run.</p>
                </article>
              </div>
            </div>

            <div className="setup-sync-card setup-sync-card--wide setup-sync-card--accent">
              <h3>History Range</h3>
              <div className="form-grid">
                <label>
                  Start date
                  <input type="date" value={rangeStart} disabled={isSyncBusy} onChange={(event) => setRangeStart(event.target.value)} />
                </label>
                <label>
                  End date
                  <input type="date" value={rangeEnd} disabled={isSyncBusy} onChange={(event) => setRangeEnd(event.target.value)} />
                </label>
              </div>
              <button className="primary-button" type="button" onClick={startSyncHistoryRange} disabled={isSyncBusy}>
                {syncHistoryRangeMutation.isPending ? 'Syncing...' : 'Sync History Range'}
              </button>
            </div>
          </div>

          {syncTargetsQuery.error ? <p className="error-text">{syncTargetsQuery.error.message}</p> : null}
          {syncStocksMutation.data ? <p className="success-text">Stock universe refreshed: {syncStocksMutation.data.synced_count} symbols.</p> : null}
          {syncHistoryRangeMutation.data ? (
            <p className="success-text">
              Synced {syncHistoryRangeMutation.data.synced_rows} rows across {syncHistoryRangeMutation.data.synced_codes} symbols.
              Mode: {syncedRangeSelectionLabel}. Symbols: {syncedRangeCodeSummary || 'n/a'}.
            </p>
          ) : null}
          {failedRangeCodes.length > 0 ? <p className="error-text">Failed symbols: {failedRangeCodes.join(', ')}</p> : null}
          {syncStocksMutation.error ? <p className="error-text">{syncStocksMutation.error.message}</p> : null}
          {syncHistoryRangeMutation.error ? <p className="error-text">{syncHistoryRangeMutation.error.message}</p> : null}
        </div>
      </Panel>
    </div>
  )
}
