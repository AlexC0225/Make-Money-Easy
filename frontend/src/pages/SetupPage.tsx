import { startTransition, useEffect, useRef, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { ArrowRight, RefreshCcw } from 'lucide-react'
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
    .split(',')
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

export function SetupPage() {
  const navigate = useNavigate()
  const [activeUserId, setActiveUserIdState] = useState<number | null>(() => getActiveUserId())
  const hydrated = useRef(false)
  const clearedInvalidWorkspace = useRef(false)
  const [positions, setPositions] = useState<ManualPositionInput[]>([])
  const [overrideCodes, setOverrideCodes] = useState('')
  const [historyYear, setHistoryYear] = useState(new Date().getFullYear())
  const [historyMonth, setHistoryMonth] = useState(new Date().getMonth() + 1)
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

  const syncHistoryMutation = useMutation({
    mutationFn: () =>
      api.syncHistory({
        user_id: activeUserId ?? undefined,
        codes: manualOverrideCodes,
        year: historyYear,
        month: historyMonth,
      }),
  })

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
              <p>預設來自自選關注清單與 0050 成分股。</p>
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
          <div className="setup-sync-card">
            <h3>預設同步範圍</h3>
            <p className="muted-text">預設同步會合併自選關注清單與 0050 成分股，重複股票只會處理一次。</p>

            <div className="setup-summary-grid">
              <article className="setup-summary-card">
                <span>自選股票</span>
                <strong>{syncTargetsQuery.data?.watchlist_codes.length ?? 0}</strong>
                <p>來自關注清單頁的自選股票。</p>
              </article>
              <article className="setup-summary-card">
                <span>0050 成分股</span>
                <strong>{syncTargetsQuery.data?.benchmark_codes.length ?? 0}</strong>
                <p>來自 0050 成分股快照。</p>
              </article>
              <article className="setup-summary-card">
                <span>實際同步</span>
                <strong>{syncTargetsQuery.data?.codes.length ?? 0}</strong>
                <p>去重後真正會同步的股票數量。</p>
              </article>
            </div>

            <div className="setup-meta-row">
              <span>公告日 {syncTargetsQuery.data?.announce_date ?? '--'}</span>
              <span>交易日 {syncTargetsQuery.data?.trade_date ?? '--'}</span>
            </div>

            {previewCodes.length > 0 ? (
              <div className="chip-row">
                {previewCodes.slice(0, 24).map((code) => (
                  <span className="setup-chip" key={code}>
                    {code}
                  </span>
                ))}
              </div>
            ) : null}
          </div>

          <div className="setup-sync-grid">
            <div className="setup-sync-card">
              <h3>本次同步覆蓋代碼</h3>
              <label>
                只同步這些股票
                <input
                  value={overrideCodes}
                  onChange={(event) => setOverrideCodes(event.target.value)}
                  placeholder="例如：2330,2317,2454"
                />
              </label>
              <p className="muted-text">若有填入代碼，這次同步只會處理這份清單，不再使用預設同步池。</p>
              <button className="ghost-button" type="button" onClick={() => syncStocksMutation.mutate()}>
                更新股票主檔
              </button>
            </div>

            <div className="setup-sync-card">
              <h3>同步當月資料</h3>
              <div className="form-grid form-grid--three">
                <label>
                  年
                  <input
                    type="number"
                    value={historyYear}
                    onWheel={(event) => event.currentTarget.blur()}
                    onChange={(event) => setHistoryYear(Number(event.target.value))}
                  />
                </label>
                <label>
                  月
                  <input
                    type="number"
                    value={historyMonth}
                    onWheel={(event) => event.currentTarget.blur()}
                    onChange={(event) => setHistoryMonth(Number(event.target.value))}
                  />
                </label>
                <label className="align-end">
                  <button className="secondary-button" type="button" onClick={() => syncHistoryMutation.mutate()}>
                    同步當月
                  </button>
                </label>
              </div>
            </div>

            <div className="setup-sync-card setup-sync-card--wide">
              <h3>同步指定區間</h3>
              <div className="form-grid">
                <label>
                  開始日期
                  <input type="date" value={rangeStart} onChange={(event) => setRangeStart(event.target.value)} />
                </label>
                <label>
                  結束日期
                  <input type="date" value={rangeEnd} onChange={(event) => setRangeEnd(event.target.value)} />
                </label>
              </div>
              <button className="primary-button" type="button" onClick={() => syncHistoryRangeMutation.mutate()}>
                同步區間資料
              </button>
            </div>
          </div>

          {syncTargetsQuery.error ? <p className="error-text">{syncTargetsQuery.error.message}</p> : null}
          {syncStocksMutation.data ? <p className="success-text">已更新 {syncStocksMutation.data.synced_count} 檔股票主檔。</p> : null}
          {syncHistoryMutation.data ? (
            <p className="success-text">
              已同步 {syncHistoryMutation.data.synced_rows} 筆當月資料，涵蓋 {syncHistoryMutation.data.synced_codes} 檔股票。
            </p>
          ) : null}
          {syncHistoryRangeMutation.data ? (
            <p className="success-text">
              已同步 {syncHistoryRangeMutation.data.synced_rows} 筆區間資料，涵蓋 {syncHistoryRangeMutation.data.synced_codes} 檔股票。
            </p>
          ) : null}
          {syncStocksMutation.error ? <p className="error-text">{syncStocksMutation.error.message}</p> : null}
          {syncHistoryMutation.error ? <p className="error-text">{syncHistoryMutation.error.message}</p> : null}
          {syncHistoryRangeMutation.error ? <p className="error-text">{syncHistoryRangeMutation.error.message}</p> : null}
        </div>
      </Panel>
    </div>
  )
}
