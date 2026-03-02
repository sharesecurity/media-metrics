import { useQuery } from '@tanstack/react-query'
import { getArticles, getSources, searchArticles } from '../utils/api'
import { Link } from 'react-router-dom'
import { useState } from 'react'
import { Search, ExternalLink } from 'lucide-react'

const BiasBar = ({ value }) => {
  if (value == null) return <span className="text-xs text-gray-600">not analyzed</span>
  const pct = ((value + 1) / 2) * 100
  const color = value < -0.2 ? '#3b82f6' : value > 0.2 ? '#ef4444' : '#22c55e'
  const label = value < -0.3 ? 'Left' : value > 0.3 ? 'Right' : 'Center'
  return (
    <div className="flex items-center gap-2">
      <div className="w-20 h-1.5 bg-gray-800 rounded-full relative">
        <div
          className="absolute top-1/2 -translate-y-1/2 w-2.5 h-2.5 rounded-full border border-white"
          style={{ left: `calc(${pct}% - 5px)`, backgroundColor: color }}
        />
      </div>
      <span className="text-xs" style={{ color }}>{label} ({value > 0 ? '+' : ''}{value.toFixed(2)})</span>
    </div>
  )
}

export default function Articles() {
  const [q, setQ] = useState('')
  const [sourceFilter, setSourceFilter] = useState('')
  const [leanFilter, setLeanFilter] = useState('all') // all | left | center | right
  const [analyzedOnly, setAnalyzedOnly] = useState(false)
  const [debouncedQ, setDebouncedQ] = useState('')

  const { data: sources } = useQuery({ queryKey: ['sources'], queryFn: getSources })
  const { data: articles, isLoading } = useQuery({
    queryKey: ['articles', sourceFilter],
    queryFn: () => getArticles({ source_id: sourceFilter || undefined, limit: 200 }),
  })
  const { data: searchResults } = useQuery({
    queryKey: ['search', debouncedQ],
    queryFn: () => searchArticles(debouncedQ),
    enabled: debouncedQ.length > 2,
  })

  const handleSearch = (val) => {
    setQ(val)
    clearTimeout(window._searchTimer)
    window._searchTimer = setTimeout(() => setDebouncedQ(val), 400)
  }

  const baseArticles = debouncedQ.length > 2 ? searchResults : articles
  const displayArticles = (baseArticles || []).filter(a => {
    if (analyzedOnly && a.political_lean == null) return false
    if (leanFilter === 'left' && (a.political_lean == null || a.political_lean >= -0.2)) return false
    if (leanFilter === 'center' && (a.political_lean == null || a.political_lean < -0.2 || a.political_lean > 0.2)) return false
    if (leanFilter === 'right' && (a.political_lean == null || a.political_lean <= 0.2)) return false
    return true
  })

  const sentimentColor = (s) => {
    if (s == null) return 'text-gray-600'
    if (s > 0.05) return 'text-green-400'
    if (s < -0.05) return 'text-red-400'
    return 'text-yellow-400'
  }

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">Articles</h1>
        <span className="text-sm text-gray-500">
          {displayArticles.length} {(leanFilter !== 'all' || analyzedOnly) ? `of ${baseArticles?.length ?? 0} ` : ''}articles
        </span>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <div className="relative flex-1 min-w-48">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
          <input
            type="text"
            placeholder="Search articles..."
            value={q}
            onChange={e => handleSearch(e.target.value)}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg pl-9 pr-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
          />
        </div>
        <select
          value={sourceFilter}
          onChange={e => setSourceFilter(e.target.value)}
          className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
        >
          <option value="">All Sources</option>
          {(sources || []).map(s => (
            <option key={s.id} value={s.id}>{s.name}</option>
          ))}
        </select>
        <div className="flex rounded-lg overflow-hidden border border-gray-700 text-sm">
          {[['all','All Lean'],['left','Left'],['center','Center'],['right','Right']].map(([val, label]) => (
            <button
              key={val}
              onClick={() => setLeanFilter(val)}
              className={`px-3 py-2 transition-colors ${leanFilter === val ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'}`}
            >
              {label}
            </button>
          ))}
        </div>
        <button
          onClick={() => setAnalyzedOnly(v => !v)}
          className={`px-3 py-2 rounded-lg border text-sm transition-colors ${analyzedOnly ? 'bg-blue-600 border-blue-500 text-white' : 'bg-gray-800 border-gray-700 text-gray-400 hover:bg-gray-700'}`}
        >
          Analyzed only
        </button>
      </div>

      {/* Table */}
      <div className="card p-0 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800">
              {['Title', 'Source', 'Author', 'Published', 'Sentiment', 'Political Lean', ''].map(h => (
                <th key={h} className="text-left text-xs text-gray-500 uppercase tracking-wider px-4 py-3 font-medium">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr><td colSpan={7} className="text-center py-12 text-gray-600">Loading...</td></tr>
            )}
            {!isLoading && !displayArticles?.length && (
              <tr><td colSpan={7} className="text-center py-12 text-gray-600">
                No articles yet. Go to Dashboard and click "Ingest Articles".
              </td></tr>
            )}
            {(displayArticles || []).map(a => (
              <tr key={a.id} className="border-b border-gray-800/50 hover:bg-gray-800/30 transition-colors">
                <td className="px-4 py-3 max-w-xs">
                  <Link to={`/articles/${a.id}`} className="text-white hover:text-blue-400 line-clamp-2">
                    {a.title}
                  </Link>
                </td>
                <td className="px-4 py-3 text-gray-400 whitespace-nowrap">{a.source_name || '—'}</td>
                <td className="px-4 py-3 text-gray-500 text-xs max-w-[120px] truncate" title={a.author_name || ''}>
                  {a.author_name || <span className="text-gray-700">—</span>}
                </td>
                <td className="px-4 py-3 text-gray-500 whitespace-nowrap text-xs">
                  {a.published_at ? new Date(a.published_at).toLocaleDateString() : '—'}
                </td>
                <td className="px-4 py-3">
                  <span className={`text-xs ${sentimentColor(a.sentiment_score)}`}>
                    {a.sentiment_score != null
                      ? (a.sentiment_score > 0.05 ? '▲ Positive' : a.sentiment_score < -0.05 ? '▼ Negative' : '● Neutral')
                      : '—'
                    }
                  </span>
                </td>
                <td className="px-4 py-3 min-w-[160px]">
                  <BiasBar value={a.political_lean} />
                </td>
                <td className="px-4 py-3">
                  {a.url && (
                    <a href={a.url} target="_blank" rel="noreferrer"
                      className="text-gray-600 hover:text-gray-400">
                      <ExternalLink size={13} />
                    </a>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
