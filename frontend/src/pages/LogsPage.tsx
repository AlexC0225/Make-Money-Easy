import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '../api'
import { Panel } from '../components/Panel'
import { StockAutocompleteInput } from '../components/StockAutocompleteInput'
import { formatCurrency, formatPercent } from '../lib/format'
import { getBacktestStrategy, setBacktestStrategy } from '../lib/storage'
import type { BacktestRunPayload } from '../types/api'

function signalBadge(signal: string) {
  return `signal-badge signal-badge--${signal.toLowerCase()}`
}

function describeStrategy(strategyName?: string) {
  switch (strategyName) {
    case 'hybrid_tw_strategy':
      return '偏向趨勢與量價過濾，適合觀察波段進出節奏。'
    case 'connors_rsi2_long':
      return '偏向短線均值回歸，依賴長期趨勢與超跌訊號。'
    default:
      return '請先選擇一個策略，再執行手動回測。'
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
    code: '2330',
    strategy_name: getBacktestStrategy() ?? 'hybrid_tw_strategy',
    start_date: toDateInputValue(start),
    end_date: toDateInputValue(today),
    initial_cash: 1_000_000,
    lot_size: 1000,
  }
}

export function LogsPage() {
  const queryClient = useQueryClient()
  const [form, setForm] = useState<BacktestRunPayload>(() => createInitialBacktestForm())

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
    mutationFn: api.runBacktest,
    onSuccess: async (result) => {
      setBacktestStrategy(result.strategy_name)
      await queryClient.invalidateQueries({ queryKey: ['backtests'] })
    },
  })

  const signalsQuery = useQuery({
    queryKey: ['signals', 'all'],
    queryFn: () => api.listSignals(20),
  })

  const backtestsQuery = useQuery({
    queryKey: ['backtests'],
    queryFn: () => api.listBacktests(12),
  })

  const selectedStrategyMeta = strategyCatalogQuery.data?.find((item) => item.name === form.strategy_name)
  const highlightedResult = runBacktestMutation.data ?? backtestsQuery.data?.[0] ?? null

  return (
    <div className="page-grid">
      <section className="hero-strip">
        <div>
          <p className="hero-kicker">Strategy Plan</p>
          <h2>手動回測與策略紀錄</h2>
          <p>策略選擇、回測參數與結果集中在這一頁處理，避免和日常監控混在一起。</p>
        </div>
      </section>

      <div className="backtest-layout">
        <Panel title="手動回測" subtitle="Manual Backtest">
          <div className="stack-form">
            <div className="backtest-form-grid">
              <label>
                股票代碼
                <StockAutocompleteInput
                  value={form.code}
                  onChange={(value) => setForm((current) => ({ ...current, code: value }))}
                  placeholder="2330"
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
                每次股數
                <input
                  type="number"
                  min={1}
                  step={1}
                  value={form.lot_size}
                  onWheel={(event) => event.currentTarget.blur()}
                  onChange={(event) => setForm((current) => ({ ...current, lot_size: Number(event.target.value) }))}
                />
              </label>
            </div>

            <div className="info-card">
              <strong>{selectedStrategyMeta?.title ?? '策略載入中'}</strong>
              <p>{describeStrategy(form.strategy_name)}</p>
              <p>
                {selectedStrategyMeta?.execution_timing === 'next_market_open' ? '成交假設：下一個交易日開盤價' : '成交假設：當日收盤價'}
              </p>
            </div>

            <div className="inline-actions">
              <button
                className="primary-button"
                type="button"
                onClick={() => runBacktestMutation.mutate(form)}
                disabled={runBacktestMutation.isPending || !form.code.trim()}
              >
                {runBacktestMutation.isPending ? '回測中...' : '執行手動回測'}
              </button>
            </div>

            {runBacktestMutation.error ? <p className="error-text">{runBacktestMutation.error.message}</p> : null}
            {runBacktestMutation.data ? <p className="success-text">已建立新的手動回測結果。</p> : null}
          </div>
        </Panel>

        <Panel title="回測結果摘要" subtitle="Backtest Snapshot">
          {highlightedResult ? (
            <div className="stack-form">
              <div className="info-card">
                <strong>
                  {highlightedResult.strategy_name} / {highlightedResult.stock_code} {highlightedResult.stock_name}
                </strong>
                <p>
                  {highlightedResult.start_date} ~ {highlightedResult.end_date}
                </p>
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
                  <span>夏普值</span>
                  <strong>{highlightedResult.sharpe_ratio.toFixed(2)}</strong>
                </article>
              </div>

              <div className="setup-summary-grid">
                <article className="setup-summary-card">
                  <span>最終權益</span>
                  <strong>{formatCurrency(highlightedResult.result.final_equity)}</strong>
                  <p>根據回測期間的權益曲線計算。</p>
                </article>
                <article className="setup-summary-card">
                  <span>已平倉筆數</span>
                  <strong>{highlightedResult.result.closed_trade_count}</strong>
                  <p>只計算已完成進出場的交易。</p>
                </article>
                <article className="setup-summary-card">
                  <span>未平倉股數</span>
                  <strong>{highlightedResult.result.open_position_quantity}</strong>
                  <p>若回測結束時仍有部位，會留在這裡。</p>
                </article>
              </div>

              {highlightedResult.result.trades.length > 0 ? (
                <div className="table-wrap">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>日期</th>
                        <th>方向</th>
                        <th>價格</th>
                        <th>股數</th>
                        <th>原因</th>
                      </tr>
                    </thead>
                    <tbody>
                      {highlightedResult.result.trades.slice(-5).reverse().map((trade, index) => (
                        <tr key={`${trade.date}-${trade.side}-${index}`}>
                          <td>{String(trade.date)}</td>
                          <td>{String(trade.side)}</td>
                          <td>{trade.price}</td>
                          <td>{trade.quantity}</td>
                          <td>{String(trade.reason ?? '--')}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="empty-card">這次回測沒有產生交易，可能是條件尚未觸發。</div>
              )}
            </div>
          ) : (
            <div className="empty-card">先執行一次手動回測，這裡就會顯示結果摘要。</div>
          )}
        </Panel>
      </div>

      <div className="dashboard-columns dashboard-columns--wide">
        <Panel title="最近回測紀錄" subtitle="Backtest Logs">
          <div className="signal-list">
            {(backtestsQuery.data ?? []).map((item) => (
              <article className="signal-item" key={item.id}>
                <div>
                  <strong>
                    {item.strategy_name} / {item.stock_code} {item.stock_name}
                  </strong>
                  <p>
                    {item.start_date} ~ {item.end_date}
                  </p>
                </div>
                <span className={`signal-badge ${item.total_return >= 0 ? 'signal-badge--buy' : 'signal-badge--sell'}`}>
                  {formatPercent(item.total_return)}
                </span>
              </article>
            ))}
            {(backtestsQuery.data ?? []).length === 0 ? <div className="empty-card">目前還沒有回測紀錄。</div> : null}
          </div>
        </Panel>

        <Panel title="最近策略訊號" subtitle="Signals">
          <div className="signal-list">
            {(signalsQuery.data ?? []).map((signal) => (
              <article className="signal-item" key={signal.id}>
                <div>
                  <strong>
                    {signal.strategy_name} / {signal.stock_code} {signal.stock_name}
                  </strong>
                  <p>{signal.execution?.message ?? signal.signal_reason ?? '目前沒有額外說明。'}</p>
                </div>
                <span className={signalBadge(signal.signal)}>{signal.signal}</span>
              </article>
            ))}
            {(signalsQuery.data ?? []).length === 0 ? <div className="empty-card">目前還沒有策略訊號紀錄。</div> : null}
          </div>
        </Panel>
      </div>
    </div>
  )
}
