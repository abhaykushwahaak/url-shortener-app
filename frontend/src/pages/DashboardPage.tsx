import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import { formatNumber } from '../lib/format'
import type { Timeline, TopURL, URLStats } from '../types'
import { StatCard } from '../components/StatCard'
import { Loading, ErrorMessage } from '../components/States'
import { ClickTimelineChart, TopURLsChart } from '../components/Charts'

export function DashboardPage() {
  const [stats, setStats] = useState<URLStats | null>(null)
  const [timeline, setTimeline] = useState<Timeline | null>(null)
  const [topURLs, setTopURLs] = useState<TopURL[]>([])
  const [days, setDays] = useState(30)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    setLoading(true); setError('')
    Promise.all([api.stats(), api.overviewTimeline(days), api.topURLs(5)])
      .then(([s, t, top]) => { if (cancelled) return; setStats(s); setTimeline(t); setTopURLs(top) })
      .catch(err => { if (!cancelled) setError((err as Error).message) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [days])

  if (loading) return <Loading />
  if (error) return <ErrorMessage message={error} />
  if (!stats) return null

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-slate-900">Dashboard</h1>
        <Link to="/urls" className="btn-primary">+ Shorten URL</Link>
      </div>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatCard label="Total URLs" value={formatNumber(stats.total_urls)} />
        <StatCard label="Active URLs" value={formatNumber(stats.active_urls)} tone="positive" />
        <StatCard label="Expired" value={formatNumber(stats.expired_urls)} tone={stats.expired_urls > 0 ? 'warning' : 'default'} />
        <StatCard label="Total Clicks" value={formatNumber(stats.total_clicks)} />
      </div>
      <div className="card">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-700">Clicks over time</h2>
          <div className="flex gap-1">
            {([7, 14, 30, 90] as const).map(d => (
              <button key={d} type="button" onClick={() => setDays(d)}
                className={`rounded px-2 py-1 text-xs font-medium transition-colors ${days === d ? 'bg-brand-600 text-white' : 'text-slate-500 hover:bg-slate-100'}`}>
                {d}d
              </button>
            ))}
          </div>
        </div>
        {timeline && timeline.points.length > 0
          ? <ClickTimelineChart data={timeline.points} />
          : <p className="py-8 text-center text-sm text-slate-400">No click data yet.</p>}
      </div>
      {topURLs.length > 0 && (
        <div className="card">
          <h2 className="mb-4 text-sm font-semibold text-slate-700">Top URLs</h2>
          <TopURLsChart data={topURLs} />
        </div>
      )}
    </div>
  )
}
