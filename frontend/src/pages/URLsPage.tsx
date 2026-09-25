import { useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError } from '../lib/api'
import { formatDate, formatNumber, isoToLocalInput, localInputToISO, truncateURL } from '../lib/format'
import type { CreateURLPayload, Paginated, ShortURL, UpdateURLPayload } from '../types'
import { Loading, ErrorMessage, EmptyState } from '../components/States'
import { StatusBadge } from '../components/StatusBadge'

function URLDrawer({ initial, onClose, onSaved }: { initial?: ShortURL | null; onClose: () => void; onSaved: (url: ShortURL) => void }) {
  const isEdit = Boolean(initial)
  const [originalUrl, setOriginalUrl] = useState(initial?.original_url ?? '')
  const [alias, setAlias] = useState(initial?.custom_alias ?? '')
  const [expiresAt, setExpiresAt] = useState(isoToLocalInput(initial?.expires_at ?? null))
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault(); setError(''); setBusy(true)
    try {
      let saved: ShortURL
      if (isEdit && initial) {
        saved = await api.updateURL(initial.id, { original_url: originalUrl || undefined, custom_alias: alias || null, expires_at: localInputToISO(expiresAt) } as UpdateURLPayload)
      } else {
        saved = await api.createURL({ original_url: originalUrl, custom_alias: alias || null, expires_at: localInputToISO(expiresAt) } as CreateURLPayload)
      }
      onSaved(saved)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong.')
    } finally { setBusy(false) }
  }

  return (
    <div className="fixed inset-0 z-40 flex">
      <div className="absolute inset-0 bg-black/30" onClick={onClose} aria-hidden="true" />
      <div className="relative ml-auto flex h-full w-full max-w-md flex-col bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
          <h2 className="font-semibold text-slate-900">{isEdit ? 'Edit URL' : 'Shorten a URL'}</h2>
          <button type="button" onClick={onClose} className="rounded-lg p-1 text-slate-400 hover:bg-slate-100" aria-label="Close">X</button>
        </div>
        <form onSubmit={handleSubmit} className="flex flex-1 flex-col gap-4 overflow-auto p-5">
          {error && <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>}
          <div>
            <label className="label" htmlFor="originalUrl">Destination URL <span className="text-red-500">*</span></label>
            <input id="originalUrl" type="url" className="input" value={originalUrl} onChange={e => setOriginalUrl(e.target.value)} placeholder="https://example.com" required autoFocus />
          </div>
          <div>
            <label className="label" htmlFor="alias">Custom alias <span className="text-slate-400 font-normal">(optional)</span></label>
            <input id="alias" type="text" className="input" value={alias} onChange={e => setAlias(e.target.value)} placeholder="my-link" pattern="[a-zA-Z0-9_-]+" />
          </div>
          <div>
            <label className="label" htmlFor="expiresAt">Expires at <span className="text-slate-400 font-normal">(optional)</span></label>
            <input id="expiresAt" type="datetime-local" className="input" value={expiresAt} onChange={e => setExpiresAt(e.target.value)} />
          </div>
          <div className="mt-auto flex gap-2 pt-2">
            <button type="submit" className="btn-primary flex-1" disabled={busy}>{busy ? 'Saving...' : isEdit ? 'Save changes' : 'Create short URL'}</button>
            <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
          </div>
        </form>
      </div>
    </div>
  )
}

export function URLsPage() {
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [filterActive, setFilterActive] = useState<'all' | 'active' | 'inactive'>('all')
  const [result, setResult] = useState<Paginated<ShortURL> | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [editing, setEditing] = useState<ShortURL | null>(null)
  const [copied, setCopied] = useState<string | null>(null)
  const copyTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const fetchURLs = useCallback(async () => {
    setLoading(true); setError('')
    try {
      const data = await api.listURLs({
        page, limit: 20,
        search: search || undefined,
        is_active: filterActive === 'all' ? undefined : filterActive === 'active',
        sort: 'created_at',
      })
      setResult(data)
    } catch (err) { setError((err as Error).message) }
    finally { setLoading(false) }
  }, [page, search, filterActive])

  useEffect(() => { void fetchURLs() }, [fetchURLs])

  const handleSaved = (url: ShortURL) => {
    setDrawerOpen(false); setEditing(null)
    setResult(prev => {
      if (!prev) return prev
      const exists = prev.items.some(u => u.id === url.id)
      return {
        ...prev,
        items: exists ? prev.items.map(u => u.id === url.id ? url : u) : [url, ...prev.items],
        total: exists ? prev.total : prev.total + 1,
      }
    })
  }

  const handleToggleActive = async (url: ShortURL) => {
    try {
      const updated = await api.updateURL(url.id, { is_active: !url.is_active })
      setResult(prev => prev ? { ...prev, items: prev.items.map(u => u.id === updated.id ? updated : u) } : prev)
    } catch (err) { alert((err as Error).message) }
  }

  const handleDelete = async (url: ShortURL) => {
    if (!confirm(`Delete /${url.short_code}? This cannot be undone.`)) return
    try {
      await api.deleteURL(url.id)
      setResult(prev => prev
        ? { ...prev, items: prev.items.filter(u => u.id !== url.id), total: prev.total - 1 }
        : prev)
    } catch (err) { alert((err as Error).message) }
  }

  const handleCopy = (url: ShortURL) => {
    void navigator.clipboard.writeText(url.short_url)
    setCopied(url.id)
    if (copyTimerRef.current) clearTimeout(copyTimerRef.current)
    copyTimerRef.current = setTimeout(() => setCopied(null), 2000)
  }

  const totalPages = result ? Math.ceil(result.total / 20) : 1

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold text-slate-900">My URLs</h1>
        <button type="button" className="btn-primary" onClick={() => { setEditing(null); setDrawerOpen(true) }}>
          + Shorten URL
        </button>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-2">
        <input type="search" className="input max-w-xs" placeholder="Search URLs..."
          value={search} onChange={e => { setSearch(e.target.value); setPage(1) }} />
        {(['all', 'active', 'inactive'] as const).map(f => (
          <button key={f} type="button" onClick={() => { setFilterActive(f); setPage(1) }}
            className={`rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
              filterActive === f
                ? 'bg-brand-600 text-white'
                : 'border border-slate-300 bg-white text-slate-600 hover:bg-slate-50'
            }`}>
            {f.charAt(0).toUpperCase() + f.slice(1)}
          </button>
        ))}
      </div>

      {/* Table */}
      {loading ? <Loading /> : error ? <ErrorMessage message={error} /> : !result || result.items.length === 0 ? (
        <EmptyState title="No URLs yet" hint="Click '+ Shorten URL' to create your first short link." />
      ) : (
        <>
          <div className="card overflow-hidden p-0">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 bg-slate-50 text-xs font-semibold uppercase tracking-wide text-slate-400">
                  <th className="px-4 py-3 text-left">Short URL</th>
                  <th className="hidden px-4 py-3 text-left sm:table-cell">Destination</th>
                  <th className="px-4 py-3 text-right">Clicks</th>
                  <th className="hidden px-4 py-3 text-left md:table-cell">Created</th>
                  <th className="px-4 py-3 text-left">Status</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {result.items.map(url => (
                  <tr key={url.id} className="hover:bg-slate-50">

                    {/* Short URL — clickable + copyable */}
                    <td className="px-4 py-3">
                      <div className="flex flex-col gap-0.5">
                        {/* Clickable short link that opens the redirect */}
                        <a
                          href={url.short_url}
                          target="_blank"
                          rel="noreferrer"
                          className="font-mono text-sm font-medium text-brand-600 hover:underline"
                          title={`Open ${url.short_url}`}
                        >
                          {url.short_url}
                        </a>
                        {/* Copy button */}
                        <button
                          type="button"
                          onClick={() => handleCopy(url)}
                          className="flex w-fit items-center gap-1 rounded px-1.5 py-0.5 text-xs text-slate-400 hover:bg-slate-100 hover:text-brand-600 transition-colors"
                          title="Copy to clipboard"
                        >
                          {copied === url.id
                            ? <span className="text-emerald-600 font-medium">Copied!</span>
                            : <span>Copy link</span>
                          }
                        </button>
                      </div>
                    </td>

                    {/* Destination */}
                    <td className="hidden px-4 py-3 text-slate-500 sm:table-cell">
                      <a href={url.original_url} target="_blank" rel="noreferrer" className="hover:underline">
                        {truncateURL(url.original_url)}
                      </a>
                    </td>

                    <td className="px-4 py-3 text-right font-medium">{formatNumber(url.total_clicks)}</td>
                    <td className="hidden px-4 py-3 text-slate-500 md:table-cell">{formatDate(url.created_at)}</td>
                    <td className="px-4 py-3"><StatusBadge url={url} /></td>

                    {/* Actions */}
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-2 text-xs">
                        <Link to={`/urls/${url.id}/analytics`} className="text-slate-400 hover:text-brand-600 font-medium">
                          Analytics
                        </Link>
                        <span className="text-slate-200">|</span>
                        <button type="button" onClick={() => { setEditing(url); setDrawerOpen(true) }} className="text-slate-400 hover:text-brand-600 font-medium">
                          Edit
                        </button>
                        <span className="text-slate-200">|</span>
                        <button type="button" onClick={() => handleToggleActive(url)} className={`font-medium ${url.is_active ? 'text-slate-400 hover:text-amber-600' : 'text-slate-400 hover:text-emerald-600'}`}>
                          {url.is_active ? 'Disable' : 'Enable'}
                        </button>
                        <span className="text-slate-200">|</span>
                        <button type="button" onClick={() => handleDelete(url)} className="text-slate-400 hover:text-red-600 font-medium">
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {totalPages > 1 && (
            <div className="flex items-center justify-between text-sm text-slate-500">
              <span>{result.total} URL{result.total !== 1 ? 's' : ''}</span>
              <div className="flex gap-1">
                <button type="button" className="btn-secondary" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>Prev</button>
                <span className="flex items-center px-3">{page} / {totalPages}</span>
                <button type="button" className="btn-secondary" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>Next</button>
              </div>
            </div>
          )}
        </>
      )}

      {drawerOpen && (
        <URLDrawer
          initial={editing}
          onClose={() => { setDrawerOpen(false); setEditing(null) }}
          onSaved={handleSaved}
        />
      )}
    </div>
  )
}
