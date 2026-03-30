import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CandlestickChart, RefreshCw, Wallet } from 'lucide-react'
import { Link } from 'react-router-dom'

import { api } from '../api'
import { KLineChart } from '../components/KLineChart'
import { Panel } from '../components/Panel'
import { PositionTable } from '../components/PositionTable'
import { StatCard } from '../components/StatCard'
import { StockAutocompleteInput } from '../components/StockAutocompleteInput'
import { formatCurrency } from '../lib/format'
import { getActiveUserId } from '../lib/storage'

function describeStrategy(strategyName?: string) {
  switch (strategyName) {
    case 'hybrid_tw_strategy':
      return '以趨勢與量價條件判斷進出，偏向波段觀察。'
    case 'connors_rsi2_long':
      return '用長期趨勢搭配 RSI(2) 超跌訊號，偏向短線均值回歸。'
    default:
      return '選好策略後，可直接到策略計畫頁執行手動回測。'
  }
}

function toDateInputValue(input: Date) {
  const year = input.getFullYear()
  const month = String(input.getMonth() + 1).padStart(2, '0')
  const day = String(input.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function describeQuoteSource(source?: 'realtime' | 'cache' | 'unavailable') {
  switch (source) {
    case 'cache':
      return '最新成交價暫用快取'
    case 'unavailable':
      return '目前沒有最新成交價'
    default:
      return '最新成交價來自即時快照'
  }
}

export function DashboardPage() {
  const queryClient = useQueryClient()
  const activeUserId = getActiveUserId()
  const [symbolInput, setSymbolInput] = useState('2330')
  const [resolvedStockCode, setResolvedStockCode] = useState<string | null>(null)
  const [activeSymbol, setActiveSymbol] = useState<string | null>(null)
  const [quoteThrottleMessage, setQuoteThrottleMessage] = useState<string | null>(null)
  const [chartStart, setChartStart] = useState(() => {
    const today = new Date()
    const start = new Date(today.getFullYear() - 1, today.getMonth(), today.getDate())
    return toDateInputValue(start)
  })
  const [chartEnd, setChartEnd] = useState(() => toDateInputValue(new Date()))
  const [autoRefreshQuote, setAutoRefreshQuote] = useState(true)
  const normalizedSymbol = (resolvedStockCode ?? symbolInput).trim().toUpperCase()
  const isSymbolReady = normalizedSymbol.length >= 4
  const activeSymbolRef = useRef<string | null>(null)
  const quoteRequestTimesRef = useRef<number[]>([])
  const queuedSymbolRef = useRef<string | null>(null)
  const queuedTimerRef = useRef<number | null>(null)

  useEffect(() => {
    activeSymbolRef.current = activeSymbol
  }, [activeSymbol])

  const updateSymbolInput = (value: string) => {
    const normalizedValue = value.trim().toUpperCase()
    setSymbolInput(value)

    if (activeSymbol && normalizedValue !== activeSymbol) {
      setActiveSymbol(null)
    }

    if (!resolvedStockCode || normalizedValue === resolvedStockCode) {
      return
    }

    setResolvedStockCode(null)
  }

  const resolveSymbol = (code: string) => {
    const normalizedCode = code.trim().toUpperCase()
    if (!normalizedCode) {
      return
    }

    setResolvedStockCode(normalizedCode)
    setSymbolInput(normalizedCode)
    requestQuoteActivation(normalizedCode)
  }

  const requestQuoteActivation = (symbol: string, forceRefetch = false) => {
    const now = Date.now()
    const recentRequests = quoteRequestTimesRef.current.filter((timestamp) => now - timestamp < 5_000)
    quoteRequestTimesRef.current = recentRequests

    if (recentRequests.length < 3) {
      quoteRequestTimesRef.current = [...recentRequests, now]
      setQuoteThrottleMessage(null)
      queuedSymbolRef.current = null
      if (queuedTimerRef.current !== null) {
        window.clearTimeout(queuedTimerRef.current)
        queuedTimerRef.current = null
      }

      if (activeSymbolRef.current !== symbol) {
        setActiveSymbol(symbol)
        return
      }

      if (forceRefetch) {
        void quoteQuery.refetch()
        void historyQuery.refetch()
      }
      return
    }

    const earliestRequest = recentRequests[0]
    const waitMs = Math.max(0, 5_000 - (now - earliestRequest)) + 50
    queuedSymbolRef.current = symbol
    setQuoteThrottleMessage(`即時報價請求過快，將在 ${Math.ceil(waitMs / 1000)} 秒後自動更新。`)

    if (queuedTimerRef.current !== null) {
      window.clearTimeout(queuedTimerRef.current)
    }

    queuedTimerRef.current = window.setTimeout(() => {
      queuedTimerRef.current = null
      const queuedSymbol = queuedSymbolRef.current
      queuedSymbolRef.current = null
      if (!queuedSymbol) {
        return
      }
      requestQuoteActivation(queuedSymbol, true)
    }, waitMs)
  }

  const refreshMarketView = () => {
    if (!isSymbolReady) {
      return
    }

    setResolvedStockCode(normalizedSymbol)
    setSymbolInput(normalizedSymbol)
    requestQuoteActivation(normalizedSymbol, true)
  }

  useEffect(() => {
    return () => {
      if (queuedTimerRef.current !== null) {
        window.clearTimeout(queuedTimerRef.current)
      }
    }
  }, [])

  const userQuery = useQuery({
    queryKey: ['user', activeUserId],
    queryFn: () => api.getUser(activeUserId!),
    enabled: activeUserId !== null,
  })

  const summaryQuery = useQuery({
    queryKey: ['portfolio-summary', activeUserId],
    queryFn: () => api.getPortfolioSummary(activeUserId!),
    enabled: activeUserId !== null,
  })

  const positionsQuery = useQuery({
    queryKey: ['positions', activeUserId],
    queryFn: () => api.getPositions(activeUserId!),
    enabled: activeUserId !== null,
  })

  const watchlistQuery = useQuery({
    queryKey: ['watchlist', activeUserId],
    queryFn: () => api.getWatchlist(activeUserId!),
    enabled: activeUserId !== null,
  })

  const strategyCatalogQuery = useQuery({
    queryKey: ['strategy-catalog'],
    queryFn: api.listStrategies,
  })

  const automationConfigQuery = useQuery({
    queryKey: ['automation-config', activeUserId],
    queryFn: () => api.getAutomationConfig(activeUserId!),
    enabled: activeUserId !== null,
  })

  const updateAutomationConfigMutation = useMutation({
    mutationFn: (payload: {
      strategy_name: string
      position_sizing_mode: 'fixed_shares' | 'cash_percent'
      buy_quantity: number
      cash_allocation_pct: number
      enabled: boolean
    }) =>
      api.updateAutomationConfig(activeUserId!, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['automation-config', activeUserId] })
    },
  })

  const quoteQuery = useQuery({
    queryKey: ['quote', activeSymbol],
    queryFn: () => api.getQuote(activeSymbol!, { forceRefresh: true }),
    enabled: activeSymbol !== null,
    refetchInterval: autoRefreshQuote && activeSymbol ? 15_000 : false,
    staleTime: 0,
    refetchOnWindowFocus: false,
    retry: false,
  })

  const historyQuery = useQuery({
    queryKey: ['history-range', activeSymbol, chartStart, chartEnd],
    queryFn: () => api.getHistoryRange(activeSymbol!, chartStart, chartEnd),
    enabled: activeSymbol !== null,
    staleTime: 60_000,
    refetchOnWindowFocus: false,
    retry: false,
  })

  if (activeUserId === null) {
    return (
      <div className="empty-workspace">
        <h2>還沒有啟用工作區</h2>
        <p>先建立工作區後，才能查看持倉、關注清單與手動回測。</p>
        <Link to="/setup" className="primary-button">
          前往工作區設定
        </Link>
      </div>
    )
  }

  const selectedStrategy = automationConfigQuery.data?.strategy_name ?? 'connors_rsi2_long'
  const positionSizingMode = automationConfigQuery.data?.position_sizing_mode ?? 'fixed_shares'
  const buyQuantity = automationConfigQuery.data?.buy_quantity ?? 1000
  const cashAllocationPct = automationConfigQuery.data?.cash_allocation_pct ?? 10
  const maxOpenPositions = 20
  const selectedStrategyMeta = strategyCatalogQuery.data?.find((item) => item.name === selectedStrategy)
  const createAutomationPayload = (
    overrides: Partial<{
      enabled: boolean
      strategy_name: string
      position_sizing_mode: 'fixed_shares' | 'cash_percent'
      buy_quantity: number
      cash_allocation_pct: number
    }> = {},
  ) => ({
    enabled: automationConfigQuery.data?.enabled ?? true,
    strategy_name: selectedStrategy,
    position_sizing_mode: positionSizingMode,
    buy_quantity: buyQuantity,
    cash_allocation_pct: cashAllocationPct,
    ...overrides,
  })

  return (
    <div className="page-grid">
      <section className="hero-strip">
        <div>
          <p className="hero-kicker">Workspace</p>
          <h2>{userQuery.data ? `${userQuery.data.username} 的工作臺` : '工作臺載入中...'}</h2>
          <p>先看部位與行情，再決定要不要切到策略計畫做手動回測，整個工作流會更順。</p>
        </div>
      </section>

      <div className="stats-grid">
        <StatCard label="可用現金" value={formatCurrency(summaryQuery.data?.available_cash ?? 0)} icon={<Wallet size={18} />} />
        <StatCard label="持倉市值" value={formatCurrency(summaryQuery.data?.market_value ?? 0)} icon={<CandlestickChart size={18} />} />
        <StatCard label="總權益" value={formatCurrency(summaryQuery.data?.total_equity ?? 0)} />
        <StatCard
          label="未實現損益"
          value={formatCurrency(summaryQuery.data?.unrealized_pnl ?? 0)}
          accent={(summaryQuery.data?.unrealized_pnl ?? 0) >= 0 ? 'positive' : 'negative'}
        />
      </div>

      <div className="dashboard-focus-grid">
        <Panel title="行情觀察" subtitle="Market View">
          <div className="stack-form">
            <div className="form-grid form-grid--three">
              <label>
                股票代碼
                <StockAutocompleteInput
                  value={symbolInput}
                  onChange={updateSymbolInput}
                  onResolved={(stock) => resolveSymbol(stock.code)}
                  placeholder="例如 2330 或 台積電"
                />
              </label>
              <label>
                開始日期
                <input type="date" value={chartStart} onChange={(event) => setChartStart(event.target.value)} />
              </label>
              <label>
                結束日期
                <input type="date" value={chartEnd} onChange={(event) => setChartEnd(event.target.value)} />
              </label>
            </div>

            <div className="inline-actions">
              <button
                className="ghost-button"
                type="button"
                onClick={refreshMarketView}
              >
                <RefreshCw size={16} />
                重新整理
              </button>
              <button
                className={autoRefreshQuote ? 'primary-button' : 'ghost-button'}
                type="button"
                onClick={() => setAutoRefreshQuote((current) => !current)}
              >
                {autoRefreshQuote ? '關閉即時更新' : '啟用即時更新'}
              </button>
            </div>

            {watchlistQuery.data && watchlistQuery.data.length > 0 ? (
              <div className="chip-row">
                {watchlistQuery.data.slice(0, 8).map((item) => (
                  <button key={item.id} className="chip-button" type="button" onClick={() => resolveSymbol(item.code)}>
                    {item.code}
                  </button>
                ))}
              </div>
            ) : null}

            {quoteQuery.data ? (
              <div className="quote-card quote-card--inline">
                <div>
                  <span>{quoteQuery.data.name ?? quoteQuery.data.code}</span>
                  <strong>
                    {quoteQuery.data.latest_trade_price
                      ? formatCurrency(quoteQuery.data.latest_trade_price)
                      : '--'}
                  </strong>
                </div>
                <div className="quote-meta">
                  <p>報價時間 {new Date(quoteQuery.data.quote_time).toLocaleTimeString('zh-TW', { hour12: false })}</p>
                  <p>{describeQuoteSource(quoteQuery.data.latest_trade_price_source)}</p>
                  <p>開 {quoteQuery.data.open_price ?? '--'}</p>
                  <p>高 {quoteQuery.data.high_price ?? '--'}</p>
                  <p>低 {quoteQuery.data.low_price ?? '--'}</p>
                  <p>量 {quoteQuery.data.accumulate_trade_volume ?? '--'}</p>
                </div>
              </div>
            ) : null}

            {quoteThrottleMessage ? <p className="muted-text">{quoteThrottleMessage}</p> : null}
            {quoteQuery.data?.warning_message ? <p className="muted-text">{quoteQuery.data.warning_message}</p> : null}
            {historyQuery.isPending ? <p className="muted-text">正在載入歷史圖表資料...</p> : null}
            {historyQuery.data ? <KLineChart data={historyQuery.data.prices} /> : null}
            {historyQuery.isSuccess && !historyQuery.data ? <div className="empty-card">目前沒有可顯示的圖表資料。</div> : null}
            {quoteQuery.error ? <p className="error-text">{quoteQuery.error.message}</p> : null}
            {historyQuery.error ? <p className="error-text">{historyQuery.error.message}</p> : null}
          </div>
        </Panel>

        <Panel title="自動下單策略" subtitle="Auto Execution">
          <div className="strategy-focus-card">
            <label>
              執行策略
              <select
                value={selectedStrategy}
                onChange={(event) => {
                  updateAutomationConfigMutation.mutate(createAutomationPayload({ strategy_name: event.target.value }))
                }}
                disabled={!automationConfigQuery.data || updateAutomationConfigMutation.isPending}
              >
                {(strategyCatalogQuery.data ?? []).map((strategy) => (
                  <option key={strategy.name} value={strategy.name}>
                    {strategy.title}
                  </option>
                ))}
              </select>
            </label>

            <div className="info-stack">
              <div className="info-card">
                <strong>{selectedStrategyMeta?.title ?? '尚未載入策略'}</strong>
                <p>{describeStrategy(selectedStrategyMeta?.name)}</p>
              </div>
              <div className="info-card">
                <strong>下單標的</strong>
                <p>排程會對工作區預設同步池執行策略，也就是自選關注清單加上科技、金融產業股票池。</p>
              </div>
              <div className="info-card">
                <strong>執行方式</strong>
                <p>{selectedStrategyMeta?.execution_timing === 'next_market_open' ? '每天 09:00 自動決策並依即時報價執行' : '每天 09:00 自動決策並依即時報價執行'}</p>
              </div>
              <div className="info-card">
                <strong>使用提醒</strong>
                <p>你在這裡只需要選策略，系統會於每日 14:10 更新資料，並在隔天 09:00 自動決策與套用下單。</p>
              </div>
              <div className="info-card">
                <strong>風控設定</strong>
                <p>自動交易目前最多同時持有 {maxOpenPositions} 檔股票，超過上限的新買進訊號會跳過。</p>
              </div>
            </div>

            <label>
              下單方式
              <select
                value={positionSizingMode}
                onChange={(event) =>
                  updateAutomationConfigMutation.mutate(
                    createAutomationPayload({
                      position_sizing_mode: event.target.value as 'fixed_shares' | 'cash_percent',
                    }),
                  )
                }
                disabled={!automationConfigQuery.data || updateAutomationConfigMutation.isPending}
              >
                <option value="fixed_shares">固定股數</option>
                <option value="cash_percent">可用現金百分比</option>
              </select>
            </label>

            {positionSizingMode === 'fixed_shares' ? (
              <label>
                每次買進股數
                <input
                  type="number"
                  min={1000}
                  step={1000}
                  value={buyQuantity}
                  onWheel={(event) => event.currentTarget.blur()}
                  onChange={(event) =>
                    updateAutomationConfigMutation.mutate(
                      createAutomationPayload({ buy_quantity: Number(event.target.value) }),
                    )
                  }
                  disabled={!automationConfigQuery.data || updateAutomationConfigMutation.isPending}
                />
              </label>
            ) : (
              <label>
                每次投入可用現金比例
                <input
                  type="number"
                  min={1}
                  max={100}
                  step="0.5"
                  value={cashAllocationPct}
                  onWheel={(event) => event.currentTarget.blur()}
                  onChange={(event) =>
                    updateAutomationConfigMutation.mutate(
                      createAutomationPayload({ cash_allocation_pct: Number(event.target.value) }),
                    )
                  }
                  disabled={!automationConfigQuery.data || updateAutomationConfigMutation.isPending}
                />
              </label>
            )}

            {automationConfigQuery.data ? (
              <div className="info-card">
                <strong>{automationConfigQuery.data.enabled ? '自動化已啟用' : '自動化已停用'}</strong>
                <p>
                  目前設定：{automationConfigQuery.data.strategy_name}，
                  {automationConfigQuery.data.position_sizing_mode === 'cash_percent'
                    ? `每次投入可用現金 ${automationConfigQuery.data.cash_allocation_pct}%`
                    : `每次買進 ${automationConfigQuery.data.buy_quantity} 股`}
                  ，最多持倉 {maxOpenPositions} 檔。
                </p>
              </div>
            ) : null}
            <div className="inline-actions">
              <button
                className={automationConfigQuery.data?.enabled ? 'ghost-button' : 'primary-button'}
                type="button"
                onClick={() => updateAutomationConfigMutation.mutate(createAutomationPayload({ enabled: !(automationConfigQuery.data?.enabled ?? true) }))}
                disabled={!automationConfigQuery.data || updateAutomationConfigMutation.isPending}
              >
                {automationConfigQuery.data?.enabled ? '暫停自動化' : '啟用自動化'}
              </button>
              <Link to="/logs" className="ghost-button">
                前往策略計畫
              </Link>
            </div>

            {automationConfigQuery.error ? <p className="error-text">{automationConfigQuery.error.message}</p> : null}
            {updateAutomationConfigMutation.error ? <p className="error-text">{updateAutomationConfigMutation.error.message}</p> : null}
          </div>
        </Panel>
      </div>

      <Panel title="目前持倉" subtitle="Portfolio">
        <PositionTable positions={positionsQuery.data ?? []} />
      </Panel>
    </div>
  )
}
