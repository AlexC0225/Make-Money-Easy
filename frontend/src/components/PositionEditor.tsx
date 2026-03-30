import { useMutation } from '@tanstack/react-query'
import { Plus, Trash2 } from 'lucide-react'

import { api } from '../api'
import { StockAutocompleteInput } from './StockAutocompleteInput'
import type { ManualPositionInput } from '../types/api'

type PositionEditorProps = {
  positions: ManualPositionInput[]
  onChange: (positions: ManualPositionInput[]) => void
}

export function PositionEditor({ positions, onChange }: PositionEditorProps) {
  const updatePosition = (index: number, key: keyof ManualPositionInput, value: string) => {
    const next = [...positions]
    const current = next[index]
    const normalizedValue = key === 'code' ? value.trim() : value
    next[index] = {
      ...current,
      [key]: key === 'code' ? normalizedValue : Number(normalizedValue),
      ...(key === 'code' && current.code !== normalizedValue ? { market_price: 0 } : {}),
    }
    onChange(next)
  }

  const quoteMutation = useMutation({
    mutationFn: async ({ code }: { code: string }) => {
      try {
        const quote = await api.getQuote(code)
        return quote.latest_trade_price ?? null
      } catch {
        return null
      }
    },
  })

  const resolveStock = (index: number, code: string) => {
    const current = positions[index]
    const normalizedCode = code.trim()

    if (!normalizedCode) {
      return
    }

    if (current?.code === normalizedCode && (current.market_price ?? 0) > 0) {
      return
    }

    void quoteMutation.mutateAsync({ code: normalizedCode }).then((resolvedPrice) => {
      if (resolvedPrice === undefined || resolvedPrice === null) {
        return
      }
      const next = [...positions]
      next[index] = {
        ...next[index],
        code: normalizedCode,
        market_price: resolvedPrice,
      }
      onChange(next)
    })
  }

  const addRow = () => {
    onChange([
      ...positions,
      {
        code: '',
        quantity: 1000,
        avg_cost: 0,
        market_price: 0,
      },
    ])
  }

  const removeRow = (index: number) => {
    onChange(positions.filter((_, currentIndex) => currentIndex !== index))
  }

  return (
    <div className="position-editor">
      <div className="position-editor-head">
        <p>輸入現有持倉後，系統會用目前成本與市價重建資產狀態，作為後續追蹤與策略記錄的基礎。</p>
        <button className="ghost-button" type="button" onClick={addRow}>
          <Plus size={16} />
          新增持倉
        </button>
      </div>

      {positions.length === 0 ? <div className="empty-card">目前沒有持倉資料，按下「新增持倉」即可開始建立資產組合。</div> : null}

      <div className="position-grid">
        {positions.map((position, index) => (
          <div className="position-row" key={index}>
            <label>
              股票代碼
              <StockAutocompleteInput
                value={position.code}
                onChange={(value) => updatePosition(index, 'code', value)}
                onResolved={(stock) => resolveStock(index, stock.code)}
                placeholder="例如 2330"
              />
            </label>
            <label>
              股數
              <input
                type="number"
                min={1}
                step={1}
                inputMode="numeric"
                value={position.quantity}
                onWheel={(event) => event.currentTarget.blur()}
                onChange={(event) => updatePosition(index, 'quantity', event.target.value)}
              />
            </label>
            <label>
              平均成本
              <input
                type="number"
                min={0}
                step="0.01"
                inputMode="decimal"
                value={position.avg_cost}
                onWheel={(event) => event.currentTarget.blur()}
                onChange={(event) => updatePosition(index, 'avg_cost', event.target.value)}
              />
            </label>
            <label>
              目前市價
              <input
                type="number"
                min={0}
                step="0.01"
                inputMode="decimal"
                value={position.market_price ?? 0}
                onWheel={(event) => event.currentTarget.blur()}
                onChange={(event) => updatePosition(index, 'market_price', event.target.value)}
              />
            </label>
            <button className="icon-button" type="button" onClick={() => removeRow(index)} aria-label="刪除持倉">
              <Trash2 size={16} />
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}
