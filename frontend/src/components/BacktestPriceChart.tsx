import {
  Brush,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import type { BacktestTrade, HistoricalPrice } from '../types/api'
import { formatCurrency, formatNumber } from '../lib/format'

type BacktestPriceChartProps = {
  prices: HistoricalPrice[]
  trades: BacktestTrade[]
  executionTimingLabel?: string
}

type BacktestChartRow = {
  date: string
  price: number
  buyTrade?: TradePoint
  sellTrade?: TradePoint
}

type TradePoint = {
  date: string
  price: number
  side: 'BUY' | 'SELL'
  quantity: number
  reason?: string
  pnl?: number
  return?: number
  executionTimingLabel?: string
}

type BacktestTooltipProps = {
  active?: boolean
  payload?: Array<{ payload: BacktestChartRow; dataKey?: string }>
}

type ScatterShapeProps = {
  cx?: number
  cy?: number
  fill?: string
}

type TradeDotProps = {
  cx?: number
  cy?: number
  payload?: BacktestChartRow
}

function formatTradePrice(value: number) {
  return new Intl.NumberFormat('zh-TW', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  }).format(value)
}

function formatAxisDate(value: string) {
  return value.replace(/-/g, '/').slice(2)
}

function BacktestTooltip({ active, payload }: BacktestTooltipProps) {
  if (!active || !payload?.length) {
    return null
  }

  const row = payload[0].payload
  const tradePoint = row.sellTrade ?? row.buyTrade

  if (tradePoint) {
    return (
      <div className="chart-tooltip">
        <strong>
          {tradePoint.side === 'BUY' ? '買進' : '賣出'} {tradePoint.date}
        </strong>
        <p>
          {tradePoint.executionTimingLabel ?? '成交'} @{formatTradePrice(tradePoint.price)}
        </p>
        <p>股數 {formatNumber(tradePoint.quantity)}</p>
        <p>原因 {tradePoint.reason ?? '--'}</p>
        <p>損益 {tradePoint.pnl !== undefined ? formatCurrency(tradePoint.pnl) : '--'}</p>
        <p>報酬率 {tradePoint.return !== undefined ? `${(tradePoint.return * 100).toFixed(2)}%` : '--'}</p>
      </div>
    )
  }

  return (
    <div className="chart-tooltip">
      <strong>{row.date}</strong>
      <p>收盤 {formatTradePrice(row.price)}</p>
    </div>
  )
}

function BuyTradeShape({ cx = 0, cy = 0, fill = '#0c7c59' }: ScatterShapeProps) {
  return <circle cx={cx} cy={cy} r={6} fill={fill} stroke="#fffaf1" strokeWidth={2} />
}

function SellTradeShape({ cx = 0, cy = 0, fill = '#b5453a' }: ScatterShapeProps) {
  return (
    <path
      d={`M ${cx} ${cy - 7} L ${cx + 7} ${cy} L ${cx} ${cy + 7} L ${cx - 7} ${cy} Z`}
      fill={fill}
      stroke="#fffaf1"
      strokeWidth={2}
    />
  )
}

function TradeDot({ cx = 0, cy = 0, payload }: TradeDotProps) {
  if (!payload) {
    return null
  }
  if (payload.sellTrade) {
    return <SellTradeShape cx={cx} cy={cy} />
  }
  if (payload.buyTrade) {
    return <BuyTradeShape cx={cx} cy={cy} />
  }
  return null
}

export function BacktestPriceChart({ prices, trades, executionTimingLabel }: BacktestPriceChartProps) {
  const buyTrades: TradePoint[] = trades
    .filter((trade) => trade.side === 'BUY')
    .map((trade) => ({
      date: trade.date,
      price: trade.price,
      side: trade.side,
      quantity: trade.quantity,
      reason: trade.reason,
      pnl: trade.pnl,
      return: trade.return,
      executionTimingLabel,
    }))

  const sellTrades: TradePoint[] = trades
    .filter((trade) => trade.side === 'SELL')
    .map((trade) => ({
      date: trade.date,
      price: trade.price,
      side: trade.side,
      quantity: trade.quantity,
      reason: trade.reason,
      pnl: trade.pnl,
      return: trade.return,
      executionTimingLabel,
    }))

  const buyTradeByDate = new Map(buyTrades.map((trade) => [trade.date, trade]))
  const sellTradeByDate = new Map(sellTrades.map((trade) => [trade.date, trade]))

  const points: BacktestChartRow[] = []
  for (const item of prices) {
    const price = item.close_price ?? item.open_price ?? item.high_price ?? item.low_price
    if (price === null) {
      continue
    }

    points.push({
      date: item.trade_date,
      price,
      buyTrade: buyTradeByDate.get(item.trade_date),
      sellTrade: sellTradeByDate.get(item.trade_date),
    })
  }
  points.sort((left, right) => left.date.localeCompare(right.date))

  if (points.length === 0) {
    return <div className="empty-card">目前沒有可繪製的回測價格資料。</div>
  }

  const pricesOnly = points.map((item) => item.price)
  const tradeValues = trades.length > 0 ? trades.map((trade) => trade.price) : pricesOnly
  const minPrice = Math.min(...pricesOnly, ...tradeValues)
  const maxPrice = Math.max(...pricesOnly, ...tradeValues)
  const first = points[0]!
  const latest = points[points.length - 1]!
  const priceMin = Math.floor(minPrice * 0.98)
  const priceMax = Math.ceil(maxPrice * 1.02)

  return (
    <div className="backtest-chart-card">
      <div className="backtest-chart-head">
        <div>
          <strong>互動回測圖</strong>
          <p>滑鼠移到價格線或交易點可查看完整資訊，底部刷選器可快速聚焦特定區間。</p>
        </div>
      </div>

      <div className="chart-summary-grid">
        <article className="chart-summary-card">
          <span>區間最低</span>
          <strong>{formatTradePrice(minPrice)}</strong>
        </article>
        <article className="chart-summary-card">
          <span>區間最高</span>
          <strong>{formatTradePrice(maxPrice)}</strong>
        </article>
        <article className="chart-summary-card">
          <span>最新收盤</span>
          <strong>{formatTradePrice(latest.price)}</strong>
        </article>
        <article className="chart-summary-card">
          <span>交易筆數</span>
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
              domain={[priceMin, priceMax]}
              tickFormatter={(value: number) => formatTradePrice(value)}
              tick={{ fill: '#5b756f', fontSize: 12 }}
              tickLine={false}
              axisLine={false}
              width={72}
            />
            <Tooltip content={<BacktestTooltip />} cursor={{ stroke: 'rgba(17, 49, 45, 0.18)', strokeWidth: 1 }} />
            <Legend wrapperStyle={{ fontSize: '12px' }} />
            <ReferenceLine y={latest.price} stroke="rgba(17, 49, 45, 0.18)" strokeDasharray="4 4" />
            <Line
              type="monotone"
              dataKey="price"
              name="收盤價"
              stroke="#11312d"
              strokeWidth={3}
              dot={<TradeDot />}
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

      <p className="muted-text">
        {first.date} ~ {latest.date} 區間價格範圍 {formatTradePrice(minPrice)} 至 {formatTradePrice(maxPrice)}，共 {points.length} 筆價格與 {trades.length} 筆交易。
      </p>
    </div>
  )
}
