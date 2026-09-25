import type { ShortURL } from '../types'

export function StatusBadge({ url }: { url: ShortURL }) {
  if (url.is_expired) {
    return <span className="badge bg-amber-100 text-amber-700">Expired</span>
  }
  if (!url.is_active) {
    return <span className="badge bg-slate-100 text-slate-600">Disabled</span>
  }
  return <span className="badge bg-emerald-100 text-emerald-700">Active</span>
}