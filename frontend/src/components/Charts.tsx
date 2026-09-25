import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { CountByKey, TimelinePoint } from '../types'
import { formatNumber } from '../lib/format'

const PALETTE = ['#2856d8', '#059669', '#d97706', '#e11d48', '#7c3aed']
const GRID = '#e2e8f0'
const TICK = '#94a3b8'
const TT: React.CSSProperties = { borderRadius: 8, border: '1px solid #e2e8f0', fontSize: 13 }

export function ClickTimelineChart({ data, color = PALETTE[0] }: { data: TimelinePoint[]; color?: string }) {
  return (
    <ResponsiveContainer width="100%" height={220}>
      <AreaChart data={data} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
        <defs>
          <linearGradient id="tlGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor={color} stopOpacity={0.18} />
            <stop offset="95%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke={GRID} />
        <XAxis dataKey="date" tick={{ fontSize: 11, fill: TICK }} tickLine={false} axisLine={false} minTickGap={32} />
        <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: TICK }} tickLine={false} axisLine={false} tickFormatter={(v: number) => v >= 1000 ? `${(v/1000).toFixed(1)}k` : String(v)} />
        <Tooltip contentStyle={TT} formatter={(v: number) => [formatNumber(v), 'Clicks']} />
        <Area type="monotone" dataKey="clicks" stroke={color} strokeWidth={2} fill="url(#tlGrad)" dot={false} activeDot={{ r: 4, strokeWidth: 0, fill: color }} />
      </AreaChart>
    </ResponsiveContainer>
  )
}

export function BreakdownBarChart({ data, color = PALETTE[0], maxBars = 8 }: { data: CountByKey[]; color?: string; maxBars?: number }) {
  const rows = data.slice(0, maxBars)
  return (
    <ResponsiveContainer width="100%" height={Math.max(160, rows.length * 36 + 32)}>
      <BarChart layout="vertical" data={rows} margin={{ top: 0, right: 24, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={GRID} horizontal={false} />
        <XAxis type="number" tick={{ fontSize: 11, fill: TICK }} tickLine={false} axisLine={false} allowDecimals={false} />
        <YAxis type="category" dataKey="key" width={90} tick={{ fontSize: 11, fill: TICK }} tickLine={false} axisLine={false} />
        <Tooltip contentStyle={TT} formatter={(v: number) => [formatNumber(v), 'Clicks']} />
        <Bar dataKey="count" fill={color} radius={[0, 4, 4, 0]} maxBarSize={20} />
      </BarChart>
    </ResponsiveContainer>
  )
}

export function DonutChart({ data, maxSlices = 5 }: { data: CountByKey[]; maxSlices?: number }) {
  const top = data.slice(0, maxSlices - 1)
  const otherCount = data.slice(maxSlices - 1).reduce((s, d) => s + d.count, 0)
  const slices = otherCount > 0 ? [...top, { key: 'Other', count: otherCount }] : top
  return (
    <ResponsiveContainer width="100%" height={200}>
      <PieChart>
        <Pie data={slices} dataKey="count" nameKey="key" cx="50%" cy="50%" innerRadius={55} outerRadius={80} paddingAngle={2}>
          {slices.map((_e, i) => <Cell key={i} fill={PALETTE[i % PALETTE.length]} />)}
        </Pie>
        <Tooltip contentStyle={TT} formatter={(v: number) => [formatNumber(v), 'Clicks']} />
        <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12, color: '#64748b' }} />
      </PieChart>
    </ResponsiveContainer>
  )
}

export function TopURLsChart({ data }: { data: { short_code: string; clicks: number }[] }) {
  return (
    <ResponsiveContainer width="100%" height={Math.max(140, data.length * 40 + 32)}>
      <BarChart layout="vertical" data={data} margin={{ top: 0, right: 24, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={GRID} horizontal={false} />
        <XAxis type="number" tick={{ fontSize: 11, fill: TICK }} tickLine={false} axisLine={false} allowDecimals={false} />
        <YAxis type="category" dataKey="short_code" width={80} tick={{ fontSize: 11, fill: TICK }} tickLine={false} axisLine={false} />
        <Tooltip contentStyle={TT} formatter={(v: number) => [formatNumber(v), 'Clicks']} />
        <Bar dataKey="clicks" radius={[0, 4, 4, 0]} maxBarSize={22}>
          {data.map((_e, i) => <Cell key={i} fill={PALETTE[i % PALETTE.length]} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
