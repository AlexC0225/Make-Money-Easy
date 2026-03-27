import type { ReactNode } from 'react'

type StatCardProps = {
  label: string
  value: string
  hint?: string
  accent?: 'default' | 'positive' | 'negative'
  icon?: ReactNode
}

export function StatCard({ label, value, hint, accent = 'default', icon }: StatCardProps) {
  return (
    <article className={`stat-card stat-card--${accent}`}>
      <div className="stat-card-head">
        <span>{label}</span>
        {icon}
      </div>
      <strong>{value}</strong>
      {hint ? <p>{hint}</p> : null}
    </article>
  )
}
