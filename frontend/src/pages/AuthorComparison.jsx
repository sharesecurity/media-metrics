import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ReferenceLine,
  ResponsiveContainer, Cell, Legend,
} from 'recharts'
import { Users } from 'lucide-react'
import { Link } from 'react-router-dom'
import { getAuthorComparison, getSources, getByDemographic, getByDemographicBySource } from '../utils/api'

// ── Colour palettes ──────────────────────────────────────────────────────────
const GENDER_COLORS = {
  male: '#3b82f6', female: '#ec4899', mostly_male: '#60a5fa',
  mostly_female: '#f472b6', unknown: '#6b7280',
}
const GENDER_LABELS = {
  male: 'Male', female: 'Female', mostly_male: 'Mostly Male',
  mostly_female: 'Mostly Female', unknown: 'Unknown',
}
const ETHNICITY_COLORS = {
  white: '#a78bfa', hispanic: '#34d399', black: '#fb923c',
  asian: '#facc15', api: '#67e8f9', unknown: '#6b7280',
}
const ETHNICITY_LABELS = {
  white: 'White', hispanic: 'Hispanic', black: 'Black',
  asian: 'Asian', api: 'API', unknown: 'Unknown',
}

function leanColor(v) {
  if (v == null) return '#6b7280'
  if (v < -0.3) return '#3b82f6'
  if (v > 0.3) return '#ef4444'
  return '#22c55e'
}

function LeanLabel({ v }) {
  if (v == null) return <span className="text-gray-600 text-xs">—</span>
  const color = v < -0.3 ? 'text-blue-400' : v > 0.3 ? 'text-red-400' : 'text-green-400'
  return <span className={`text-sm font-semibold ${color}`}>{v > 0 ? '+' : ''}{v.toFixed(2)}</span>
}

// ── Demographic summary section ───────────────────────────────────────────────
function DemographicPanel({ groupBy }) {
  const palette = groupBy === 'gender' ? GENDER_COLORS : ETHNICITY_COLORS
  const labels  = groupBy === 'gender' ? GENDER_LABELS  : ETHNICITY_LABELS

  const { data: overall = [] } = useQuery({
    queryKey: ['by-demographic', groupBy],
    queryFn: () => getByDemographic(groupBy),
  })
  const { data: bySource = [] } = useQuery({
    queryKey: ['by-demographic-by-source', groupBy],
    queryFn: () => getByDemographicBySource(groupBy),
  })

  if (overall.length === 0) {
    return (
      <p className="text-gray-600 text-sm py-4 text-center">
        No {groupBy} data available — run "Infer Demographics" on the Authors page first.
      </p>
    )
  }

  // Build grouped-bar dataset: one row per source, one bar per group
  const groups = [...new Set(bySource.map(r => r.group))].filter(Boolean)
  const sourceNames = [...new Set(bySource.map(r => r.source_name))]
  const grouped = sourceNames.map(src => {
    const row = { source: src }
    groups.forEach(g => {
      const found = bySource.find(r => r.source_name === src && r.group === g)
      row[g] = found?.avg_lean ?? null
    })
    return row
  })

  return (
    <div className="space-y-4">
      {/* Overall avg lean per group — horizontal bars */}
      <div>
        <p className="text-xs text-gray-500 uppercase tracking-wider mb-3">Overall avg lean by {groupBy}</p>
        <div className="space-y-2">
          {overall.map(r => {
            const pct = ((r.avg_lean ?? 0) + 1) / 2 * 100
            const color = palette[r.group] || '#6b7280'
            return (
              <div key={r.group} className="flex items-center gap-3">
                <span className="text-xs w-28 text-gray-400 shrink-0 text-right">
                  {labels[r.group] || r.group}
                </span>
                <div className="flex-1 h-5 bg-gray-800 rounded relative">
                  <div
                    className="absolute top-1/2 -translate-y-1/2 w-3 h-3 rounded-full border-2 border-gray-900"
                    style={{ left: `calc(${pct}% - 6px)`, backgroundColor: color }}
                  />
                  {/* center line */}
                  <div className="absolute left-1/2 top-0 w-px h-full bg-gray-700" />
                </div>
                <span className="text-xs w-14 shrink-0"
                  style={{ color }}>
                  {r.avg_lean != null ? `${r.avg_lean > 0 ? '+' : ''}${r.avg_lean.toFixed(3)}` : '—'}
                </span>
                <span className="text-xs text-gray-600 w-20 shrink-0">
                  {r.analyzed_count} analyzed
                </span>
              </div>
            )
          })}
        </div>
      </div>

      {/* Grouped bar chart: avg lean per outlet × group */}
      {grouped.length > 0 && groups.length > 0 && (
        <div>
          <p className="text-xs text-gray-500 uppercase tracking-wider mb-3">Avg lean by outlet + {groupBy}</p>
          <ResponsiveContainer width="100%" height={Math.max(160, grouped.length * 38)}>
            <BarChart data={grouped} layout="vertical" margin={{ left: 110, right: 40 }}>
              <XAxis type="number" domain={[-1, 1]} tickCount={5}
                tick={{ fill: '#6b7280', fontSize: 10 }} />
              <YAxis type="category" dataKey="source"
                tick={{ fill: '#9ca3af', fontSize: 11 }} width={105} />
              <Tooltip
                contentStyle={{ background: '#111827', border: '1px solid #374151', borderRadius: 8 }}
                formatter={(val) => val != null ? [`${val > 0 ? '+' : ''}${val.toFixed(3)}`, ''] : ['—', '']}
              />
              <ReferenceLine x={0} stroke="#374151" strokeDasharray="4 2" />
              <Legend
                formatter={(g) => <span style={{ color: palette[g] || '#9ca3af', fontSize: 11 }}>{labels[g] || g}</span>}
              />
              {groups.map(g => (
                <Bar key={g} dataKey={g} fill={palette[g] || '#6b7280'} radius={[0, 3, 3, 0]} maxBarSize={14} />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function AuthorComparison() {
  const [sourceFilter, setSourceFilter] = useState('')
  const [sortBy, setSortBy]             = useState('lean')
  const [minArticles, setMinArticles]   = useState(1)
  const [demoTab, setDemoTab]           = useState('gender') // gender | ethnicity

  const { data: sources = [] } = useQuery({ queryKey: ['sources'], queryFn: getSources })

  const { data: authors = [], isLoading } = useQuery({
    queryKey: ['author-comparison', sourceFilter, minArticles],
    queryFn: () => getAuthorComparison({
      source_id: sourceFilter || undefined,
      min_articles: minArticles,
    }),
  })

  const withLean    = authors.filter(a => a.avg_lean != null)
  const withoutLean = authors.filter(a => a.avg_lean == null)

  const sorted = [...withLean].sort((a, b) => {
    if (sortBy === 'lean')     return (a.avg_lean ?? 0) - (b.avg_lean ?? 0)
    if (sortBy === 'name')     return a.name.localeCompare(b.name)
    if (sortBy === 'articles') return b.article_count - a.article_count
    return 0
  })

  const chartData = sorted.map(a => ({
    name: a.name.split(' ').slice(-1)[0],
    fullName: a.name,
    avg_lean: a.avg_lean,
    source: a.source_name,
  }))

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white flex items-center gap-2">
          <Users size={24} />
          Author Comparison
        </h1>
        <p className="text-gray-400 mt-1 text-sm">
          Average political lean per author · {withLean.length} authors with analysis data
        </p>
      </div>

      {/* ── Demographics summary panel ─────────────────────────────────────── */}
      <div className="bg-gray-900 rounded-xl p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-semibold text-white text-sm">Demographic Breakdown</h2>
          <div className="flex rounded-lg overflow-hidden border border-gray-700 text-xs">
            {[['gender', 'By Gender'], ['ethnicity', 'By Ethnicity']].map(([val, label]) => (
              <button
                key={val}
                onClick={() => setDemoTab(val)}
                className={`px-3 py-1.5 transition-colors ${demoTab === val ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'}`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
        <DemographicPanel groupBy={demoTab} />
      </div>

      {/* ── Per-author chart + table ────────────────────────────────────────── */}

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <select
          value={sourceFilter}
          onChange={e => setSourceFilter(e.target.value)}
          className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
        >
          <option value="">All Outlets</option>
          {sources.map(s => (
            <option key={s.id} value={s.id}>{s.name}</option>
          ))}
        </select>
        <select
          value={minArticles}
          onChange={e => setMinArticles(Number(e.target.value))}
          className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
        >
          <option value={1}>Min 1 article</option>
          <option value={2}>Min 2 articles</option>
          <option value={3}>Min 3 articles</option>
          <option value={5}>Min 5 articles</option>
        </select>
        <div className="flex rounded-lg overflow-hidden border border-gray-700 text-sm">
          {[['lean', 'By Lean'], ['articles', 'By Count'], ['name', 'By Name']].map(([val, label]) => (
            <button
              key={val}
              onClick={() => setSortBy(val)}
              className={`px-3 py-2 transition-colors ${sortBy === val ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'}`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Per-author horizontal bar chart */}
      {withLean.length > 0 && (
        <div className="bg-gray-900 rounded-xl p-5">
          <h2 className="text-white font-semibold mb-1">Average Political Lean by Author</h2>
          <p className="text-gray-500 text-xs mb-4">−1.0 = far left · 0.0 = neutral · +1.0 = far right</p>
          <ResponsiveContainer width="100%" height={Math.max(180, chartData.length * 22)}>
            <BarChart data={chartData} layout="vertical" margin={{ left: 80, right: 60 }}>
              <XAxis type="number" domain={[-1, 1]} tickCount={9}
                tick={{ fill: '#6b7280', fontSize: 10 }} />
              <YAxis type="category" dataKey="name" tick={{ fill: '#9ca3af', fontSize: 11 }} width={75} />
              <Tooltip
                contentStyle={{ background: '#111827', border: '1px solid #374151', borderRadius: 8 }}
                formatter={(val, _, props) => [
                  `${val > 0 ? '+' : ''}${val?.toFixed(3)}`,
                  props.payload.fullName,
                ]}
              />
              <ReferenceLine x={0} stroke="#374151" strokeDasharray="4 2" />
              <Bar dataKey="avg_lean" radius={[0, 3, 3, 0]}>
                {chartData.map((entry, i) => (
                  <Cell key={i} fill={leanColor(entry.avg_lean)} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Table */}
      <div className="bg-gray-900 rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-800">
          <h2 className="font-semibold text-white text-sm">
            {sorted.length} authors
            {withoutLean.length > 0 && (
              <span className="text-gray-600 font-normal ml-2">
                · {withoutLean.length} without analysis data
              </span>
            )}
          </h2>
        </div>
        {isLoading ? (
          <div className="p-8 text-center text-gray-500">Loading...</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800 text-gray-400 text-left">
                <th className="px-4 py-3">Author</th>
                <th className="px-4 py-3">Outlet</th>
                <th className="px-4 py-3">Gender</th>
                <th className="px-4 py-3">Ethnicity</th>
                <th className="px-4 py-3 text-center">Articles</th>
                <th className="px-4 py-3 text-center">Analyzed</th>
                <th className="px-4 py-3">Avg Lean</th>
                <th className="px-4 py-3">Lean Bar</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map(author => (
                <tr key={author.id} className="border-b border-gray-800 hover:bg-gray-800/50 transition-colors">
                  <td className="px-4 py-3">
                    <Link to={`/authors/${author.id}`} className="text-white hover:text-blue-400 font-medium">
                      {author.name}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-gray-400 text-xs">{author.source_name || '—'}</td>
                  <td className="px-4 py-3">
                    {author.gender ? (
                      <span
                        className="px-2 py-0.5 rounded text-xs font-medium"
                        style={{
                          background: (GENDER_COLORS[author.gender] || '#6b7280') + '33',
                          color: GENDER_COLORS[author.gender] || '#6b7280',
                        }}
                      >
                        {GENDER_LABELS[author.gender] || author.gender}
                      </span>
                    ) : <span className="text-gray-700 text-xs">—</span>}
                  </td>
                  <td className="px-4 py-3">
                    {author.ethnicity ? (
                      <span
                        className="px-2 py-0.5 rounded text-xs font-medium"
                        style={{
                          background: (ETHNICITY_COLORS[author.ethnicity] || '#6b7280') + '33',
                          color: ETHNICITY_COLORS[author.ethnicity] || '#6b7280',
                        }}
                      >
                        {ETHNICITY_LABELS[author.ethnicity] || author.ethnicity}
                      </span>
                    ) : <span className="text-gray-700 text-xs">—</span>}
                  </td>
                  <td className="px-4 py-3 text-center text-gray-400">{author.article_count}</td>
                  <td className="px-4 py-3 text-center text-gray-400">{author.analyzed_count}</td>
                  <td className="px-4 py-3"><LeanLabel v={author.avg_lean} /></td>
                  <td className="px-4 py-3 min-w-[100px]">
                    {author.avg_lean != null ? (
                      <div className="w-24 h-1.5 bg-gray-800 rounded-full relative">
                        <div
                          className="absolute top-1/2 -translate-y-1/2 w-2.5 h-2.5 rounded-full border border-white"
                          style={{
                            left: `calc(${((author.avg_lean + 1) / 2) * 100}% - 5px)`,
                            backgroundColor: leanColor(author.avg_lean),
                          }}
                        />
                      </div>
                    ) : null}
                  </td>
                </tr>
              ))}
              {withoutLean.map(author => (
                <tr key={author.id} className="border-b border-gray-800/50 opacity-50">
                  <td className="px-4 py-3">
                    <Link to={`/authors/${author.id}`} className="text-gray-500 hover:text-gray-300">
                      {author.name}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-gray-600 text-xs">{author.source_name || '—'}</td>
                  <td className="px-4 py-3 text-gray-700 text-xs">—</td>
                  <td className="px-4 py-3 text-gray-700 text-xs">—</td>
                  <td className="px-4 py-3 text-center text-gray-600">{author.article_count}</td>
                  <td className="px-4 py-3 text-center text-gray-600">0</td>
                  <td className="px-4 py-3 text-gray-700 text-xs">—</td>
                  <td className="px-4 py-3"></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
