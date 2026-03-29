import {
  Brush,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import type { BacktestResult, BacktestTrade } from '../types/api'
import { formatCurrency, formatNumber } from '../lib/format'

type BacktestEquityChartProps = {
  equityCurve: BacktestResult['result']['equity_curve']
  trades: BacktestTrade[]
}

type EquityChartRow = BacktestResult['result']['equity_curve'][number] & {
  tradeSummary?: {
    buyCount: number
    sellCount: number
  }
}

type EquityTooltipProps = {
  active?: boolean
  payload?: Array<{ payload: EquityChartRow }>
}

function formatAxisDate(value: string) {
  return value.replace(/-/g, '/').slice(2)
}

function EquityTooltip({ active, payload }: EquityTooltipProps) {
  if (!active || !payload?.length) {
    return null
  }

  const row = payload[0].payload
  return (
    <div className="chart-tooltip">
      <strong>{row.date}</strong>
      <p>總資產 {formatCurrency(row.equity)}</p>
      <p>現金 {formatCurrency(row.cash ?? 0)}</p>
      <p>持股市值 {formatCurrency(row.holdings_value ?? 0)}</p>
      <p>持倉檔數 {formatNumber(row.open_positions ?? 0)}</p>
      {row.tradeSummary ? (
        <p>
          當日交易 {formatNumber(row.tradeSummary.buyCount)} 買 / {formatNumber(row.tradeSummary.sellCount)} 賣
        </p>
      ) : null}
    </div>
  )
}

export function BacktestEquityChart({ equityCurve, trades }: BacktestEquityChartProps) {
  const tradesByDate = new Map<string, { buyCount: number; sellCount: number }>()
  for (const trade of trades) {
    const current = tradesByDate.get(trade.date) ?? { buyCount: 0, sellCount: 0 }
    if (trade.side === 'BUY') {
      current.buyCount += 1
    } else {
      current.sellCount += 1
    }
    tradesByDate.set(trade.date, current)
  }

  const points = equityCurve
    .map((item) => ({
      ...item,
      tradeSummary: tradesByDate.get(item.date),
    }))
    .sort((left, right) => left.date.localeCompare(right.date))

  if (points.length === 0) {
    return <div className="empty-card">目前沒有可顯示的投組權益曲線。</div>
  }

  const equities = points.map((item) => item.equity)
  const minEquity = Math.min(...equities)
  const maxEquity = Math.max(...equities)
  const first = points[0]
  const latest = points[points.length - 1]

  return (
    <div className="backtest-chart-card">
      <div className="backtest-chart-head">
        <div>
          <strong>投組權益曲線</strong>
          <p>這裡會看見多股票投組在整段回測期間的總資產、現金部位與持股市值變化。</p>
        </div>
      </div>

      <div className="chart-summary-grid">
        <article className="chart-summary-card">
          <span>最低權益</span>
          <strong>{formatCurrency(minEquity)}</strong>
        </article>
        <article className="chart-summary-card">
          <span>最高權益</span>
          <strong>{formatCurrency(maxEquity)}</strong>
        </article>
        <article className="chart-summary-card">
          <span>最新權益</span>
          <strong>{formatCurrency(latest.equity)}</strong>
        </article>
        <article className="chart-summary-card">
          <span>交易次數</span>
          <strong>{formatNumber(trades.length)}</strong>
        </article>
      </div>

      <div className="chart-surface">
        <ResponsiveContainer width="100%" height={420}>
          <ComposedChart data={points} margin={{ top: 12, right: 16, bottom: 24, left: 0 }}>
            <CartesianGrid stroke="rgba(16, 46, 42, 0.08)" strokeDasharray="4 4" vertical={false} />
            <XAxis
              dataKey="date"
              minTickGap={36}
              tickFormatter={formatAxisDate}
              tick={{ fill: '#5b756f', fontSize: 12 }}
              tickLine={false}
              axisLine={false}
            />
            <YAxis
              tickFormatter={(value: number) => formatCurrency(value)}
              tick={{ fill: '#5b756f', fontSize: 12 }}
              tickLine={false}
              axisLine={false}
              width={92}
            />
            <Tooltip content={<EquityTooltip />} cursor={{ stroke: 'rgba(17, 49, 45, 0.18)', strokeWidth: 1 }} />
            <Legend wrapperStyle={{ fontSize: '12px' }} />
            <Line
              type="monotone"
              dataKey="equity"
              name="總資產"
              stroke="#11312d"
              strokeWidth={3}
              dot={false}
              activeDot={{ r: 5, fill: '#11312d', stroke: '#fffaf1', strokeWidth: 2 }}
            />
            <Line
              type="monotone"
              dataKey="cash"
              name="現金"
              stroke="#0c7c59"
              strokeWidth={2}
              dot={false}
            />
            <Line
              type="monotone"
              dataKey="holdings_value"
              name="持股市值"
              stroke="#b07a24"
              strokeWidth={2}
              dot={false}
            />
            <Brush
              dataKey="date"
              height={28}
              stroke="#5f7b74"
              travellerWidth={10}
              fill="rgba(17, 49, 45, 0.05)"
              tickFormatter={formatAxisDate}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <p className="muted-text">
        {first.date} ~ {latest.date}，權益區間 {formatCurrency(minEquity)} 到 {formatCurrency(maxEquity)}，共
        {formatNumber(points.length)} 個交易日。
      </p>
    </div>
  )
}
