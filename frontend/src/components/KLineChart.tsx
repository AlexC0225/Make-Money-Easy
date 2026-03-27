import type { HistoricalPrice } from '../types/api'
import { formatNumber } from '../lib/format'

type KLineChartProps = {
  data: HistoricalPrice[]
}

const chartHeight = 320
const chartWidth = 920
const padding = { top: 20, right: 18, bottom: 36, left: 64 }

export function KLineChart({ data }: KLineChartProps) {
  if (data.length === 0) {
    return <div className="empty-card">這段期間還沒有歷史資料，請先到設定頁同步資料。</div>
  }

  const highs = data.map((item) => item.high_price ?? 0)
  const lows = data.map((item) => item.low_price ?? 0)
  const minPrice = Math.min(...lows)
  const maxPrice = Math.max(...highs)
  const range = maxPrice - minPrice || 1
  const innerWidth = chartWidth - padding.left - padding.right
  const innerHeight = chartHeight - padding.top - padding.bottom
  const candleGap = innerWidth / Math.max(data.length, 1)
  const candleWidth = Math.max(4, Math.min(12, candleGap * 0.55))

  const toY = (value: number) => padding.top + ((maxPrice - value) / range) * innerHeight
  const ticks = Array.from({ length: 5 }, (_, index) => maxPrice - (range / 4) * index)
  const visibleDates = data.filter((_, index) => index % Math.max(1, Math.floor(data.length / 6)) === 0)

  return (
    <div className="kline-card">
      <svg viewBox={`0 0 ${chartWidth} ${chartHeight}`} className="kline-svg" role="img" aria-label="K line chart">
        <rect x="0" y="0" width={chartWidth} height={chartHeight} rx="24" fill="transparent" />

        {ticks.map((tick) => {
          const y = toY(tick)
          return (
            <g key={tick}>
              <line
                x1={padding.left}
                y1={y}
                x2={chartWidth - padding.right}
                y2={y}
                stroke="rgba(16, 46, 42, 0.08)"
                strokeDasharray="4 4"
              />
              <text x={padding.left - 12} y={y + 4} textAnchor="end" className="kline-axis-text">
                {formatNumber(Number(tick.toFixed(0)))}
              </text>
            </g>
          )
        })}

        {data.map((item, index) => {
          const open = item.open_price ?? 0
          const close = item.close_price ?? 0
          const high = item.high_price ?? 0
          const low = item.low_price ?? 0
          const x = padding.left + index * candleGap + candleGap / 2
          const openY = toY(open)
          const closeY = toY(close)
          const highY = toY(high)
          const lowY = toY(low)
          const isUp = close >= open
          const bodyY = Math.min(openY, closeY)
          const bodyHeight = Math.max(2, Math.abs(closeY - openY))
          const fill = isUp ? '#0c7c59' : '#b5453a'

          return (
            <g key={item.trade_date}>
              <title>{`${item.trade_date} O:${open} H:${high} L:${low} C:${close}`}</title>
              <line x1={x} y1={highY} x2={x} y2={lowY} stroke={fill} strokeWidth={1.5} />
              <rect
                x={x - candleWidth / 2}
                y={bodyY}
                width={candleWidth}
                height={bodyHeight}
                rx="2"
                fill={fill}
                opacity="0.9"
              />
            </g>
          )
        })}

        {visibleDates.map((item, index) => {
          const sourceIndex = data.findIndex((entry) => entry.trade_date === item.trade_date)
          const x = padding.left + sourceIndex * candleGap + candleGap / 2
          return (
            <text
              key={`${item.trade_date}-${index}`}
              x={x}
              y={chartHeight - 10}
              textAnchor="middle"
              className="kline-axis-text"
            >
              {item.trade_date.slice(5)}
            </text>
          )
        })}
      </svg>
    </div>
  )
}
