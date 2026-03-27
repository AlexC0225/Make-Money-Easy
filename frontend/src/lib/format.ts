export function formatCurrency(value: number) {
  return new Intl.NumberFormat('zh-TW', {
    style: 'currency',
    currency: 'TWD',
    maximumFractionDigits: 0,
  }).format(value)
}

export function formatNumber(value: number) {
  return new Intl.NumberFormat('zh-TW').format(value)
}

export function formatPercent(value: number) {
  return `${(value * 100).toFixed(2)}%`
}

export function clsx(...values: Array<string | false | null | undefined>) {
  return values.filter(Boolean).join(' ')
}
