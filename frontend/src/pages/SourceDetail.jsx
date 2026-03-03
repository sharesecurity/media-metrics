import { useQuery } from '@tanstack/react-query'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, Globe, Newspaper, Users, BarChart2 } from 'lucide-react'
import { getSource } from '../utils/api'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'

function LeanBadge({ value, large = false }) {
  if (value == null) return <span className="text-gray-500">—</span>
  const color = value < -0.2 ? '#3b82f6' : value > 0.2 ? '#ef4444' : '#22c55e'
  const cls = large ? 'text-3xl font-bold' : 'text-sm font-mono font-medium'
  return (
    <span className={cls} style={{ color }}>
      {value > 0 ? '+' : ''}{value.toFixed(2)}
    </span>
  )
}

function StatCard({ label, value, sub, color = 'text-white' }) {
  return (
    <div className="card text-center">
      <p className="text-xs text-gray-500 uppercase tracking-wider">{label}</p>
      <p className={`text-3xl font-bold mt-1 ${color}`}>{value ?? '—'}</p>
      {sub && <p className="text-xs text-gray-500 mt-0.5">{sub}</p>}
    </div>
  )
}

function LeanBar({ value }) {
  if (value == null) return null
  const pct = ((value + 1) / 2) * 100
  const color = value < -0.2 ? '#3b82f6' : value > 0.2 ? '#ef4444' : '#22c55e'
  return (
    <div className="flex items-center gap-2 mt-2">
      <span className="text-xs text-gray-500 w-16 text-right">Far Left</span>
      <div className="flex-1 h-2 bg-gray-800 rounded-full relative">
        <div
          className="absolute top-0 bottom-0 w-0.5 bg-gray-600"
          style={{ left: '50%' }}
        />
        <div
          className="absolute top-1/2 -translate-y-1/2 w-4 h-4 rounded-full border-2 border-white shadow-lg"
          style={{ left: `calc(${pct}% - 8px)`, backgroundColor: color }}
        />
      </div>
      <span className="text-xs text-gray-500 w-16">Far Right</span>
    </div>
  )
}

export default function SourceDetail() {
  const { id } = useParams()

  const { data: source, isLoading } = useQuery({
    queryKey: ['source', id],
    queryFn: () => getSource(id),
  })

  if (isLoading) return <div className="p-6 text-gray-400">Loading...</div>
  if (!source) return <div className="p-6 text-red-400">Source not found</div>

  const { stats, top_authors = [], recent_articles = [] } = source
  const scrapeRate = stats?.scrape_rate != null ? `${(stats.scrape_rate * 100).toFixed(0)}%` : '—'
  const analysisRate = stats?.analysis_rate != null ? `${(stats.analysis_rate * 100).toFixed(0)}%` : '—'

  // Prepare lean histogram data from recent articles
  const leanBuckets = { 'Far Left\n(<-0.5)': 0, 'Left\n(-0.5–-0.2)': 0, 'Center\n(-0.2–0.2)': 0, 'Right\n(0.2–0.5)': 0, 'Far Right\n(>0.5)': 0 }
  for (const a of recent_articles) {
    if (a.political_lean == null) continue
    const v = a.political_lean
    if (v < -0.5) leanBuckets['Far Left\n(<-0.5)']++
    else if (v < -0.2) leanBuckets['Left\n(-0.5–-0.2)']++
    else if (v <= 0.2) leanBuckets['Center\n(-0.2–0.2)']++
    else if (v <= 0.5) leanBuckets['Right\n(0.2–0.5)']++
    else leanBuckets['Far Right\n(>0.5)']++
  }
  const histData = Object.entries(leanBuckets).map(([name, count]) => ({ name, count }))
  const histColors = ['#3b82f6', '#60a5fa', '#22c55e', '#f87171', '#ef4444']

  return (
    <div className="p-6 space-y-6 max-w-5xl">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Link to="/bias" className="text-gray-500 hover:text-gray-300">
          <ArrowLeft size={18} />
        </Link>
        <Globe size={20} className="text-blue-400" />
        <h1 className="text-xl font-bold text-white">{source.name}</h1>
        {source.domain && (
          <a
            href={`https://${source.domain}`}
            target="_blank"
            rel="noreferrer"
            className="text-xs text-gray-500 hover:text-blue-400 flex items-center gap-1"
          >
            {source.domain}
          </a>
        )}
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-5 gap-4">
        <StatCard label="Total Articles" value={stats?.total?.toLocaleString()} />
        <StatCard
          label="Scraped"
          value={stats?.scraped?.toLocaleString()}
          sub={`${scrapeRate} success rate`}
          color={parseFloat(scrapeRate) > 50 ? 'text-green-400' : 'text-yellow-400'}
        />
        <StatCard
          label="Failed Scrapes"
          value={stats?.scrape_failed}
          color={stats?.scrape_failed > 0 ? 'text-red-400' : 'text-green-400'}
        />
        <StatCard
          label="Analyzed"
          value={stats?.analyzed}
          sub={`${analysisRate} of scraped`}
        />
        <div className="card text-center">
          <p className="text-xs text-gray-500 uppercase tracking-wider">Avg Political Lean</p>
          <div className="mt-2">
            <LeanBadge value={source.avg_lean} large />
          </div>
          {source.political_lean != null && (
            <p className="text-xs text-gray-600 mt-1">baseline: {source.political_lean > 0 ? '+' : ''}{source.political_lean?.toFixed(2)}</p>
          )}
        </div>
      </div>

      {/* Lean gauge */}
      {source.avg_lean != null && (
        <div className="card">
          <h2 className="text-sm font-medium text-gray-400 mb-1">Political Lean Position</h2>
          <LeanBar value={source.avg_lean} />
          <div className="flex justify-between text-xs text-gray-600 mt-2">
            <span>−1.0</span>
            <span>−0.5</span>
            <span>0.0 (center)</span>
            <span>+0.5</span>
            <span>+1.0</span>
          </div>
        </div>
      )}

      <div className="grid grid-cols-2 gap-6">
        {/* Lean histogram */}
        {recent_articles.some(a => a.political_lean != null) && (
          <div className="card">
            <div className="flex items-center gap-2 mb-4">
              <BarChart2 size={16} className="text-gray-400" />
              <h2 className="font-semibold text-white">Lean Distribution</h2>
              <span className="text-xs text-gray-500">(recent {recent_articles.filter(a => a.political_lean != null).length} analyzed)</span>
            </div>
            <ResponsiveContainer width="100%" height={160}>
              <BarChart data={histData} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
                <XAxis dataKey="name" tick={{ fill: '#6b7280', fontSize: 9 }} />
                <YAxis tick={{ fill: '#6b7280', fontSize: 10 }} />
                <Tooltip
                  contentStyle={{ background: '#111827', border: '1px solid #374151', borderRadius: 8 }}
                  labelStyle={{ color: '#f9fafb' }}
                />
                <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                  {histData.map((_, i) => <Cell key={i} fill={histColors[i]} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* Top authors */}
        {top_authors.length > 0 && (
          <div className="card">
            <div className="flex items-center gap-2 mb-4">
              <Users size={16} className="text-gray-400" />
              <h2 className="font-semibold text-white">Top Authors</h2>
            </div>
            <div className="space-y-2">
              {top_authors.map(a => (
                <div key={a.id} className="flex items-center justify-between text-sm">
                  <Link to={`/authors/${a.id}`} className="text-white hover:text-blue-400 truncate flex-1">
                    {a.name}
                  </Link>
                  <span className="text-gray-500 text-xs ml-3 shrink-0">
                    {a.article_count} article{a.article_count !== 1 ? 's' : ''}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Recent articles */}
      {recent_articles.length > 0 && (
        <div className="card p-0 overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-800 flex items-center gap-2">
            <Newspaper size={16} className="text-gray-400" />
            <h2 className="font-semibold text-white">Recent Articles</h2>
            <span className="text-xs text-gray-500">({recent_articles.length} shown)</span>
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800">
                {['Title', 'Author', 'Date', 'Lean', 'Words'].map(h => (
                  <th key={h} className="text-left text-xs text-gray-500 uppercase tracking-wider px-4 py-2 font-medium">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {recent_articles.map(a => (
                <tr key={a.id} className="border-b border-gray-800/50 hover:bg-gray-800/30 transition-colors">
                  <td className="px-4 py-2 max-w-xs">
                    <Link to={`/articles/${a.id}`} className="text-white hover:text-blue-400 line-clamp-1 text-xs">
                      {a.title}
                    </Link>
                  </td>
                  <td className="px-4 py-2 text-gray-500 text-xs whitespace-nowrap">{a.author_name || '—'}</td>
                  <td className="px-4 py-2 text-gray-600 text-xs whitespace-nowrap">
                    {a.published_at ? new Date(a.published_at).toLocaleDateString() : '—'}
                  </td>
                  <td className="px-4 py-2">
                    <LeanBadge value={a.political_lean} />
                  </td>
                  <td className="px-4 py-2 text-gray-600 text-xs">{a.word_count ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
