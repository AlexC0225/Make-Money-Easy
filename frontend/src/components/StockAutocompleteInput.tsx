import { useDeferredValue, useEffect, useEffectEvent, useId, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'

import { api } from '../api'
import type { StockLookupItem } from '../types/api'

type StockAutocompleteInputProps = {
  value: string
  onChange: (value: string) => void
  onResolved?: (stock: StockLookupItem) => void
  placeholder?: string
  minSearchLength?: number
}

export function StockAutocompleteInput({
  value,
  onChange,
  onResolved,
  placeholder,
  minSearchLength = 2,
}: StockAutocompleteInputProps) {
  const listId = useId()
  const deferredValue = useDeferredValue(value.trim())
  const lastResolvedMatchRef = useRef<string | null>(null)
  const emitResolved = useEffectEvent((stock: StockLookupItem) => {
    onResolved?.(stock)
  })

  const searchQuery = useQuery({
    queryKey: ['stock-search', deferredValue],
    queryFn: () => api.searchStocks(deferredValue, 10),
    enabled: deferredValue.length >= minSearchLength,
    staleTime: 60_000,
    retry: false,
  })

  useEffect(() => {
    if (!onResolved || !searchQuery.data || deferredValue.length < minSearchLength) {
      return
    }

    const exactMatch = searchQuery.data.find(
      (item) => item.code.toLowerCase() === deferredValue.toLowerCase() || item.name === deferredValue,
    )
    if (exactMatch) {
      const matchKey = `${deferredValue.toLowerCase()}::${exactMatch.code}`
      if (lastResolvedMatchRef.current === matchKey) {
        return
      }
      lastResolvedMatchRef.current = matchKey
      emitResolved(exactMatch)
      return
    }

    lastResolvedMatchRef.current = null
  }, [deferredValue, emitResolved, minSearchLength, onResolved, searchQuery.data])

  return (
    <>
      <input
        list={listId}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        autoComplete="off"
      />
      <datalist id={listId}>
        {(searchQuery.data ?? []).map((item) => (
          <option
            key={item.code}
            value={item.code}
          >{`${item.code} ${item.name}${item.latest_price ? ` · ${item.latest_price}` : ''}`}</option>
        ))}
      </datalist>
    </>
  )
}
