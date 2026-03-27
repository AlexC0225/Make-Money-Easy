import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '../api'
import { Panel } from '../components/Panel'
import { getActiveUserId } from '../lib/storage'

export function MarketPage() {
  const queryClient = useQueryClient()
  const activeUserId = getActiveUserId()
  const [watchCode, setWatchCode] = useState('')
  const [watchNote, setWatchNote] = useState('')

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
    mutationFn: () => api.addWatchlist(activeUserId!, watchCode, watchNote || undefined),
    onSuccess: async () => {
      setWatchCode('')
      setWatchNote('')
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

  return (
    <div className="page-grid">
      <section className="hero-strip">
        <div>
          <p className="hero-kicker">Watchlist</p>
          <h2>自選關注與 0050 成分股</h2>
          <p>這一頁只保留你自己的關注清單，以及同步流程會一起追蹤的 0050 成分股。</p>
        </div>
      </section>

      <div className="dashboard-columns dashboard-columns--wide">
        <Panel title="自選關注清單" subtitle="Watchlist">
          {activeUserId === null ? (
            <div className="empty-card">請先登入工作區，才能維護自選關注清單。</div>
          ) : (
            <div className="stack-form">
              <div className="form-grid">
                <label>
                  股票代碼
                  <input value={watchCode} onChange={(event) => setWatchCode(event.target.value)} placeholder="2330" />
                </label>
                <label>
                  備註
                  <input value={watchNote} onChange={(event) => setWatchNote(event.target.value)} placeholder="例如：區間整理、等突破" />
                </label>
              </div>

              <div className="inline-actions">
                <button className="primary-button" type="button" onClick={() => addWatchMutation.mutate()} disabled={!watchCode.trim()}>
                  新增關注
                </button>
              </div>

              {addWatchMutation.error ? <p className="error-text">{addWatchMutation.error.message}</p> : null}

              {(watchlistQuery.data ?? []).length === 0 ? <div className="empty-card">目前還沒有自選股票。</div> : null}

              <div className="watchlist-grid">
                {(watchlistQuery.data ?? []).map((item) => (
                  <article className="watch-card" key={item.id}>
                    <div>
                      <strong>{item.code}</strong>
                      <p>{item.name}</p>
                      <span>{item.note || '尚未填寫備註'}</span>
                    </div>
                    <button className="ghost-button" type="button" onClick={() => removeWatchMutation.mutate(item.code)}>
                      移除
                    </button>
                  </article>
                ))}
              </div>

              {removeWatchMutation.error ? <p className="error-text">{removeWatchMutation.error.message}</p> : null}
            </div>
          )}
        </Panel>

        <Panel title="0050 成分股" subtitle="Benchmark Universe">
          <div className="stack-form">
            <div className="setup-summary-grid">
              <article className="setup-summary-card">
                <span>成分股數量</span>
                <strong>{syncTargetsQuery.data?.benchmark_codes.length ?? 0}</strong>
                <p>這份清單會併入預設同步股票池。</p>
              </article>
              <article className="setup-summary-card">
                <span>公告日</span>
                <strong>{syncTargetsQuery.data?.announce_date ?? '--'}</strong>
                <p>用來辨識目前抓到的成分股快照版本。</p>
              </article>
              <article className="setup-summary-card">
                <span>交易日</span>
                <strong>{syncTargetsQuery.data?.trade_date ?? '--'}</strong>
                <p>對應這次成分股資料的交易日期。</p>
              </article>
            </div>

            {syncTargetsQuery.data?.benchmark_codes?.length ? (
              <div className="chip-row">
                {syncTargetsQuery.data.benchmark_codes.map((code) => (
                  <span className="setup-chip" key={code}>
                    {code}
                  </span>
                ))}
              </div>
            ) : (
              <div className="empty-card">目前還沒有 0050 成分股資料，請先到工作區設定同步股票池。</div>
            )}

            {syncTargetsQuery.data?.source_url ? (
              <a className="ghost-button" href={syncTargetsQuery.data.source_url} target="_blank" rel="noreferrer">
                查看來源清單
              </a>
            ) : null}
            {syncTargetsQuery.error ? <p className="error-text">{syncTargetsQuery.error.message}</p> : null}
          </div>
        </Panel>
      </div>
    </div>
  )
}
