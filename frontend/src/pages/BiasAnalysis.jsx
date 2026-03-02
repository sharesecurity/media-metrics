import { useQuery } from '@tanstack/react-query'
import { getArticles, getSources, getTrends } from '../utils/api'
import { Link } from 'react-router-dom'
import {
  ScatterChart, Scatter, XAxis, YAxis, Tooltip, ResponsiveContainer,
  LineChart, Line, Legend, CartesianGrid, ReferenceLine
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

const BiasBar = ({ value, label, confidence }) => {
  if (value == null) return null
  const pct = ((value + 1) / 2) * 100
  const color = value < -0.3 ? '#3b82f6' : value > 0.3 ? '#ef4444' : '#22c55e'
  return (
    <div className="flex items-center gap-3 py-1">
      <span className="text-sm text-gray-300 w-44 truncate">{label}</span>
      <div className="flex-1 relative h-2 rounded-full"
        style={{ background: 'linear-gradient(to right, #3b82f6 0%, #22c55e 50%, #ef4444 100%)' }}>
        <div className="absolute top-1/2 -translate-y-1/2 w-3 h-3 rounded-full bg-white border-2 border-gray-900"
          style={{ left: `calc(${pct}% - 6px)` }} />
      </div>
      <span className="text-xs w-12 text-right" style={{ color }}>
        {value > 0 ? '+' : ''}{value.toFixed(2)}
      </span>
      {confidence != null && (
        <span className="text-xs text-gray-600 w-16">
          {(confidence * 100).toFixed(0)}% conf.
        </span>
      )}
    </div>
  )
}

export default function BiasAnalysis() {
  const [metric, setMetric] = useState('political_lean')

  const { data: articles } = useQuery({
    queryKey: ['articles-bias'],
    queryFn: () => getArticles({ limit: 200 }),
  })
  const { data: sources } = useQuery({ queryKey: ['sources'], queryFn: getSources })
  const { data: trends } = useQuery({
    queryKey: ['trends', metric],
    queryFn: () => getTrends({ metric }),
  })

  // Build scatter data: sentiment vs political lean, colored by source
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

  // Group analyzed articles by source for average bias display
  const bySource = {}
  ;(articles || []).forEach(a => {
    if (a.political_lean == null) return
    if (!bySource[a.source_name]) bySource[a.source_name] = { sum: 0, count: 0 }
    bySource[a.source_name].sum += a.political_lean
    bySource[a.source_name].count++
  })
  const sourceSummary = Object.entries(bySource)
    .map(([name, v]) => ({ name, avg: v.sum / v.count, count: v.count }))
    .sort((a, b) => a.avg - b.avg)

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Bias Analysis</h1>
        <p className="text-gray-400 text-sm mt-1">Compare political lean and sentiment across sources</p>
      </div>

      {/* Per-source average bias */}
      <div className="card">
        <h2 className="font-semibold text-white mb-4">Average Political Lean by Source (from Analysis)</h2>
        {sourceSummary.length > 0 ? (
          <div className="space-y-2">
            <div className="flex justify-between text-xs text-gray-600 px-44 pr-16 mb-2">
              <span>◄ Left</span>
              <span>Neutral</span>
              <span>Right ►</span>
            </div>
            {sourceSummary.map(s => (
              <BiasBar key={s.name} label={`${s.name} (${s.count})`} value={s.avg} />
            ))}
          </div>
        ) : (
          <p className="text-gray-600 text-sm">
            No analyzed articles yet. Go to Dashboard → Analyze All, then wait for Ollama to process them.
          </p>
        )}
      </div>

      {/* Scatter: political lean vs sentiment */}
      <div className="card">
        <h2 className="font-semibold text-white mb-4">Political Lean vs. Sentiment</h2>
        {scatterData.length > 0 ? (
          <ResponsiveContainer width="100%" height={300}>
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
                return <circle cx={cx} cy={cy} r={6} fill={payload.color} fillOpacity={0.8} stroke="none" />
              }} />
            </ScatterChart>
          </ResponsiveContainer>
        ) : (
          <p className="text-gray-600 text-sm">Analyze some articles first to see this chart.</p>
        )}
      </div>

      {/* Article list with bias */}
      <div className="card">
        <h2 className="font-semibold text-white mb-4">All Articles — Political Lean</h2>
        <div className="space-y-1">
          {(articles || [])
            .filter(a => a.political_lean != null)
            .sort((a, b) => a.political_lean - b.political_lean)
            .map(a => (
              <Link key={a.id} to={`/articles/${a.id}`} className="flex items-center gap-3 py-1 hover:bg-gray-800/30 rounded px-2">
                <BiasBar
                  label={`${a.source_name || '?'} — ${a.title?.slice(0, 50)}`}
                  value={a.political_lean}
                  confidence={null}
                />
              </Link>
            ))}
          {!(articles || []).some(a => a.political_lean != null) && (
            <p className="text-gray-600 text-sm">No analyzed articles yet.</p>
          )}
        </div>
      </div>
    </div>
  )
}
