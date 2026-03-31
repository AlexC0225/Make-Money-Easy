import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '../api'
import { BacktestEquityChart } from '../components/BacktestEquityChart'
import { BacktestPriceChart } from '../components/BacktestPriceChart'
import { Panel } from '../components/Panel'
import { clsx, formatCurrency, formatPercent } from '../lib/format'
import { getActiveUserId, getBacktestStrategy, setBacktestStrategy } from '../lib/storage'
import type { BacktestResult, BacktestRunPayload, BacktestTrade } from '../types/api'

type SignalTab = 'SELL' | 'HOLD' | 'BUY'

function signalBadge(signal: string) {
  return `signal-badge signal-badge--${signal.toLowerCase()}`
}

function normalizeSignalTab(signal: string): SignalTab {
  const normalized = signal.trim().toUpperCase()
  if (normalized === 'SELL' || normalized === 'HOLD' || normalized === 'BUY') {
    return normalized
  }
  return 'HOLD'
}

function describeStrategy(strategyName?: string) {
  switch (strategyName) {
    case 'hybrid_tw_strategy':
      return '用 MA20 / MA60 趨勢與 Best Four Point 條件判斷進出，偏向收盤決策。'
    case 'connors_rsi2_long':
      return '用 SMA200 搭配 RSI(2) 超跌切入，依隔日開盤執行短波段交易。'
    case 'tw_momentum_breakout_long':
      return '趨勢、突破、量能與 RSI 一起確認，再搭配 ATR 與持有天數控管出場。'
    default:
      return '依策略條件在指定區間內重建交易，評估報酬、回撤與交易品質。'
  }
}

function toDateInputValue(input: Date) {
  const year = input.getFullYear()
  const month = String(input.getMonth() + 1).padStart(2, '0')
  const day = String(input.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function createInitialBacktestForm(): BacktestRunPayload {
  const today = new Date()
  const start = new Date(today.getFullYear() - 1, today.getMonth(), today.getDate())

  return {
    code: '',
    strategy_name: getBacktestStrategy() ?? 'hybrid_tw_strategy',
    start_date: toDateInputValue(start),
    end_date: toDateInputValue(today),
    initial_cash: 1_000_000,
    position_sizing_mode: 'fixed_shares',
    lot_size: 1000,
    cash_allocation_pct: 10,
    max_open_positions: 20,
  }
}

function summarizeTarget(result: BacktestResult) {
  if (!result.is_portfolio) {
    return `${result.stock_code} ${result.stock_name}`
  }

  const preview = result.portfolio_codes.slice(0, 4).join(', ')
  const extra = result.portfolio_codes.length > 4 ? ` +${result.portfolio_codes.length - 4}` : ''
  return `投組 / ${preview}${extra}`
}

export function LogsPage() {
  const activeUserId = getActiveUserId()
  const queryClient = useQueryClient()
  const [form, setForm] = useState<BacktestRunPayload>(() => createInitialBacktestForm())
  const [selectedBacktestId, setSelectedBacktestId] = useState<number | null>(null)
  const [selectedSignalTab, setSelectedSignalTab] = useState<SignalTab>('SELL')

  const strategyCatalogQuery = useQuery({
    queryKey: ['strategy-catalog'],
    queryFn: api.listStrategies,
  })

  useEffect(() => {
    if (!strategyCatalogQuery.data?.length) {
      return
    }

    if (!strategyCatalogQuery.data.some((item) => item.name === form.strategy_name)) {
      const fallbackStrategy = strategyCatalogQuery.data[0].name
      setForm((current) => ({ ...current, strategy_name: fallbackStrategy }))
      setBacktestStrategy(fallbackStrategy)
    }
  }, [form.strategy_name, strategyCatalogQuery.data])

  const runBacktestMutation = useMutation({
    mutationFn: (payload: BacktestRunPayload) =>
      api.runBacktest({
        ...payload,
        user_id: activeUserId ?? undefined,
      }),
    onSuccess: async (result) => {
      setBacktestStrategy(result.strategy_name)
      setSelectedBacktestId(result.id)
      await queryClient.invalidateQueries({ queryKey: ['backtests'] })
    },
  })

  const signalsQuery = useQuery({
    queryKey: ['signals', 'all'],
    queryFn: () => api.listSignals({ limit: 20 }),
  })

  const backtestsQuery = useQuery({
    queryKey: ['backtests'],
    queryFn: () => api.listBacktests(12),
  })

  const selectedStrategyMeta = strategyCatalogQuery.data?.find((item) => item.name === form.strategy_name)
  const highlightedResult =
    (runBacktestMutation.data && runBacktestMutation.data.id === selectedBacktestId ? runBacktestMutation.data : null) ??
    backtestsQuery.data?.find((item) => item.id === selectedBacktestId) ??
    runBacktestMutation.data ??
    null
  const highlightedStrategyMeta = strategyCatalogQuery.data?.find((item) => item.name === highlightedResult?.strategy_name)

  const highlightedHistoryQuery = useQuery({
    queryKey: [
      'backtest-history',
      highlightedResult?.id,
      highlightedResult?.stock_code,
      highlightedResult?.start_date,
      highlightedResult?.end_date,
    ],
    queryFn: () => api.getHistoryRange(highlightedResult!.stock_code, highlightedResult!.start_date, highlightedResult!.end_date),
    enabled: highlightedResult !== null && !highlightedResult.is_portfolio,
    staleTime: 60_000,
    retry: false,
  })

  const trades: BacktestTrade[] = highlightedResult ? [...highlightedResult.result.trades].reverse() : []
  const executionTimingLabel =
    highlightedStrategyMeta?.execution_timing === 'next_market_open' ? '隔日開盤執行' : '當日收盤執行'
  const targetSummary = highlightedResult ? summarizeTarget(highlightedResult) : ''
  const signalTabs: SignalTab[] = ['SELL', 'HOLD', 'BUY']
  const filteredSignals = (signalsQuery.data ?? []).filter((signal) => normalizeSignalTab(signal.signal) === selectedSignalTab)

  return (
    <div className="page-grid">
      <section className="hero-strip">
        <div>
          <p className="hero-kicker">Strategy Lab</p>
          <h2>多股票投組回測</h2>
          <p>這裡可以直接用單一股票或多股票清單回測，檢查策略在整段區間內的資金配置與持倉變化。</p>
        </div>
      </section>

      <div className="backtest-layout">
        <Panel title="回測設定" subtitle="Manual Backtest">
          <div className="stack-form">
            <div className="backtest-form-grid">
              <label>
                股票代碼 / 投組清單
                <textarea
                  rows={3}
                  value={form.code}
                  onChange={(event) => setForm((current) => ({ ...current, code: event.target.value }))}
                  placeholder="2330, 2317, 2454"
                />
              </label>

              <label>
                回測策略
                <select
                  value={form.strategy_name}
                  onChange={(event) => {
                    const nextStrategy = event.target.value
                    setForm((current) => ({ ...current, strategy_name: nextStrategy }))
                    setBacktestStrategy(nextStrategy)
                  }}
                >
                  {(strategyCatalogQuery.data ?? []).map((strategy) => (
                    <option key={strategy.name} value={strategy.name}>
                      {strategy.title}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                開始日期
                <input
                  type="date"
                  value={form.start_date}
                  onChange={(event) => setForm((current) => ({ ...current, start_date: event.target.value }))}
                />
              </label>

              <label>
                結束日期
                <input
                  type="date"
                  value={form.end_date}
                  onChange={(event) => setForm((current) => ({ ...current, end_date: event.target.value }))}
                />
              </label>

              <label>
                初始資金
                <input
                  type="number"
                  min={1}
                  value={form.initial_cash}
                  onWheel={(event) => event.currentTarget.blur()}
                  onChange={(event) => setForm((current) => ({ ...current, initial_cash: Number(event.target.value) }))}
                />
              </label>

              <label>
                下單模式
                <select
                  value={form.position_sizing_mode}
                  onChange={(event) =>
                    setForm((current) => ({
                      ...current,
                      position_sizing_mode: event.target.value as 'fixed_shares' | 'cash_percent',
                    }))
                  }
                >
                  <option value="fixed_shares">固定股數</option>
                  <option value="cash_percent">可用現金百分比</option>
                </select>
              </label>

              {form.position_sizing_mode === 'fixed_shares' ? (
                <label>
                  每次買進股數
                  <input
                    type="number"
                    min={1000}
                    step={1000}
                    value={form.lot_size}
                    onWheel={(event) => event.currentTarget.blur()}
                    onChange={(event) => setForm((current) => ({ ...current, lot_size: Number(event.target.value) }))}
                  />
                </label>
              ) : (
                <label>
                  每次投入現金比例
                  <input
                    type="number"
                    min={1}
                    max={100}
                    step="0.5"
                    value={form.cash_allocation_pct}
                    onWheel={(event) => event.currentTarget.blur()}
                    onChange={(event) =>
                      setForm((current) => ({ ...current, cash_allocation_pct: Number(event.target.value) }))
                    }
                  />
                </label>
              )}
            </div>

            <div className="info-card">
              <strong>{selectedStrategyMeta?.title ?? '策略說明'}</strong>
              <p>{describeStrategy(form.strategy_name)}</p>
              <p>{selectedStrategyMeta?.execution_timing === 'next_market_open' ? '訊號在收盤判斷，隔日開盤成交。' : '訊號在當日收盤判斷並成交。'}</p>
              <p>
                目前投組回測最多同時持有 20 檔。
                {form.position_sizing_mode === 'cash_percent'
                  ? ` 每筆買進會以當下可用現金的 ${form.cash_allocation_pct}% 估算股數。`
                  : ` 每筆買進固定使用 ${form.lot_size.toLocaleString('zh-TW')} 股。`}
              </p>
            </div>

            <div className="inline-actions">
              <button
                className="primary-button"
                type="button"
                onClick={() => runBacktestMutation.mutate(form)}
                disabled={runBacktestMutation.isPending || !form.code.trim()}
              >
                {runBacktestMutation.isPending ? '回測中...' : '開始回測'}
              </button>
            </div>

            {runBacktestMutation.error ? <p className="error-text">{runBacktestMutation.error.message}</p> : null}
            {runBacktestMutation.data ? <p className="success-text">回測完成，已更新右側結果卡片。</p> : null}
          </div>
        </Panel>

        <Panel title="回測摘要" subtitle="Backtest Snapshot">
          {highlightedResult ? (
            <div className="stack-form">
              <div className="info-card">
                <strong>
                  {highlightedResult.strategy_name} / {targetSummary}
                </strong>
                <p>
                  區間 {highlightedResult.start_date} ~ {highlightedResult.end_date}
                </p>
                {highlightedResult.is_portfolio ? (
                  <p>股票池: {highlightedResult.portfolio_codes.join(', ')}</p>
                ) : null}
              </div>

              <div className="metric-grid">
                <article className="metric-card">
                  <span>總報酬</span>
                  <strong className={highlightedResult.total_return >= 0 ? 'positive' : 'negative'}>
                    {formatPercent(highlightedResult.total_return)}
                  </strong>
                </article>
                <article className="metric-card">
                  <span>最大回撤</span>
                  <strong>{formatPercent(highlightedResult.max_drawdown)}</strong>
                </article>
                <article className="metric-card">
                  <span>勝率</span>
                  <strong>{formatPercent(highlightedResult.win_rate)}</strong>
                </article>
                <article className="metric-card">
                  <span>Sharpe</span>
                  <strong>{highlightedResult.sharpe_ratio.toFixed(2)}</strong>
                </article>
              </div>

              <div className="setup-summary-grid">
                <article className="setup-summary-card">
                  <span>期末權益</span>
                  <strong>{formatCurrency(highlightedResult.result.final_equity)}</strong>
                  <p>回測結束時的總資產。</p>
                </article>
                <article className="setup-summary-card">
                  <span>已完成交易</span>
                  <strong>{highlightedResult.result.closed_trade_count}</strong>
                  <p>以賣出完成結算的交易筆數。</p>
                </article>
                <article className="setup-summary-card">
                  <span>{highlightedResult.is_portfolio ? '目前持倉檔數' : '目前持股數量'}</span>
                  <strong>
                    {highlightedResult.is_portfolio
                      ? highlightedResult.result.open_position_count ?? 0
                      : highlightedResult.result.open_position_quantity}
                  </strong>
                  <p>{highlightedResult.is_portfolio ? '回測結束時仍持有的股票檔數。' : '回測結束時尚未賣出的股數。'}</p>
                </article>
              </div>
            </div>
          ) : (
            <div className="empty-card">執行一次回測後，這裡會顯示績效摘要與回測設定。</div>
          )}
        </Panel>
      </div>

      <Panel title={highlightedResult?.is_portfolio ? '投組權益曲線' : '回測價格圖'} subtitle="Backtest Chart">
        {highlightedResult ? (
          <div className="stack-form">
            {highlightedResult.is_portfolio ? (
              <BacktestEquityChart equityCurve={highlightedResult.result.equity_curve} trades={highlightedResult.result.trades} />
            ) : (
              <>
                {highlightedHistoryQuery.isPending ? <p className="muted-text">正在載入回測價格資料...</p> : null}
                {highlightedHistoryQuery.isSuccess ? (
                  <BacktestPriceChart
                    prices={highlightedHistoryQuery.data.prices}
                    trades={highlightedResult.result.trades}
                    executionTimingLabel={executionTimingLabel}
                  />
                ) : null}
                {highlightedHistoryQuery.error ? <p className="error-text">{highlightedHistoryQuery.error.message}</p> : null}
              </>
            )}
          </div>
        ) : (
          <div className="empty-card">執行回測後，這裡會顯示價格圖或投組權益曲線。</div>
        )}
      </Panel>

      <Panel title="交易明細" subtitle="Trade Ledger">
        {highlightedResult ? (
          highlightedResult.result.trades.length > 0 ? (
            <div className="stack-form">
              <p className="muted-text">共 {highlightedResult.result.trades.length} 筆交易，以下依時間由新到舊排列。</p>
              <div className="table-wrap table-wrap--scroll-y">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>日期</th>
                      {highlightedResult.is_portfolio ? <th>股票</th> : null}
                      <th>方向</th>
                      <th>價格</th>
                      <th>股數</th>
                      <th>原因</th>
                      <th>損益</th>
                      <th>報酬率</th>
                    </tr>
                  </thead>
                  <tbody>
                    {trades.map((trade, index) => (
                      <tr key={`${trade.date}-${trade.side}-${trade.stock_code ?? 'single'}-${index}`}>
                        <td>{trade.date}</td>
                        {highlightedResult.is_portfolio ? (
                          <td>
                            {trade.stock_code} {trade.stock_name ?? ''}
                          </td>
                        ) : null}
                        <td>{trade.side}</td>
                        <td>{trade.price.toLocaleString('zh-TW', { maximumFractionDigits: 2 })}</td>
                        <td>{trade.quantity}</td>
                        <td>{trade.reason ?? '--'}</td>
                        <td className={trade.pnl !== undefined ? (trade.pnl >= 0 ? 'positive' : 'negative') : undefined}>
                          {trade.pnl !== undefined ? formatCurrency(trade.pnl) : '--'}
                        </td>
                        <td className={trade.return !== undefined ? (trade.return >= 0 ? 'positive' : 'negative') : undefined}>
                          {trade.return !== undefined ? formatPercent(trade.return) : '--'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <div className="empty-card">這段回測區間內沒有產生實際交易。</div>
          )
        ) : (
          <div className="empty-card">先執行一次回測，這裡才會列出交易明細。</div>
        )}
      </Panel>

      <div className="dashboard-columns dashboard-columns--wide">
        <Panel title="回測紀錄" subtitle="Backtest Logs">
          <div className="signal-list signal-list--scrollable">
            {(backtestsQuery.data ?? []).map((item) => (
              <button
                className={clsx('signal-item signal-item-button', item.id === highlightedResult?.id && 'signal-item-button--active')}
                key={item.id}
                type="button"
                onClick={() => setSelectedBacktestId(item.id)}
              >
                <div>
                  <strong>
                    {item.strategy_name} / {summarizeTarget(item)}
                  </strong>
                  <p>
                    {item.start_date} ~ {item.end_date}
                  </p>
                </div>
                <span className={`signal-badge ${item.total_return >= 0 ? 'signal-badge--buy' : 'signal-badge--sell'}`}>
                  {formatPercent(item.total_return)}
                </span>
              </button>
            ))}
            {(backtestsQuery.data ?? []).length === 0 ? <div className="empty-card">目前還沒有回測紀錄。</div> : null}
          </div>
        </Panel>

        <Panel title="最新訊號" subtitle="Signals">
          <div className="stack-form">
            <div className="tab-row" role="tablist" aria-label="訊號類型">
              {signalTabs.map((tab) => {
                const count = (signalsQuery.data ?? []).filter((signal) => normalizeSignalTab(signal.signal) === tab).length
                return (
                  <button
                    key={tab}
                    className={clsx('tab-button', selectedSignalTab === tab && 'tab-button--active')}
                    type="button"
                    role="tab"
                    aria-selected={selectedSignalTab === tab}
                    onClick={() => setSelectedSignalTab(tab)}
                  >
                    {tab} {count}
                  </button>
                )
              })}
            </div>

            <div className="signal-list signal-list--scrollable">
              {filteredSignals.map((signal) => (
                <article className="signal-item" key={signal.id}>
                  <div>
                    <strong>
                      {signal.strategy_name} / {signal.stock_code} {signal.stock_name}
                    </strong>
                    <p>{signal.execution?.message ?? signal.signal_reason ?? '目前沒有額外訊號說明。'}</p>
                  </div>
                  <span className={signalBadge(signal.signal)}>{signal.signal}</span>
                </article>
              ))}
              {(signalsQuery.data ?? []).length === 0 ? <div className="empty-card">目前還沒有策略訊號。</div> : null}
              {(signalsQuery.data ?? []).length > 0 && filteredSignals.length === 0 ? (
                <div className="empty-card">目前沒有 {selectedSignalTab} 訊號。</div>
              ) : null}
            </div>
          </div>
        </Panel>
      </div>
    </div>
  )
}
