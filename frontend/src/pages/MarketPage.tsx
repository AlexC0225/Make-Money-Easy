import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '../api'
import { Panel } from '../components/Panel'
import { getActiveUserId } from '../lib/storage'
import type { WatchlistItem } from '../types/api'

type UniverseItem = {
  code: string
  name: string
  industry?: string | null
}

type UniverseGroup = {
  industry: string
  items: UniverseItem[]
}

function groupByIndustry(items: UniverseItem[]): UniverseGroup[] {
  const groups = new Map<string, UniverseItem[]>()

  for (const item of items) {
    const industry = item.industry?.trim() || '未分類'
    const group = groups.get(industry)
    if (group) {
      group.push(item)
    } else {
      groups.set(industry, [item])
    }
  }

  return [...groups.entries()]
    .sort((left, right) => left[0].localeCompare(right[0], 'zh-Hant'))
    .map(([industry, groupItems]) => ({
      industry,
      items: [...groupItems].sort((left, right) => left.code.localeCompare(right.code)),
    }))
}

function countUniqueIndustries(items: UniverseItem[]) {
  return new Set(items.map((item) => item.industry?.trim() || '未分類')).size
}

function UniverseSection({
  title,
  subtitle,
  items,
  tone,
  emptyMessage,
  onRemove,
  isRemoving,
}: {
  title: string
  subtitle: string
  items: UniverseItem[]
  tone: 'watchlist' | 'default'
  emptyMessage: string
  onRemove?: (code: string) => void
  isRemoving?: boolean
}) {
  const groups = groupByIndustry(items)

  return (
    <section className="universe-column">
      <div className="universe-section-head">
        <div>
          <h3>{title}</h3>
          <p>{subtitle}</p>
        </div>
        <span className={`universe-badge universe-badge--${tone}`}>{items.length} 檔</span>
      </div>

      {groups.length === 0 ? (
        <div className="empty-card universe-empty">{emptyMessage}</div>
      ) : (
        <div className="universe-group-list">
          {groups.map((group) => (
            <section className="universe-group" key={`${tone}-${group.industry}`}>
              <div className="universe-group-head">
                <div>
                  <strong>{group.industry}</strong>
                  <span>{group.items.length} 檔</span>
                </div>
              </div>

              <div className="universe-stock-grid">
                {group.items.map((item) => (
                  <article className={`universe-stock-card universe-stock-card--${tone}`} key={`${tone}-${item.code}`}>
                    <div className="universe-stock-copy">
                      <strong className="universe-stock-code">{item.code}</strong>
                      <p className="universe-stock-name">{item.name}</p>
                    </div>
                    {onRemove ? (
                      <button
                        className="ghost-button"
                        type="button"
                        onClick={() => onRemove(item.code)}
                        disabled={isRemoving}
                      >
                        移除
                      </button>
                    ) : null}
                  </article>
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </section>
  )
}

export function MarketPage() {
  const queryClient = useQueryClient()
  const activeUserId = getActiveUserId()
  const [watchCode, setWatchCode] = useState('')

  const watchlistQuery = useQuery({
    queryKey: ['watchlist', activeUserId],
    queryFn: () => api.getWatchlist(activeUserId!),
    enabled: activeUserId !== null,
  })

  const syncTargetsQuery = useQuery({
    queryKey: ['sync-targets', activeUserId],
    queryFn: () => api.getSyncTargets(activeUserId ?? undefined),
    staleTime: 60_000,
    retry: false,
  })

  const addWatchMutation = useMutation({
    mutationFn: () => api.addWatchlist(activeUserId!, watchCode),
    onSuccess: async () => {
      setWatchCode('')
      await queryClient.invalidateQueries({ queryKey: ['watchlist', activeUserId] })
      await queryClient.invalidateQueries({ queryKey: ['sync-targets', activeUserId] })
    },
  })

  const removeWatchMutation = useMutation({
    mutationFn: (code: string) => api.removeWatchlist(activeUserId!, code),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['watchlist', activeUserId] })
      await queryClient.invalidateQueries({ queryKey: ['sync-targets', activeUserId] })
    },
  })

  const watchlistItems = (watchlistQuery.data ?? []) as WatchlistItem[]
  const defaultPoolItems = syncTargetsQuery.data?.default_pool_items ?? []
  const combinedCount = new Set([...watchlistItems.map((item) => item.code), ...defaultPoolItems.map((item) => item.code)]).size
  const trackedIndustryCount = countUniqueIndustries([...watchlistItems, ...defaultPoolItems])

  return (
    <div className="page-grid">
      <section className="hero-strip">
        <div>
          <p className="hero-kicker">Watchlist</p>
          <h2>自選與預設同步池</h2>
          <p>市場頁會把自選股票和預設同步池用同一套產業分組方式呈現，讓你更快看懂目前真正會同步的股票範圍。</p>
        </div>
      </section>

      <Panel title="同步股票池工作區" subtitle="Universe Workspace">
        {activeUserId === null ? (
          <div className="empty-card">請先登入工作區，才能管理自選關注與同步股票池。</div>
        ) : (
          <div className="stack-form">
            <div className="setup-summary-grid">
              <article className="setup-summary-card">
                <span>自選股票</span>
                <strong>{watchlistItems.length}</strong>
                <p>你手動加入、優先關注的股票。</p>
              </article>
              <article className="setup-summary-card">
                <span>預設池股票</span>
                <strong>{defaultPoolItems.length}</strong>
                <p>系統依科技與金融產業自動整理。</p>
              </article>
              <article className="setup-summary-card">
                <span>整體同步範圍</span>
                <strong>{combinedCount}</strong>
                <p>合併後重複股票只會算一次。</p>
              </article>
              <article className="setup-summary-card">
                <span>涵蓋產業</span>
                <strong>{trackedIndustryCount}</strong>
                <p>自選與預設池都會依產業自動分組。</p>
              </article>
            </div>

            <div className="universe-toolbar">
              <label>
                新增自選股票
                <input value={watchCode} onChange={(event) => setWatchCode(event.target.value)} placeholder="輸入股票代碼，例如 2330" />
              </label>
              <button className="primary-button" type="button" onClick={() => addWatchMutation.mutate()} disabled={!watchCode.trim()}>
                加入自選
              </button>
            </div>

            <p className="muted-text">新增後會自動帶入股票名稱與產業，不需要另外填寫備註。</p>

            <div className="universe-layout">
              <UniverseSection
                title="你的自選"
                subtitle="保留你自己的觀察標的，並按產業整理。"
                items={watchlistItems}
                tone="watchlist"
                emptyMessage="目前還沒有自選股票，輸入代碼後就會出現在這裡。"
                onRemove={(code) => removeWatchMutation.mutate(code)}
                isRemoving={removeWatchMutation.isPending}
              />
              <UniverseSection
                title="預設同步池"
                subtitle="來自科技業與金融業的預設清單，也用同樣方式分組。"
                items={defaultPoolItems}
                tone="default"
                emptyMessage="目前還沒有預設同步池資料，請先更新股票主檔。"
              />
            </div>

            {addWatchMutation.error ? <p className="error-text">{addWatchMutation.error.message}</p> : null}
            {removeWatchMutation.error ? <p className="error-text">{removeWatchMutation.error.message}</p> : null}
            {syncTargetsQuery.error ? <p className="error-text">{syncTargetsQuery.error.message}</p> : null}
          </div>
        )}
      </Panel>
    </div>
  )
}
