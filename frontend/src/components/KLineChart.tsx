import {
  Area,
  Bar,
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

import type { HistoricalPrice } from '../types/api'
import { formatNumber } from '../lib/format'

type KLineChartProps = {
  data: HistoricalPrice[]
}

type MarketChartRow = {
  date: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

type MarketTooltipProps = {
  active?: boolean
  payload?: Array<{ payload: MarketChartRow }>
}

function formatPrice(value: number) {
  return new Intl.NumberFormat('zh-TW', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  }).format(value)
}

function formatAxisDate(value: string) {
  return value.replace(/-/g, '/').slice(2)
}

function MarketTooltip({ active, payload }: MarketTooltipProps) {
  if (!active || !payload?.length) {
    return null
  }

  const row = payload[0].payload

  return (
    <div className="chart-tooltip">
      <strong>{row.date}</strong>
      <p>收盤 {formatPrice(row.close)}</p>
      <p>開盤 {formatPrice(row.open)}</p>
      <p>最高 {formatPrice(row.high)}</p>
      <p>最低 {formatPrice(row.low)}</p>
      <p>成交量 {formatNumber(row.volume)}</p>
    </div>
  )
}

export function KLineChart({ data }: KLineChartProps) {
  const rows = data
    .map((item) => {
      const open = item.open_price ?? item.close_price
      const high = item.high_price ?? item.close_price
      const low = item.low_price ?? item.close_price
      const close = item.close_price ?? item.open_price

      if (open === null || high === null || low === null || close === null) {
        return null
      }

      return {
        date: item.trade_date,
        open,
        high,
        low,
        close,
        volume: item.volume ?? 0,
      }
    })
    .filter((item): item is MarketChartRow => item !== null)
    .sort((left, right) => left.date.localeCompare(right.date))

  if (rows.length === 0) {
    return <div className="empty-card">目前沒有可繪製的行情資料。</div>
  }

  const latest = rows[rows.length - 1]
  const highest = Math.max(...rows.map((item) => item.high))
  const lowest = Math.min(...rows.map((item) => item.low))
  const priceMin = Math.floor(lowest * 0.98)
  const priceMax = Math.ceil(highest * 1.02)

  return (
    <div className="kline-card">
      <div className="chart-header">
        <div>
          <strong>互動行情圖</strong>
          <p>可滑鼠查看明細，並用底部區間刷選快速縮放時間範圍。</p>
        </div>
      </div>

      <div className="chart-summary-grid">
        <article className="chart-summary-card">
          <span>最新收盤</span>
          <strong>{formatPrice(latest.close)}</strong>
        </article>
        <article className="chart-summary-card">
          <span>區間最高</span>
          <strong>{formatPrice(highest)}</strong>
        </article>
        <article className="chart-summary-card">
          <span>區間最低</span>
          <strong>{formatPrice(lowest)}</strong>
        </article>
        <article className="chart-summary-card">
          <span>最新量能</span>
          <strong>{formatNumber(latest.volume)}</strong>
        </article>
      </div>

      <div className="chart-surface">
        <ResponsiveContainer width="100%" height={380}>
          <ComposedChart data={rows} margin={{ top: 12, right: 16, bottom: 24, left: 0 }}>
            <defs>
              <linearGradient id="marketCloseFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#0c7c59" stopOpacity={0.22} />
                <stop offset="100%" stopColor="#0c7c59" stopOpacity={0.02} />
              </linearGradient>
            </defs>

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
              yAxisId="price"
              domain={[priceMin, priceMax]}
              tickFormatter={(value: number) => formatPrice(value)}
              tick={{ fill: '#5b756f', fontSize: 12 }}
              tickLine={false}
              axisLine={false}
              width={72}
            />
            <YAxis yAxisId="volume" hide domain={[0, 'dataMax']} />
            <Tooltip content={<MarketTooltip />} cursor={{ stroke: 'rgba(17, 49, 45, 0.18)', strokeWidth: 1 }} />
            <Legend wrapperStyle={{ fontSize: '12px' }} />
            <Bar
              yAxisId="volume"
              dataKey="volume"
              name="成交量"
              barSize={10}
              fill="rgba(17, 49, 45, 0.16)"
              radius={[6, 6, 0, 0]}
            />
            <Area
              yAxisId="price"
              type="monotone"
              dataKey="close"
              name="收盤價"
              legendType="none"
              stroke="none"
              fill="url(#marketCloseFill)"
            />
            <Line
              yAxisId="price"
              type="monotone"
              dataKey="close"
              name="收盤價"
              stroke="#11312d"
              strokeWidth={3}
              dot={false}
              activeDot={{ r: 5, fill: '#11312d', stroke: '#fffaf1', strokeWidth: 2 }}
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
    </div>
  )
}
