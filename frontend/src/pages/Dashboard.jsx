import { useQuery } from '@tanstack/react-query'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import { getArticleStats, getSources, startIngest, runAllAnalysis, getAuthors, getIngestStatus, getQueueStats } from '../utils/api'
import { Play, Database, FileText, Users, RefreshCw, Globe, Cpu, Activity } from 'lucide-react'
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
  const [scraping, setScraping] = useState(false)
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
  const { data: authors = [] } = useQuery({
    queryKey: ['authors'],
    queryFn: getAuthors,
  })

  const { data: ingestStatus } = useQuery({
    queryKey: ['ingest-status'],
    queryFn: getIngestStatus,
    refetchInterval: (data) => (data?.scraper?.running ? 3000 : 15000),
  })

  const { data: queueStats } = useQuery({
    queryKey: ['queue-stats'],
    queryFn: getQueueStats,
    refetchInterval: 10000,
  })

  const handleIngest = async () => {
    setIngesting(true)
    setMsg('Fetching live articles from RSS feeds across 10 major outlets (auto-analysis enabled)...')
    try {
      await startIngest('rss', 15, null, true)
      setMsg('RSS ingest + auto-analysis started! Articles from NYT, Fox, Reuters, AP, BBC & more are being fetched and analyzed automatically. Check back in a few minutes.')
      setTimeout(() => refetchStats(), 8000)
      setTimeout(() => refetchStats(), 30000)
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

  const handleScrape = async () => {
    setScraping(true)
    setMsg('Scraping full text for articles missing content (auto-analysis enabled)...')
    try {
      const res = await startIngest('scrape', 50, null, true)
      setMsg(`Scraping started for up to ${res.limit} articles. Titles and text will be extracted, then bias analysis will run automatically.`)
      setTimeout(() => refetchStats(), 15000)
      setTimeout(() => refetchStats(), 45000)
    } catch (e) {
      setMsg('Scrape failed: ' + e.message)
    }
    setScraping(false)
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
            onClick={handleScrape}
            disabled={scraping || ingesting}
            className="btn-ghost border border-gray-700 flex items-center gap-2 text-sm"
            title="Scrape full text for articles missing content"
          >
            <RefreshCw size={14} className={scraping ? 'animate-spin' : ''} />
            {scraping ? 'Scraping...' : 'Scrape Text'}
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

      {/* Pipeline status panel */}
      {(ingestStatus && (ingestStatus.scraper?.running || ingestStatus.scraper?.needs_scrape > 0 || ingestStatus.analysis?.needs_analysis > 0)) || (queueStats && (queueStats.active > 0 || queueStats.queued > 0 || queueStats.workers?.length > 0)) ? (
        <div className="bg-gray-900 border border-gray-700 rounded-xl p-4">
          <h3 className="text-xs text-gray-500 uppercase tracking-wider mb-3">Pipeline Status</h3>
          <div className="flex gap-6">
            <div className="flex items-center gap-3">
              <Globe size={16} className={ingestStatus?.scraper?.running ? 'text-blue-400 animate-pulse' : 'text-gray-600'} />
              <div>
                <p className="text-xs text-gray-500">Scraper</p>
                {ingestStatus?.scraper?.running ? (
                  <p className="text-sm text-blue-300 font-medium">
                    Running — {ingestStatus.scraper.scraped}/{ingestStatus.scraper.total} done
                    {ingestStatus.scraper.failed > 0 && <span className="text-gray-500 ml-1">({ingestStatus.scraper.failed} failed)</span>}
                  </p>
                ) : (
                  <p className="text-sm text-gray-400">
                    {ingestStatus?.scraper?.needs_scrape > 0
                      ? <span className="text-yellow-400">{ingestStatus.scraper.needs_scrape} articles need scraping</span>
                      : <span className="text-green-400">All articles scraped</span>}
                    {ingestStatus?.scraper?.scraped > 0 && !ingestStatus.scraper.running && (
                      <span className="text-gray-600 ml-2 text-xs">
                        Last run: {ingestStatus.scraper.scraped} scraped
                      </span>
                    )}
                  </p>
                )}
              </div>
            </div>
            <div className="flex items-center gap-3 border-l border-gray-800 pl-6">
              <Cpu size={16} className={ingestStatus?.analysis?.needs_analysis > 0 ? 'text-purple-400 animate-pulse' : 'text-gray-600'} />
              <div>
                <p className="text-xs text-gray-500">Analysis Queue</p>
                {ingestStatus?.analysis?.needs_analysis > 0 ? (
                  <p className="text-sm text-purple-300 font-medium">
                    {ingestStatus.analysis.needs_analysis} articles pending analysis
                  </p>
                ) : (
                  <p className="text-sm text-green-400">All articles analyzed</p>
                )}
              </div>
            </div>
            {queueStats && (
              <div className="flex items-center gap-3 border-l border-gray-800 pl-6">
                <Activity size={16} className={queueStats.active > 0 ? 'text-green-400 animate-pulse' : 'text-gray-600'} />
                <div>
                  <p className="text-xs text-gray-500">Celery Workers</p>
                  {queueStats.workers?.length > 0 ? (
                    <p className="text-sm text-green-300 font-medium">
                      {queueStats.workers.length} worker{queueStats.workers.length !== 1 ? 's' : ''}
                      {' · '}
                      {queueStats.active > 0
                        ? <span className="text-yellow-300">{queueStats.active} running</span>
                        : <span className="text-gray-400">idle</span>}
                      {queueStats.queued > 0 && <span className="text-gray-400 ml-1">· {queueStats.queued} queued</span>}
                    </p>
                  ) : (
                    <p className="text-sm text-gray-600">No workers connected</p>
                  )}
                </div>
              </div>
            )}
          </div>
          {ingestStatus?.scraper?.running && ingestStatus.scraper.total > 0 && (
            <div className="mt-3">
              <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-blue-500 rounded-full transition-all duration-500"
                  style={{ width: `${(ingestStatus.scraper.scraped / ingestStatus.scraper.total) * 100}%` }}
                />
              </div>
            </div>
          )}
        </div>
      ) : null}

      {/* Stats cards */}
      <div className="grid grid-cols-4 gap-4">
        {[
          { label: 'Total Articles', value: stats?.total_articles ?? '—' },
          {
            label: 'Analyzed',
            value: stats?.analyzed_articles ?? '—',
            sub: stats?.total_articles
              ? `${((stats.analyzed_articles / stats.total_articles) * 100).toFixed(0)}%`
              : null,
          },
          { label: 'News Sources', value: sources?.length ?? '—' },
          { label: 'Authors', value: authors.length || '—', icon: Users },
        ].map(({ label, value, sub }) => (
          <div key={label} className="card">
            <p className="text-gray-500 text-xs uppercase tracking-wider">{label}</p>
            <p className="text-3xl font-bold text-white mt-1">{value}</p>
            {sub && <p className="text-xs text-gray-500 mt-0.5">{sub} analyzed</p>}
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
