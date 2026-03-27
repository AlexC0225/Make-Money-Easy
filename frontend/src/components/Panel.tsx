import type { PropsWithChildren, ReactNode } from 'react'

type PanelProps = PropsWithChildren<{
  title: string
  subtitle?: string
  action?: ReactNode
}>

export function Panel({ title, subtitle, action, children }: PanelProps) {
  return (
    <section className="panel">
      <header className="panel-header">
        <div>
          <p className="panel-kicker">{subtitle}</p>
          <h2>{title}</h2>
        </div>
        {action ? <div>{action}</div> : null}
      </header>
      <div className="panel-body">{children}</div>
    </section>
  )
}
