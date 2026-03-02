import { useQuery } from '@tanstack/react-query'
import { getSources } from '../utils/api'
import { useState, useMemo } from 'react'
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, ReferenceLine, Legend,
} from 'recharts'

const SOURCE_COLORS = {
  'Fox News': '#ef4444',
  'Breitbart': '#dc2626',
  'The Wall Street Journal': '#f97316',
  'AP News': '#22c55e',
  'Reuters': '#10b981',
  'The New York Times': '#3b82f6',
  'The Washington Post': '#6366f1',
  'The Guardian': '#8b5cf6',
  'NPR': '#06b6d4',
  'HuffPost': '#ec4899',
  'BBC News': '#64748b',
  'CNN': '#f59e0b',
}

const PALETTE = [
  '#3b82f6', '#ef4444', '#10b981', '#f97316', '#8b5cf6',
  '#06b6d4', '#ec4899', '#22c55e', '#dc2626', '#64748b', '#f59e0b',
]

const getColor = (name, index) => SOURCE_COLORS[name] || PALETTE[index % PALETTE.length]

const METRICS = [
  { value: 'political_lean', label: 'Political Lean' },
  { value: 'sentiment_score', label: 'Sentiment Score' },
  { value: 'reading_level', label: 'Reading Level (Flesch-Kincaid)' },
]

function formatMonth(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleString('en-US', { month: 'short', year: 'numeric' })
}

export default function Trends() {
  const [metric, setMetric] = useState('political_lean')
  const [hiddenSources, setHiddenSources] = useState(new Set())

  const { data: rawTrends, isLoading, isError } = useQuery({
    queryKey: ['trends-by-source', metric],
    queryFn: () =>
      fetch(`/api/analysis/trends/by-source?metric=${metric}`)
        .then(r => r.json()),
    staleTime: 60_000,
  })

  const { data: sources } = useQuery({ queryKey: ['sources'], queryFn: getSources })

  // Transform flat rows into chart-friendly format:
  // [{month: '2024-01', 'The New York Times': -0.6, 'Fox News': 0.7, ...}, ...]
  const { chartData, sourceNames } = useMemo(() => {
    if (!rawTrends || rawTrends.length === 0) return { chartData: [], sourceNames: [] }

    const byMonth = {}
    const names = new Set()

    for (const row of rawTrends) {
      if (!row.month || row.value == null) continue
      const label = formatMonth(row.month)
      if (!byMonth[row.month]) byMonth[row.month] = { month: label, _iso: row.month }
      byMonth[row.month][row.source_name] = parseFloat(row.value.toFixed(3))
      names.add(row.source_name)
    }

    const sorted = Object.values(byMonth).sort((a, b) => a._iso.localeCompare(b._iso))
    return { chartData: sorted, sourceNames: [...names].sort() }
  }, [rawTrends])

  const toggleSource = (name) => {
    setHiddenSources(prev => {
      const next = new Set(prev)
      next.has(name) ? next.delete(name) : next.add(name)
      return next
    })
  }

  const metricLabel = METRICS.find(m => m.value === metric)?.label || metric
  const yDomain = metric === 'political_lean' ? [-1.1, 1.1]
    : metric === 'sentiment_score' ? [-1.1, 1.1]
    : ['auto', 'auto']

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Trends Over Time</h1>
        <p className="text-gray-400 text-sm mt-1">
          Track how political lean, sentiment, and reading level change across outlets over time
        </p>
      </div>

      {/* Controls */}
      <div className="flex items-center gap-4">
        <label className="text-sm text-gray-400">Metric:</label>
        <select
          value={metric}
          onChange={e => setMetric(e.target.value)}
          className="bg-gray-800 border border-gray-700 text-white text-sm rounded px-3 py-1.5 focus:outline-none focus:border-blue-500"
        >
          {METRICS.map(m => (
            <option key={m.value} value={m.value}>{m.label}</option>
          ))}
        </select>
      </div>

      {/* Chart */}
      <div className="card">
        <h2 className="font-semibold text-white mb-4">
          {metricLabel} by Source Over Time
        </h2>

        {isLoading && <p className="text-gray-500 text-sm">Loading trend data…</p>}
        {isError && <p className="text-red-400 text-sm">Failed to load trend data. Make sure articles have been analyzed.</p>}

        {!isLoading && !isError && chartData.length === 0 && (
          <p className="text-gray-600 text-sm">
            No trend data yet. Ingest articles across multiple dates and run analysis first.
          </p>
        )}

        {chartData.length > 0 && (
          <>
            {/* Source toggles */}
            <div className="flex flex-wrap gap-2 mb-4">
              {sourceNames.map((name, i) => {
                const color = getColor(name, i)
                const hidden = hiddenSources.has(name)
                return (
                  <button
                    key={name}
                    onClick={() => toggleSource(name)}
                    className={`flex items-center gap-1.5 px-2 py-1 rounded text-xs border transition-opacity ${
                      hidden ? 'opacity-30' : 'opacity-100'
                    }`}
                    style={{ borderColor: color, color }}
                  >
                    <span
                      className="w-2 h-2 rounded-full"
                      style={{ background: color }}
                    />
                    {name}
                  </button>
                )
              })}
            </div>

            <ResponsiveContainer width="100%" height={380}>
              <LineChart data={chartData} margin={{ top: 5, right: 20, bottom: 40, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                <XAxis
                  dataKey="month"
                  tick={{ fill: '#6b7280', fontSize: 11 }}
                  angle={-30}
                  textAnchor="end"
                />
                <YAxis
                  domain={yDomain}
                  tick={{ fill: '#6b7280', fontSize: 11 }}
                  tickFormatter={v => typeof v === 'number' ? v.toFixed(2) : v}
                />
                {metric === 'political_lean' && (
                  <ReferenceLine y={0} stroke="#374151" strokeDasharray="4 2" />
                )}
                <Tooltip
                  contentStyle={{
                    background: '#111827',
                    border: '1px solid #374151',
                    borderRadius: 8,
                    fontSize: 12,
                  }}
                  formatter={(value, name) => [
                    typeof value === 'number' ? value.toFixed(3) : value,
                    name,
                  ]}
                />
                {sourceNames.map((name, i) => (
                  <Line
                    key={name}
                    type="monotone"
                    dataKey={name}
                    stroke={getColor(name, i)}
                    strokeWidth={2}
                    dot={{ r: 4, fill: getColor(name, i) }}
                    connectNulls={false}
                    hide={hiddenSources.has(name)}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>

            {metric === 'political_lean' && (
              <div className="flex justify-between text-xs text-gray-600 mt-1 px-2">
                <span>← Left (−1.0)</span>
                <span>Neutral (0.0)</span>
                <span>Right (+1.0) →</span>
              </div>
            )}
          </>
        )}
      </div>

      {/* Data table */}
      {chartData.length > 0 && (
        <div className="card overflow-x-auto">
          <h2 className="font-semibold text-white mb-3">Raw Data</h2>
          <table className="w-full text-xs text-left">
            <thead>
              <tr className="text-gray-500 border-b border-gray-800">
                <th className="pb-2 pr-4">Month</th>
                {sourceNames.map(n => (
                  <th key={n} className="pb-2 pr-4 text-right" style={{ color: getColor(n, sourceNames.indexOf(n)) }}>
                    {n.replace('The ', '')}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {chartData.map(row => (
                <tr key={row._iso} className="border-b border-gray-900 hover:bg-gray-800/20">
                  <td className="py-1.5 pr-4 text-gray-300">{row.month}</td>
                  {sourceNames.map(n => (
                    <td key={n} className="py-1.5 pr-4 text-right text-gray-400">
                      {row[n] != null ? row[n].toFixed(2) : '—'}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
