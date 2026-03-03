import { useQuery } from '@tanstack/react-query'
import { getArticles, getSources, getTrendsBySource, getSourceSummary, getByDemographic, getByDemographicBySource } from '../utils/api'
import { Link } from 'react-router-dom'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, ReferenceLine,
  ScatterChart, Scatter, CartesianGrid, Legend,
} from 'recharts'
import { useState } from 'react'

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
}
const getColor = (name) => SOURCE_COLORS[name] || '#9ca3af'

const GENDER_COLORS = {
  male: '#3b82f6', female: '#ec4899', mostly_male: '#60a5fa',
  mostly_female: '#f472b6', unknown: '#6b7280',
}
const GENDER_LABELS = {
  male: 'Male', female: 'Female', mostly_male: 'Mostly Male',
  mostly_female: 'Mostly Female', unknown: 'Unknown',
}
const ETHNICITY_COLORS = {
  white: '#a78bfa', black: '#fbbf24', asian: '#34d399', hispanic: '#f97316', unknown: '#6b7280',
}
const ETHNICITY_LABELS = {
  white: 'White', black: 'Black', asian: 'Asian', hispanic: 'Hispanic', unknown: 'Unknown',
}

function leanColor(v) {
  if (v == null) return '#6b7280'
  return v < -0.25 ? '#3b82f6' : v > 0.25 ? '#ef4444' : '#22c55e'
}

function LeanBar({ value, label, sub }) {
  if (value == null) return null
  const pct = ((value + 1) / 2) * 100
  const color = leanColor(value)
  return (
    <div className="flex items-center gap-3 py-1.5">
      <div className="w-48 shrink-0">
        <span className="text-sm text-gray-300 truncate block">{label}</span>
        {sub && <span className="text-xs text-gray-600">{sub}</span>}
      </div>
      <div className="flex-1 relative h-2 rounded-full"
        style={{ background: 'linear-gradient(to right, #3b82f6 0%, #22c55e 50%, #ef4444 100%)' }}>
        <div className="absolute top-1/2 -translate-y-1/2 w-3 h-3 rounded-full bg-white border-2 border-gray-900"
          style={{ left: `calc(${pct}% - 6px)` }} />
      </div>
      <span className="text-xs w-12 text-right font-semibold" style={{ color }}>
        {value > 0 ? '+' : ''}{value.toFixed(2)}
      </span>
    </div>
  )
}

function StatTable({ rows, columns }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-800">
            {columns.map(c => (
              <th key={c.key} className={`text-left text-xs text-gray-500 uppercase tracking-wider px-3 py-2 font-medium ${c.right ? 'text-right' : ''}`}>
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-b border-gray-800/50 hover:bg-gray-800/30 transition-colors">
              {columns.map(c => (
                <td key={c.key} className={`px-3 py-2.5 ${c.right ? 'text-right' : ''}`}>
                  {c.render ? c.render(row[c.key], row) : (
                    <span className={c.color ? c.color(row[c.key]) : 'text-gray-300'}>
                      {row[c.key] ?? '—'}
                    </span>
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function leanColorClass(v) {
  if (v == null) return 'text-gray-600'
  return v < -0.25 ? 'text-blue-400' : v > 0.25 ? 'text-red-400' : 'text-green-400'
}

function sentimentColorClass(v) {
  if (v == null) return 'text-gray-600'
  return v > 0.05 ? 'text-green-400' : v < -0.05 ? 'text-red-400' : 'text-yellow-400'
}

// ---- By Source Tab ----
function BySourceTab() {
  const { data: summary = [], isLoading } = useQuery({
    queryKey: ['source-summary'],
    queryFn: getSourceSummary,
  })
  const { data: articles } = useQuery({
    queryKey: ['articles-bias'],
    queryFn: () => getArticles({ limit: 300 }),
  })

  const analyzed = summary.filter(s => s.analyzed_count > 0)
    .sort((a, b) => (a.avg_lean ?? 0) - (b.avg_lean ?? 0))

  const scatterData = (articles || [])
    .filter(a => a.political_lean != null && a.sentiment_score != null)
    .map(a => ({
      x: a.political_lean,
      y: a.sentiment_score,
      name: a.title?.slice(0, 40),
      source: a.source_name,
      color: getColor(a.source_name),
      id: a.id,
    }))

  const chartData = analyzed.map(s => ({
    name: s.name.replace('The ', ''),
    avg_lean: s.avg_lean,
    baseline: s.baseline_lean,
  }))

  if (isLoading) return <div className="text-gray-500 text-sm p-4">Loading...</div>

  return (
    <div className="space-y-6">
      {/* Lean bar chart */}
      {chartData.length > 0 && (
        <div className="bg-gray-900 rounded-xl p-5">
          <h3 className="text-white font-semibold mb-1">Avg Political Lean per Outlet (from Analysis)</h3>
          <p className="text-gray-500 text-xs mb-4">Based on analyzed articles · blue=left, green=center, red=right</p>
          <ResponsiveContainer width="100%" height={Math.max(160, chartData.length * 36)}>
            <BarChart data={chartData} layout="vertical" margin={{ left: 100, right: 60 }}>
              <XAxis type="number" domain={[-1, 1]} tickCount={9} tick={{ fill: '#6b7280', fontSize: 10 }} />
              <YAxis type="category" dataKey="name" tick={{ fill: '#9ca3af', fontSize: 11 }} width={95} />
              <Tooltip
                contentStyle={{ background: '#111827', border: '1px solid #374151', borderRadius: 8 }}
                formatter={(val) => [`${val > 0 ? '+' : ''}${val?.toFixed(3)}`, 'Avg Lean']}
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

      {/* Stats table */}
      <div className="bg-gray-900 rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-800">
          <h3 className="text-white font-semibold text-sm">Source Stats Table</h3>
        </div>
        <StatTable
          rows={summary}
          columns={[
            { key: 'name', label: 'Source', render: (v, row) => <Link to={`/sources/${row.id}`} className="text-white hover:text-blue-400 font-medium">{v}</Link> },
            { key: 'article_count', label: 'Articles', right: true, render: (v) => <span className="text-gray-400">{v}</span> },
            { key: 'analyzed_count', label: 'Analyzed', right: true, render: (v) => <span className="text-gray-400">{v}</span> },
            {
              key: 'avg_lean', label: 'Avg Lean', right: true,
              render: (v) => v != null
                ? <span className={`font-semibold ${leanColorClass(v)}`}>{v > 0 ? '+' : ''}{v?.toFixed(3)}</span>
                : <span className="text-gray-700">—</span>
            },
            {
              key: 'baseline_lean', label: 'Baseline', right: true,
              render: (v) => v != null
                ? <span className="text-gray-500 text-xs">{v > 0 ? '+' : ''}{v?.toFixed(2)}</span>
                : <span className="text-gray-700">—</span>
            },
            {
              key: 'avg_sentiment', label: 'Avg Sentiment', right: true,
              render: (v) => v != null
                ? <span className={sentimentColorClass(v)}>{v > 0 ? '+' : ''}{v?.toFixed(3)}</span>
                : <span className="text-gray-700">—</span>
            },
            {
              key: 'avg_reading_level', label: 'Reading Lvl', right: true,
              render: (v) => v != null
                ? <span className="text-gray-300">{v?.toFixed(1)}</span>
                : <span className="text-gray-700">—</span>
            },
          ]}
        />
      </div>

      {/* Scatter */}
      {scatterData.length > 0 && (
        <div className="bg-gray-900 rounded-xl p-5">
          <h3 className="text-white font-semibold mb-4">Political Lean vs. Sentiment (per article)</h3>
          <ResponsiveContainer width="100%" height={280}>
            <ScatterChart>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
              <XAxis dataKey="x" type="number" domain={[-1, 1]} name="Political Lean"
                label={{ value: 'Political Lean', position: 'insideBottom', offset: -5, fill: '#6b7280' }}
                tick={{ fill: '#6b7280', fontSize: 11 }} />
              <YAxis dataKey="y" type="number" domain={[-1, 1]} name="Sentiment"
                label={{ value: 'Sentiment', angle: -90, position: 'insideLeft', fill: '#6b7280' }}
                tick={{ fill: '#6b7280', fontSize: 11 }} />
              <ReferenceLine x={0} stroke="#374151" />
              <ReferenceLine y={0} stroke="#374151" />
              <Tooltip
                contentStyle={{ background: '#111827', border: '1px solid #374151', borderRadius: 8, fontSize: 12 }}
                content={({ payload }) => {
                  if (!payload?.length) return null
                  const d = payload[0].payload
                  return (
                    <div className="bg-gray-900 border border-gray-700 rounded-lg p-3 text-xs max-w-xs">
                      <p className="text-white font-medium">{d.name}</p>
                      <p className="text-gray-400">{d.source}</p>
                      <p>Lean: <span className="text-white">{d.x?.toFixed(3)}</span></p>
                      <p>Sentiment: <span className="text-white">{d.y?.toFixed(3)}</span></p>
                    </div>
                  )
                }}
              />
              <Scatter data={scatterData} shape={(props) => {
                const { cx, cy, payload } = props
                return <circle cx={cx} cy={cy} r={5} fill={payload.color} fillOpacity={0.75} stroke="none" />
              }} />
            </ScatterChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}

// ---- By Gender Tab ----
function ByGenderTab() {
  const { data: genderData = [] } = useQuery({
    queryKey: ['by-demographic', 'gender'],
    queryFn: () => getByDemographic('gender'),
  })
  const { data: bySource = [] } = useQuery({
    queryKey: ['by-demographic-by-source', 'gender'],
    queryFn: () => getByDemographicBySource('gender'),
  })

  // Build cross-dimensional chart: group by source, with bars per gender
  const sources = [...new Set(bySource.map(r => r.source_name))].sort()
  const genders = [...new Set(bySource.map(r => r.group))].filter(Boolean)
  const crossData = sources.map(src => {
    const row = { source: src.replace('The ', '') }
    genders.forEach(g => {
      const match = bySource.find(r => r.source_name === src && r.group === g)
      row[g] = match?.avg_lean ?? null
    })
    return row
  })

  return (
    <div className="space-y-6">
      {/* Overall gender summary */}
      <div className="bg-gray-900 rounded-xl p-5">
        <h3 className="text-white font-semibold mb-3">Avg Political Lean by Author Gender (overall)</h3>
        <div className="space-y-1">
          {genderData.map(g => (
            <LeanBar
              key={g.group}
              value={g.avg_lean}
              label={GENDER_LABELS[g.group] || g.group}
              sub={`${g.analyzed_count} articles analyzed`}
            />
          ))}
        </div>
        {genderData.length === 0 && (
          <p className="text-gray-600 text-sm">No demographic data yet. Run "Infer Demographics" on the Authors page first.</p>
        )}
      </div>

      {/* Cross-dimensional chart */}
      {crossData.length > 0 && genders.length > 1 && (
        <div className="bg-gray-900 rounded-xl p-5">
          <h3 className="text-white font-semibold mb-1">Male vs. Female Author Lean by Outlet</h3>
          <p className="text-gray-500 text-xs mb-4">Only outlets with multiple gender-inferred authors</p>
          <ResponsiveContainer width="100%" height={Math.max(160, crossData.length * 40)}>
            <BarChart data={crossData} layout="vertical" margin={{ left: 110, right: 60 }}>
              <XAxis type="number" domain={[-1, 1]} tickCount={9} tick={{ fill: '#6b7280', fontSize: 10 }} />
              <YAxis type="category" dataKey="source" tick={{ fill: '#9ca3af', fontSize: 11 }} width={105} />
              <Tooltip
                contentStyle={{ background: '#111827', border: '1px solid #374151', borderRadius: 8 }}
                formatter={(val, name) => [val != null ? `${val > 0 ? '+' : ''}${val.toFixed(3)}` : '—', GENDER_LABELS[name] || name]}
              />
              <ReferenceLine x={0} stroke="#374151" strokeDasharray="4 2" />
              {genders.map(g => (
                <Bar key={g} dataKey={g} name={g} fill={GENDER_COLORS[g] || '#6b7280'}
                  radius={[0, 2, 2, 0]} barSize={10} />
              ))}
              <Legend formatter={(v) => GENDER_LABELS[v] || v} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Stats table */}
      <div className="bg-gray-900 rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-800">
          <h3 className="text-white font-semibold text-sm">Gender Stats Table</h3>
        </div>
        <StatTable
          rows={genderData}
          columns={[
            {
              key: 'group', label: 'Gender',
              render: (v) => (
                <span className="px-2 py-0.5 rounded text-xs font-medium"
                  style={{ background: (GENDER_COLORS[v] || '#6b7280') + '33', color: GENDER_COLORS[v] || '#6b7280' }}>
                  {GENDER_LABELS[v] || v}
                </span>
              )
            },
            { key: 'article_count', label: 'Articles', right: true, render: v => <span className="text-gray-400">{v}</span> },
            { key: 'analyzed_count', label: 'Analyzed', right: true, render: v => <span className="text-gray-400">{v}</span> },
            {
              key: 'avg_lean', label: 'Avg Lean', right: true,
              render: v => v != null
                ? <span className={`font-semibold ${leanColorClass(v)}`}>{v > 0 ? '+' : ''}{v?.toFixed(3)}</span>
                : <span className="text-gray-700">—</span>
            },
            {
              key: 'avg_sentiment', label: 'Avg Sentiment', right: true,
              render: v => v != null
                ? <span className={sentimentColorClass(v)}>{v > 0 ? '+' : ''}{v?.toFixed(3)}</span>
                : <span className="text-gray-700">—</span>
            },
            {
              key: 'avg_reading_level', label: 'Reading Lvl', right: true,
              render: v => v != null ? <span className="text-gray-300">{v?.toFixed(1)}</span> : <span className="text-gray-700">—</span>
            },
          ]}
        />
      </div>
    </div>
  )
}

// ---- By Ethnicity Tab ----
function ByEthnicityTab() {
  const { data: ethData = [] } = useQuery({
    queryKey: ['by-demographic', 'ethnicity'],
    queryFn: () => getByDemographic('ethnicity'),
  })
  const { data: bySource = [] } = useQuery({
    queryKey: ['by-demographic-by-source', 'ethnicity'],
    queryFn: () => getByDemographicBySource('ethnicity'),
  })

  const sources = [...new Set(bySource.map(r => r.source_name))].sort()
  const groups = [...new Set(bySource.map(r => r.group))].filter(Boolean)
  const crossData = sources.map(src => {
    const row = { source: src.replace('The ', '') }
    groups.forEach(g => {
      const match = bySource.find(r => r.source_name === src && r.group === g)
      row[g] = match?.avg_lean ?? null
    })
    return row
  })

  return (
    <div className="space-y-6">
      <div className="bg-gray-900 rounded-xl p-5">
        <h3 className="text-white font-semibold mb-3">Avg Political Lean by Author Ethnicity (overall)</h3>
        <div className="space-y-1">
          {ethData.map(g => (
            <LeanBar
              key={g.group}
              value={g.avg_lean}
              label={ETHNICITY_LABELS[g.group] || g.group}
              sub={`${g.analyzed_count} articles analyzed`}
            />
          ))}
        </div>
        {ethData.length === 0 && (
          <p className="text-gray-600 text-sm">
            No ethnicity data yet — ethnicity inference coverage is low (Census surname lookup).
            Run "Infer Demographics" on Authors page, or improve with ethnicolr ML model.
          </p>
        )}
      </div>

      {crossData.length > 0 && groups.length > 1 && (
        <div className="bg-gray-900 rounded-xl p-5">
          <h3 className="text-white font-semibold mb-1">Author Ethnicity Lean by Outlet</h3>
          <p className="text-gray-500 text-xs mb-4">Outlets with ethnicity-inferred authors (coverage may be low)</p>
          <ResponsiveContainer width="100%" height={Math.max(160, crossData.length * 40)}>
            <BarChart data={crossData} layout="vertical" margin={{ left: 110, right: 60 }}>
              <XAxis type="number" domain={[-1, 1]} tickCount={9} tick={{ fill: '#6b7280', fontSize: 10 }} />
              <YAxis type="category" dataKey="source" tick={{ fill: '#9ca3af', fontSize: 11 }} width={105} />
              <Tooltip
                contentStyle={{ background: '#111827', border: '1px solid #374151', borderRadius: 8 }}
                formatter={(val, name) => [val != null ? `${val > 0 ? '+' : ''}${val.toFixed(3)}` : '—', ETHNICITY_LABELS[name] || name]}
              />
              <ReferenceLine x={0} stroke="#374151" strokeDasharray="4 2" />
              {groups.map(g => (
                <Bar key={g} dataKey={g} name={g} fill={ETHNICITY_COLORS[g] || '#6b7280'}
                  radius={[0, 2, 2, 0]} barSize={10} />
              ))}
              <Legend formatter={(v) => ETHNICITY_LABELS[v] || v} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      <div className="bg-gray-900 rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-800">
          <h3 className="text-white font-semibold text-sm">Ethnicity Stats Table</h3>
        </div>
        <StatTable
          rows={ethData}
          columns={[
            {
              key: 'group', label: 'Ethnicity',
              render: (v) => (
                <span className="px-2 py-0.5 rounded text-xs font-medium"
                  style={{ background: (ETHNICITY_COLORS[v] || '#6b7280') + '33', color: ETHNICITY_COLORS[v] || '#6b7280' }}>
                  {ETHNICITY_LABELS[v] || v}
                </span>
              )
            },
            { key: 'article_count', label: 'Articles', right: true, render: v => <span className="text-gray-400">{v}</span> },
            { key: 'analyzed_count', label: 'Analyzed', right: true, render: v => <span className="text-gray-400">{v}</span> },
            {
              key: 'avg_lean', label: 'Avg Lean', right: true,
              render: v => v != null
                ? <span className={`font-semibold ${leanColorClass(v)}`}>{v > 0 ? '+' : ''}{v?.toFixed(3)}</span>
                : <span className="text-gray-700">—</span>
            },
            {
              key: 'avg_sentiment', label: 'Avg Sentiment', right: true,
              render: v => v != null
                ? <span className={sentimentColorClass(v)}>{v > 0 ? '+' : ''}{v?.toFixed(3)}</span>
                : <span className="text-gray-700">—</span>
            },
          ]}
        />
      </div>
    </div>
  )
}

// ---- Main Component ----
const TABS = ['By Source', 'By Gender', 'By Ethnicity']

export default function BiasAnalysis() {
  const [tab, setTab] = useState('By Source')

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Bias Analysis</h1>
        <p className="text-gray-400 text-sm mt-1">Compare political lean and sentiment across sources, gender, and ethnicity</p>
      </div>

      {/* Tab bar */}
      <div className="flex rounded-lg overflow-hidden border border-gray-700 text-sm w-fit">
        {TABS.map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-5 py-2.5 transition-colors ${tab === t ? 'bg-blue-600 text-white' : 'bg-gray-900 text-gray-400 hover:bg-gray-800 hover:text-white'}`}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === 'By Source' && <BySourceTab />}
      {tab === 'By Gender' && <ByGenderTab />}
      {tab === 'By Ethnicity' && <ByEthnicityTab />}
    </div>
  )
}
