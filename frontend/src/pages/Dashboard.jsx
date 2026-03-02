import { useQuery } from '@tanstack/react-query'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import { getArticleStats, getSources, startIngest, runAllAnalysis } from '../utils/api'
import { Play, Database, FileText } from 'lucide-react'
import { useState } from 'react'

const BiasGauge = ({ value }) => {
  if (value == null) return <span className="text-gray-500">—</span>
  const pct = ((value + 1) / 2) * 100
  const color = value < -0.2 ? '#3b82f6' : value > 0.2 ? '#ef4444' : '#22c55e'
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-2 bg-gray-800 rounded-full relative">
        <div
          className="absolute top-1/2 -translate-y-1/2 w-3 h-3 rounded-full border-2 border-white"
          style={{ left: `calc(${pct}% - 6px)`, backgroundColor: color }}
        />
      </div>
      <span className="text-xs w-10 text-right" style={{ color }}>
        {value > 0 ? '+' : ''}{value.toFixed(2)}
      </span>
    </div>
  )
}

export default function Dashboard() {
  const [ingesting, setIngesting] = useState(false)
  const [analyzing, setAnalyzing] = useState(false)
  const [msg, setMsg] = useState('')

  const { data: stats, refetch: refetchStats } = useQuery({
    queryKey: ['article-stats'],
    queryFn: getArticleStats,
  })
  const { data: sources } = useQuery({
    queryKey: ['sources'],
    queryFn: getSources,
  })

  const handleIngest = async () => {
    setIngesting(true)
    setMsg('Fetching live articles from RSS feeds across 10 major outlets...')
    try {
      await startIngest('rss', 15)
      setMsg('RSS ingest started! Articles from NYT, Fox, Reuters, AP, BBC & more are being fetched. Refresh in ~30 seconds.')
      setTimeout(() => refetchStats(), 8000)
      setTimeout(() => refetchStats(), 20000)
    } catch (e) {
      setMsg('Ingest failed: ' + e.message)
    }
    setIngesting(false)
  }

  const handleLoadSamples = async () => {
    setIngesting(true)
    setMsg('Loading 48 sample articles across 7 stories and 8 outlets (Jan–Dec 2024)...')
    try {
      await startIngest('embedded', 50)
      setMsg('Sample data loaded! 48 articles across climate, immigration, healthcare, AI regulation, gun control, budget, and SCOTUS stories. Click "Analyze All" to run bias analysis.')
      setTimeout(() => refetchStats(), 2000)
      setTimeout(() => refetchStats(), 5000)
    } catch (e) {
      setMsg('Sample load failed: ' + e.message)
    }
    setIngesting(false)
  }

  const handleAnalyzeAll = async () => {
    setAnalyzing(true)
    setMsg('Queuing analysis for all unanalyzed articles...')
    try {
      const res = await runAllAnalysis()
      setMsg(`Analysis queued for ${res.count} articles. This may take a few minutes.`)
    } catch (e) {
      setMsg('Analysis failed: ' + e.message)
    }
    setAnalyzing(false)
  }

  const chartData = stats?.by_source?.slice(0, 8) || []

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Dashboard</h1>
          <p className="text-gray-400 text-sm mt-1">News bias analysis overview</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={handleLoadSamples}
            disabled={ingesting}
            className="btn-ghost border border-gray-700 flex items-center gap-2 text-sm"
            title="Load 48 sample articles across 7 topics (Jan–Dec 2024)"
          >
            <FileText size={14} />
            {ingesting ? 'Loading...' : 'Load Samples'}
          </button>
          <button
            onClick={handleIngest}
            disabled={ingesting}
            className="btn-primary flex items-center gap-2 text-sm"
            title="Fetch live articles from RSS feeds"
          >
            <Database size={14} />
            {ingesting ? 'Ingesting...' : 'Ingest RSS'}
          </button>
          <button
            onClick={handleAnalyzeAll}
            disabled={analyzing}
            className="btn-ghost border border-gray-700 flex items-center gap-2 text-sm"
          >
            <Play size={14} />
            {analyzing ? 'Queuing...' : 'Analyze All'}
          </button>
        </div>
      </div>

      {msg && (
        <div className="bg-blue-900/30 border border-blue-700 text-blue-300 px-4 py-2 rounded-lg text-sm">
          {msg}
        </div>
      )}

      {/* Stats cards */}
      <div className="grid grid-cols-3 gap-4">
        {[
          { label: 'Total Articles', value: stats?.total_articles ?? '—' },
          { label: 'Analyzed', value: stats?.analyzed_articles ?? '—' },
          { label: 'News Sources', value: sources?.length ?? '—' },
        ].map(({ label, value }) => (
          <div key={label} className="card">
            <p className="text-gray-500 text-xs uppercase tracking-wider">{label}</p>
            <p className="text-3xl font-bold text-white mt-1">{value}</p>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-6">
        {/* Articles by source */}
        <div className="card">
          <h2 className="font-semibold text-white mb-4">Articles by Source</h2>
          {chartData.length > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={chartData} layout="vertical">
                <XAxis type="number" tick={{ fill: '#9ca3af', fontSize: 11 }} />
                <YAxis type="category" dataKey="source" tick={{ fill: '#9ca3af', fontSize: 11 }} width={130} />
                <Tooltip
                  contentStyle={{ background: '#111827', border: '1px solid #374151', borderRadius: 8 }}
                  labelStyle={{ color: '#f9fafb' }}
                />
                <Bar dataKey="count" fill="#3b82f6" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-40 flex items-center justify-center text-gray-600 text-sm">
              No data yet — click "Ingest Articles" to get started
            </div>
          )}
        </div>

        {/* Source bias overview */}
        <div className="card">
          <h2 className="font-semibold text-white mb-4">Source Political Lean (Baseline)</h2>
          <div className="space-y-3">
            {(sources || []).map(s => (
              <div key={s.id} className="flex items-center gap-3">
                <span className="text-sm text-gray-300 w-40 truncate">{s.name}</span>
                <div className="flex-1">
                  <BiasGauge value={s.political_lean} />
                </div>
              </div>
            ))}
            {!sources?.length && (
              <p className="text-gray-600 text-sm">Loading sources...</p>
            )}
          </div>
          <p className="text-xs text-gray-600 mt-3">
            Scale: −1.0 (far left) → 0.0 (neutral) → +1.0 (far right)
          </p>
        </div>
      </div>
    </div>
  )
}
