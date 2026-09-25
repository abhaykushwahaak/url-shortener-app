import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api } from '../lib/api'
import { formatDateTime, formatNumber, truncateURL } from '../lib/format'
import type { AnalyticsSummary, ClickRecord, Paginated, Timeline } from '../types'
import { StatCard } from '../components/StatCard'
import { Loading, ErrorMessage } from '../components/States'
import { ClickTimelineChart, BreakdownBarChart, DonutChart } from '../components/Charts'

export function AnalyticsPage() {
  const { id } = useParams<{ id: string }>()
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null)
  const [timeline, setTimeline] = useState<Timeline | null>(null)
  const [clicks, setClicks] = useState<Paginated<ClickRecord> | null>(null)
  const [days, setDays] = useState(30)
  const [clicksPage, setClicksPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [clicksLoading, setClicksLoading] = useState(false)

  useEffect(() => {
    if (!id) return
    let cancelled = false
    setLoading(true); setError('')
    Promise.all([api.analytics(id), api.timeline(id, days)])
      .then(([s, t]) => { if (cancelled) return; setSummary(s); setTimeline(t) })
      .catch(err => { if (!cancelled) setError((err as Error).message) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [id, days])

  useEffect(() => {
    if (!id) return
    let cancelled = false
    setClicksLoading(true)
    api.clicks(id, clicksPage, 20)
      .then(data => { if (!cancelled) setClicks(data) })
      .catch(() => {})
      .finally(() => { if (!cancelled) setClicksLoading(false) })
    return () => { cancelled = true }
  }, [id, clicksPage])

  if (loading) return <Loading />
  if (error) return <ErrorMessage message={error} />
  if (!summary) return null

  const clicksTotalPages = clicks ? Math.ceil(clicks.total / 20) : 1

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2 text-sm text-slate-500">
        <Link to="/urls" className="hover:text-brand-600">URLs</Link>
        <span>/</span>
        <span className="font-mono text-brand-600">/{summary.short_code}</span>
        <span>/</span>
        <span>Analytics</span>
      </div>
      <div>
        <h1 className="text-xl font-semibold text-slate-900">/{summary.short_code}</h1>
        <p className="mt-0.5 text-sm text-slate-500">{truncateURL(summary.original_url, 72)}</p>
      </div>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatCard label="Total clicks" value={formatNumber(summary.total_clicks)} />
        <StatCard label="Unique visitors" value={formatNumber(summary.unique_visitors)} />
        <StatCard label="Today" value={formatNumber(summary.clicks_today)} />
        <StatCard label="This week" value={formatNumber(summary.clicks_this_week)} />
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
          : <p className="py-8 text-center text-sm text-slate-400">No clicks in this period.</p>}
      </div>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {([['Devices', summary.devices, '#2856d8'], ['Browsers', summary.browsers, '#059669'], ['Referrers', summary.referrers, '#d97706']] as [string, typeof summary.devices, string][]).map(([label, data, color]) => (
          <div key={label} className="card">
            <h2 className="mb-4 text-sm font-semibold text-slate-700">{label}</h2>
            {data.length > 0 ? (<><DonutChart data={data} /><BreakdownBarChart data={data} color={color} maxBars={6} /></>) : <p className="py-6 text-center text-sm text-slate-400">No data.</p>}
          </div>
        ))}
      </div>
      <div className="card overflow-hidden p-0">
        <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
          <h2 className="text-sm font-semibold text-slate-700">Click log</h2>
          {clicks && <span className="text-xs text-slate-400">{formatNumber(clicks.total)} total</span>}
        </div>
        {clicksLoading ? <Loading label="Loading clicks..." /> : clicks && clicks.items.length > 0 ? (
          <>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 bg-slate-50 text-xs font-semibold uppercase tracking-wide text-slate-400">
                  <th className="px-4 py-2 text-left">When</th>
                  <th className="hidden px-4 py-2 text-left sm:table-cell">Device</th>
                  <th className="hidden px-4 py-2 text-left sm:table-cell">Browser</th>
                  <th className="hidden px-4 py-2 text-left md:table-cell">Referrer</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {clicks.items.map(click => (
                  <tr key={click.id} className="hover:bg-slate-50">
                    <td className="px-4 py-2 text-slate-600">{formatDateTime(click.clicked_at)}</td>
                    <td className="hidden px-4 py-2 text-slate-500 sm:table-cell">{click.device ?? '-'}</td>
                    <td className="hidden px-4 py-2 text-slate-500 sm:table-cell">{click.browser ?? '-'}</td>
                    <td className="hidden px-4 py-2 text-slate-500 md:table-cell">{click.referrer ?? 'Direct'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {clicksTotalPages > 1 && (
              <div className="flex items-center justify-end gap-1 border-t border-slate-100 px-4 py-3">
                <button type="button" className="btn-secondary" disabled={clicksPage <= 1} onClick={() => setClicksPage(p => p - 1)}>Prev</button>
                <span className="px-3 text-sm text-slate-500">{clicksPage} / {clicksTotalPages}</span>
                <button type="button" className="btn-secondary" disabled={clicksPage >= clicksTotalPages} onClick={() => setClicksPage(p => p + 1)}>Next</button>
              </div>
            )}
          </>
        ) : <p className="py-8 text-center text-sm text-slate-400">No clicks recorded yet.</p>}
      </div>
    </div>
  )
}
