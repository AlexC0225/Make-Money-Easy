import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'

import { api } from '../api'
import { Panel } from '../components/Panel'
import { clsx, formatCurrency } from '../lib/format'
import { getActiveUserId } from '../lib/storage'

type SignalTab = 'SELL' | 'HOLD' | 'BUY'

const ALL_INDUSTRIES = '__ALL_INDUSTRIES__'

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

function formatDateTime(value?: string | null) {
  if (!value) {
    return 'n/a'
  }

  return new Date(value).toLocaleString('zh-TW', { hour12: false })
}

function getIndustryLabel(industry?: string | null) {
  const normalized = industry?.trim()
  if (!normalized) {
    return 'Unclassified'
  }
  return normalized
}

export function StrategySignalsPage() {
  const activeUserId = getActiveUserId()
  const [selectedSignalTab, setSelectedSignalTab] = useState<SignalTab>('SELL')
  const [selectedIndustry, setSelectedIndustry] = useState<string>(ALL_INDUSTRIES)
  const signalTabs: SignalTab[] = ['SELL', 'HOLD', 'BUY']

  const signalsQuery = useQuery({
    queryKey: ['signals', 'latest'],
    queryFn: () => api.listSignals({ latestOnly: true }),
    staleTime: 30_000,
  })

  const tradesQuery = useQuery({
    queryKey: ['portfolio-trades', activeUserId],
    queryFn: () => api.getTrades(activeUserId!, 30),
    enabled: activeUserId !== null,
    staleTime: 30_000,
    retry: false,
  })

  const latestSignals = signalsQuery.data ?? []
  const industryOptions = Array.from(new Set(latestSignals.map((signal) => getIndustryLabel(signal.industry)))).sort(
    (left, right) => left.localeCompare(right, 'zh-Hant'),
  )
  const industryScopedSignals = latestSignals.filter((signal) => {
    if (selectedIndustry === ALL_INDUSTRIES) {
      return true
    }
    return getIndustryLabel(signal.industry) === selectedIndustry
  })
  const filteredSignals = industryScopedSignals.filter(
    (signal) => normalizeSignalTab(signal.signal) === selectedSignalTab,
  )

  return (
    <div className="page-grid">
      <section className="hero-strip">
        <div>
          <p className="hero-kicker">Signal Monitor</p>
          <h2>Latest signals across the full universe</h2>
          <p>
            This board shows the newest saved signal for each stock and strategy pair. Use the industry filter to zoom
            in without losing the latest snapshot.
          </p>
        </div>
      </section>

      <div className="metric-grid">
        <article className="metric-card">
          <span>Latest entries</span>
          <strong>{industryScopedSignals.length}</strong>
        </article>
        <article className="metric-card">
          <span>SELL signals</span>
          <strong>{industryScopedSignals.filter((signal) => normalizeSignalTab(signal.signal) === 'SELL').length}</strong>
        </article>
        <article className="metric-card">
          <span>HOLD signals</span>
          <strong>{industryScopedSignals.filter((signal) => normalizeSignalTab(signal.signal) === 'HOLD').length}</strong>
        </article>
        <article className="metric-card">
          <span>BUY signals</span>
          <strong>{industryScopedSignals.filter((signal) => normalizeSignalTab(signal.signal) === 'BUY').length}</strong>
        </article>
      </div>

      <div className="dashboard-columns dashboard-columns--wide">
        <Panel
          title="Latest signal board"
          subtitle="Signals"
          action={
            <div className="signal-toolbar">
              <label className="signal-filter-field">
                <span>Industry</span>
                <select value={selectedIndustry} onChange={(event) => setSelectedIndustry(event.target.value)}>
                  <option value={ALL_INDUSTRIES}>All industries</option>
                  {industryOptions.map((industry) => (
                    <option key={industry} value={industry}>
                      {industry}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          }
        >
          <div className="stack-form">
            <div className="tab-row" role="tablist" aria-label="Signal tabs">
              {signalTabs.map((tab) => {
                const count = industryScopedSignals.filter((signal) => normalizeSignalTab(signal.signal) === tab).length
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
                <article className="signal-item signal-item--stacked" key={signal.id}>
                  <div className="signal-item-copy">
                    <div className="signal-item-head">
                      <strong>
                        {signal.strategy_name} / {signal.stock_code} {signal.stock_name}
                      </strong>
                      <span className="signal-industry-tag">{getIndustryLabel(signal.industry)}</span>
                    </div>
                    <p>{signal.execution?.message ?? signal.signal_reason ?? 'No signal reason was recorded.'}</p>
                    <div className="signal-meta">
                      <span>Updated {formatDateTime(signal.created_at)}</span>
                      <span>Signal date {formatDateTime(signal.signal_time)}</span>
                    </div>
                  </div>
                  <span className={signalBadge(signal.signal)}>{signal.signal}</span>
                </article>
              ))}
              {latestSignals.length === 0 ? <div className="empty-card">No strategy signals are available yet.</div> : null}
              {latestSignals.length > 0 && filteredSignals.length === 0 ? (
                <div className="empty-card">No {selectedSignalTab} signals matched the current industry filter.</div>
              ) : null}
            </div>

            {signalsQuery.error ? <p className="error-text">{signalsQuery.error.message}</p> : null}
          </div>
        </Panel>

        <Panel title="Recent executed trades" subtitle="Live Trades">
          {activeUserId === null ? (
            <div className="empty-card">Select or create a workspace user to inspect live trades.</div>
          ) : tradesQuery.data && tradesQuery.data.length > 0 ? (
            <div className="table-wrap table-wrap--scroll-y">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Executed at</th>
                    <th>Stock</th>
                    <th>Side</th>
                    <th>Price</th>
                    <th>Qty</th>
                    <th>Fee</th>
                    <th>Tax</th>
                  </tr>
                </thead>
                <tbody>
                  {tradesQuery.data.map((trade) => (
                    <tr key={trade.id}>
                      <td>{formatDateTime(trade.executed_at)}</td>
                      <td>
                        {trade.stock_code} {trade.stock_name}
                      </td>
                      <td>
                        <span className={`signal-badge ${trade.side === 'BUY' ? 'signal-badge--buy' : 'signal-badge--sell'}`}>
                          {trade.side}
                        </span>
                      </td>
                      <td>{trade.fill_price.toLocaleString('zh-TW', { maximumFractionDigits: 2 })}</td>
                      <td>{trade.fill_quantity.toLocaleString('zh-TW')}</td>
                      <td>{formatCurrency(trade.fee)}</td>
                      <td>{formatCurrency(trade.tax)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="empty-card">No executed trades are available for the active user.</div>
          )}

          {tradesQuery.error ? <p className="error-text">{tradesQuery.error.message}</p> : null}
        </Panel>
      </div>
    </div>
  )
}
