import { useDeferredValue, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CandlestickChart, RefreshCw, Wallet } from 'lucide-react'
import { Link } from 'react-router-dom'

import { api } from '../api'
import { KLineChart } from '../components/KLineChart'
import { Panel } from '../components/Panel'
import { PositionTable } from '../components/PositionTable'
import { StatCard } from '../components/StatCard'
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

export function DashboardPage() {
  const queryClient = useQueryClient()
  const activeUserId = getActiveUserId()
  const [symbol, setSymbol] = useState('2330')
  const [chartStart, setChartStart] = useState(() => {
    const start = new Date()
    start.setMonth(start.getMonth() - 3)
    return toDateInputValue(start)
  })
  const [chartEnd, setChartEnd] = useState(() => toDateInputValue(new Date()))
  const [autoRefreshQuote, setAutoRefreshQuote] = useState(true)
  const deferredSymbol = useDeferredValue(symbol.trim())
  const isSymbolReady = deferredSymbol.length >= 4

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
    mutationFn: (payload: { strategy_name: string; buy_quantity: number; enabled: boolean }) =>
      api.updateAutomationConfig(activeUserId!, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['automation-config', activeUserId] })
    },
  })

  const quoteQuery = useQuery({
    queryKey: ['quote', deferredSymbol],
    queryFn: () => api.getQuote(deferredSymbol),
    enabled: isSymbolReady,
    refetchInterval: autoRefreshQuote ? 15_000 : false,
    staleTime: 10_000,
    retry: false,
  })

  const historyQuery = useQuery({
    queryKey: ['history-range', deferredSymbol, chartStart, chartEnd],
    queryFn: () => api.getHistoryRange(deferredSymbol, chartStart, chartEnd),
    enabled: isSymbolReady,
    staleTime: 60_000,
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
  const buyQuantity = automationConfigQuery.data?.buy_quantity ?? 1000
  const selectedStrategyMeta = strategyCatalogQuery.data?.find((item) => item.name === selectedStrategy)

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
                <input value={symbol} onChange={(event) => setSymbol(event.target.value)} />
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
                onClick={() => {
                  void quoteQuery.refetch()
                  void historyQuery.refetch()
                }}
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
                  <button key={item.id} className="chip-button" type="button" onClick={() => setSymbol(item.code)}>
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
                    {quoteQuery.data.reference_price ?? quoteQuery.data.latest_trade_price
                      ? formatCurrency(quoteQuery.data.reference_price ?? quoteQuery.data.latest_trade_price ?? 0)
                      : '--'}
                  </strong>
                </div>
                <div className="quote-meta">
                  <p>報價時間 {new Date(quoteQuery.data.quote_time).toLocaleTimeString('zh-TW', { hour12: false })}</p>
                  <p>開 {quoteQuery.data.open_price ?? '--'}</p>
                  <p>高 {quoteQuery.data.high_price ?? '--'}</p>
                  <p>低 {quoteQuery.data.low_price ?? '--'}</p>
                  <p>量 {quoteQuery.data.accumulate_trade_volume ?? '--'}</p>
                </div>
              </div>
            ) : null}

            {historyQuery.data ? <KLineChart data={historyQuery.data.prices} /> : null}
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
                  updateAutomationConfigMutation.mutate({
                    enabled: automationConfigQuery.data?.enabled ?? true,
                    strategy_name: event.target.value,
                    buy_quantity: buyQuantity,
                  })
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
                <p>排程會對工作區預設同步池執行策略，也就是自選關注清單加上 0050 成分股。</p>
              </div>
              <div className="info-card">
                <strong>執行方式</strong>
                <p>{selectedStrategyMeta?.execution_timing === 'next_market_open' ? '每天 09:00 自動決策並依即時報價執行' : '每天 09:00 自動決策並依即時報價執行'}</p>
              </div>
              <div className="info-card">
                <strong>使用提醒</strong>
                <p>你在這裡只需要選策略，系統會於每日 14:10 更新資料，並在隔天 09:00 自動決策與套用下單。</p>
              </div>
            </div>

            <label>
              每次買進股數
              <input
                type="number"
                min={1}
                step={1}
                value={buyQuantity}
                onWheel={(event) => event.currentTarget.blur()}
                onChange={(event) => {
                  updateAutomationConfigMutation.mutate({
                    enabled: automationConfigQuery.data?.enabled ?? true,
                    strategy_name: selectedStrategy,
                    buy_quantity: Number(event.target.value),
                  })
                }}
                disabled={!automationConfigQuery.data || updateAutomationConfigMutation.isPending}
              />
            </label>

            {automationConfigQuery.data ? (
              <div className="info-card">
                <strong>{automationConfigQuery.data.enabled ? '自動化已啟用' : '自動化已停用'}</strong>
                <p>目前設定：{automationConfigQuery.data.strategy_name}，每次買進 {automationConfigQuery.data.buy_quantity} 股。</p>
              </div>
            ) : null}
            <div className="inline-actions">
              <button
                className={automationConfigQuery.data?.enabled ? 'ghost-button' : 'primary-button'}
                type="button"
                onClick={() =>
                  updateAutomationConfigMutation.mutate({
                    enabled: !(automationConfigQuery.data?.enabled ?? true),
                    strategy_name: selectedStrategy,
                    buy_quantity: buyQuantity,
                  })
                }
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
