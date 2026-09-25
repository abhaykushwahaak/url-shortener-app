interface StatCardProps {
  label: string
  value: number | string
  hint?: string
  tone?: 'default' | 'positive' | 'warning'
}

const toneClass: Record<NonNullable<StatCardProps['tone']>, string> = {
  default: 'text-slate-900',
  positive: 'text-emerald-600',
  warning: 'text-amber-600',
}

export function StatCard({ label, value, hint, tone = 'default' }: StatCardProps) {
  return (
    <div className="card">
      <p className="text-sm font-medium text-slate-500">{label}</p>
      <p className={`mt-1.5 text-2xl font-semibold ${toneClass[tone]}`}>{value}</p>
      {hint ? <p className="mt-1 text-xs text-slate-400">{hint}</p> : null}
    </div>
  )
}