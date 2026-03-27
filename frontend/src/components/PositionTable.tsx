import type { Position } from '../types/api'
import { clsx, formatCurrency, formatNumber } from '../lib/format'

type PositionTableProps = {
  positions: Position[]
}

export function PositionTable({ positions }: PositionTableProps) {
  if (positions.length === 0) {
    return <div className="empty-card">目前沒有持倉，先到初始化頁輸入部位，或在工作台直接買進。</div>
  }

  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>代碼</th>
            <th>股票</th>
            <th>數量</th>
            <th>均價</th>
            <th>市價</th>
            <th>未實現損益</th>
          </tr>
        </thead>
        <tbody>
          {positions.map((position) => (
            <tr key={position.stock_code}>
              <td>{position.stock_code}</td>
              <td>{position.stock_name}</td>
              <td>{formatNumber(position.quantity)}</td>
              <td>{formatCurrency(position.avg_cost)}</td>
              <td>{formatCurrency(position.market_price)}</td>
              <td className={clsx(position.unrealized_pnl >= 0 ? 'positive' : 'negative')}>
                {formatCurrency(position.unrealized_pnl)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
