import { useQuery } from '@tanstack/react-query'
import { getArticles, getArticleCount, getSources, searchArticles } from '../utils/api'
import { Link } from 'react-router-dom'
import { useState } from 'react'
import { Search, ExternalLink, ChevronLeft, ChevronRight } from 'lucide-react'

const PAGE_SIZE = 100

// lean range → [lean_min, lean_max] params
const LEAN_RANGES = {
  all:    [undefined, undefined],
  left:   [undefined, -0.2],
  center: [-0.2, 0.2],
  right:  [0.2, undefined],
}

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
  const [leanFilter, setLeanFilter] = useState('all')
  const [analyzedOnly, setAnalyzedOnly] = useState(false)
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [debouncedQ, setDebouncedQ] = useState('')
  const [page, setPage] = useState(0)

  const { data: sources } = useQuery({ queryKey: ['sources'], queryFn: getSources })

  const [leanMin, leanMax] = LEAN_RANGES[leanFilter]
  const filterParams = {
    source_id: sourceFilter || undefined,
    analyzed_only: analyzedOnly || undefined,
    lean_min: leanMin,
    lean_max: leanMax,
    date_from: dateFrom || undefined,
    date_to: dateTo || undefined,
  }

  const { data: countData } = useQuery({
    queryKey: ['articles-count', filterParams],
    queryFn: () => getArticleCount(filterParams),
    staleTime: 15000,
  })
  const { data: articles, isLoading } = useQuery({
    queryKey: ['articles', filterParams, page],
    queryFn: () => getArticles({ ...filterParams, skip: page * PAGE_SIZE, limit: PAGE_SIZE }),
    keepPreviousData: true,
  })
  const { data: searchResults } = useQuery({
    queryKey: ['search', debouncedQ],
    queryFn: () => searchArticles(debouncedQ),
    enabled: debouncedQ.length > 2,
  })

  const isSearching = debouncedQ.length > 2

  const handleSearch = (val) => {
    setQ(val)
    clearTimeout(window._searchTimer)
    window._searchTimer = setTimeout(() => setDebouncedQ(val), 400)
  }

  const resetPage = () => setPage(0)

  const displayArticles = isSearching ? (searchResults || []) : (articles || [])

  const totalArticles = countData?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(totalArticles / PAGE_SIZE))

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
          {isSearching
            ? `${displayArticles.length} search results`
            : `${totalArticles.toLocaleString()} articles`
          }
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
          onChange={e => { setSourceFilter(e.target.value); resetPage() }}
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
              onClick={() => { setLeanFilter(val); resetPage() }}
              className={`px-3 py-2 transition-colors ${leanFilter === val ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'}`}
            >
              {label}
            </button>
          ))}
        </div>
        <button
          onClick={() => { setAnalyzedOnly(v => !v); resetPage() }}
          className={`px-3 py-2 rounded-lg border text-sm transition-colors ${analyzedOnly ? 'bg-blue-600 border-blue-500 text-white' : 'bg-gray-800 border-gray-700 text-gray-400 hover:bg-gray-700'}`}
        >
          Analyzed only
        </button>
      </div>
      <div className="flex items-center gap-2 text-sm">
        <span className="text-gray-500 text-xs">Date:</span>
        <input
          type="date"
          value={dateFrom}
          onChange={e => { setDateFrom(e.target.value); resetPage() }}
          className="bg-gray-800 border border-gray-700 rounded-lg px-2 py-1.5 text-xs text-white focus:outline-none focus:border-blue-500"
          title="From date"
        />
        <span className="text-gray-600">–</span>
        <input
          type="date"
          value={dateTo}
          onChange={e => { setDateTo(e.target.value); resetPage() }}
          className="bg-gray-800 border border-gray-700 rounded-lg px-2 py-1.5 text-xs text-white focus:outline-none focus:border-blue-500"
          title="To date"
        />
        {(dateFrom || dateTo) && (
          <button
            onClick={() => { setDateFrom(''); setDateTo(''); resetPage() }}
            className="text-gray-500 hover:text-gray-300 text-xs px-1"
            title="Clear date filter"
          >
            ✕
          </button>
        )}
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

        {/* Pagination footer */}
        {!isSearching && totalPages > 1 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-gray-800">
            <span className="text-xs text-gray-500">
              Page {page + 1} of {totalPages} · {totalArticles.toLocaleString()} total
            </span>
            <div className="flex items-center gap-2">
              <button
                disabled={page === 0}
                onClick={() => setPage(p => p - 1)}
                className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-gray-800 text-sm text-gray-400 hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                <ChevronLeft size={14} /> Prev
              </button>
              <span className="text-xs text-gray-600 w-20 text-center">
                {(page * PAGE_SIZE + 1).toLocaleString()}–{Math.min((page + 1) * PAGE_SIZE, totalArticles).toLocaleString()}
              </span>
              <button
                disabled={page >= totalPages - 1}
                onClick={() => setPage(p => p + 1)}
                className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-gray-800 text-sm text-gray-400 hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                Next <ChevronRight size={14} />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
