import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Search, AlertCircle, Zap, Hash } from 'lucide-react'

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

const getColor = (name) => SOURCE_COLORS[name] || '#9ca3af'

const EXAMPLES = [
  'climate change legislation',
  'immigration border security',
  'healthcare drug prices',
  'gun control background checks',
  'government spending deficit',
  'artificial intelligence regulation',
  'Supreme Court decision',
]

function LeanBadge({ value }) {
  if (value == null) return null
  const color = value < -0.3 ? '#3b82f6' : value > 0.3 ? '#ef4444' : '#22c55e'
  const label = value < -0.3 ? 'Left' : value > 0.3 ? 'Right' : 'Center'
  return (
    <span className="text-xs px-1.5 py-0.5 rounded font-medium" style={{ color, background: `${color}22` }}>
      {label} ({value > 0 ? '+' : ''}{value.toFixed(2)})
    </span>
  )
}

function ScoreBadge({ score }) {
  if (score == null) return null
  const pct = Math.round(score * 100)
  const color = pct > 80 ? '#22c55e' : pct > 60 ? '#f59e0b' : '#9ca3af'
  return (
    <span className="text-xs px-1.5 py-0.5 rounded" style={{ color, background: `${color}22` }}>
      {pct}% match
    </span>
  )
}

export default function SemanticSearch() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState(null)
  const [method, setMethod] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const runSearch = async (q) => {
    const trimmed = (q || query).trim()
    if (!trimmed) return
    setLoading(true)
    setError(null)
    setResults(null)
    try {
      const resp = await fetch(`/api/search/semantic?q=${encodeURIComponent(trimmed)}&limit=15`)
      if (!resp.ok) throw new Error(`Server error ${resp.status}`)
      const data = await resp.json()
      setResults(data.results || [])
      setMethod(data.method)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    runSearch()
  }

  const handleExample = (ex) => {
    setQuery(ex)
    runSearch(ex)
  }

  return (
    <div className="p-6 space-y-6 max-w-3xl mx-auto">
      <div>
        <h1 className="text-2xl font-bold text-white flex items-center gap-2">
          <Zap size={22} className="text-blue-400" />
          Semantic Search
        </h1>
        <p className="text-gray-400 text-sm mt-1">
          Find articles by meaning, not just keywords. Powered by nomic-embed-text vector search.
        </p>
      </div>

      {/* Search box */}
      <form onSubmit={handleSubmit} className="flex gap-2">
        <div className="flex-1 relative">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
          <input
            type="text"
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="Describe what you're looking for…"
            className="w-full bg-gray-800 border border-gray-700 rounded-lg pl-9 pr-3 py-2.5 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
          />
        </div>
        <button
          type="submit"
          disabled={loading || !query.trim()}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm rounded-lg font-medium transition-colors"
        >
          {loading ? 'Searching…' : 'Search'}
        </button>
      </form>

      {/* Example queries */}
      <div>
        <p className="text-xs text-gray-600 mb-2">Try:</p>
        <div className="flex flex-wrap gap-2">
          {EXAMPLES.map(ex => (
            <button
              key={ex}
              onClick={() => handleExample(ex)}
              className="text-xs px-2.5 py-1 rounded-full bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-white border border-gray-700 transition-colors"
            >
              {ex}
            </button>
          ))}
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="flex items-center gap-2 text-red-400 text-sm bg-red-900/20 border border-red-900/50 rounded-lg p-3">
          <AlertCircle size={15} />
          {error}
        </div>
      )}

      {/* Results */}
      {results !== null && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold text-white">
              {results.length} result{results.length !== 1 ? 's' : ''}
            </h2>
            <span className={`text-xs px-2 py-0.5 rounded flex items-center gap-1 ${
              method === 'semantic'
                ? 'bg-blue-900/30 text-blue-400'
                : 'bg-gray-800 text-gray-500'
            }`}>
              {method === 'semantic' ? <Zap size={11} /> : <Hash size={11} />}
              {method === 'semantic' ? 'Vector search' : 'Keyword fallback'}
            </span>
          </div>

          {results.length === 0 && (
            <p className="text-gray-600 text-sm">
              No results found. Try a different query, or make sure articles have been analyzed
              (analysis generates the embeddings used for semantic search).
            </p>
          )}

          {results.map((r, i) => (
            <Link
              key={r.id || i}
              to={r.id ? `/articles/${r.id}` : '#'}
              className="block card hover:border-gray-600 transition-colors"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <p className="text-white text-sm font-medium leading-snug">{r.title}</p>
                  <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                    <span
                      className="text-xs font-medium"
                      style={{ color: getColor(r.source_name) }}
                    >
                      {r.source_name}
                    </span>
                    {r.published_at && (
                      <span className="text-xs text-gray-600">
                        {new Date(r.published_at).toLocaleDateString('en-US', {
                          month: 'short', day: 'numeric', year: 'numeric'
                        })}
                      </span>
                    )}
                    {r.section && (
                      <span className="text-xs text-gray-600 bg-gray-800 px-1.5 py-0.5 rounded">
                        {r.section}
                      </span>
                    )}
                    {r.primary_topic && (
                      <span className="text-xs text-gray-500">{r.primary_topic}</span>
                    )}
                  </div>
                </div>
                <div className="flex flex-col items-end gap-1 shrink-0">
                  <ScoreBadge score={r.score} />
                  <LeanBadge value={r.political_lean} />
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}

      {/* Explanation when no search yet */}
      {results === null && !loading && (
        <div className="card border-dashed">
          <h3 className="text-sm font-medium text-gray-400 mb-2">How it works</h3>
          <ul className="text-xs text-gray-600 space-y-1.5 list-none">
            <li className="flex items-start gap-2">
              <span className="text-blue-500 mt-0.5">1.</span>
              Your query is converted to a 768-dimension embedding using nomic-embed-text via Ollama
            </li>
            <li className="flex items-start gap-2">
              <span className="text-blue-500 mt-0.5">2.</span>
              Qdrant finds articles with the most similar embeddings using cosine similarity
            </li>
            <li className="flex items-start gap-2">
              <span className="text-blue-500 mt-0.5">3.</span>
              Articles must be analyzed first — analysis generates and stores their embeddings
            </li>
            <li className="flex items-start gap-2">
              <span className="text-yellow-500 mt-0.5">!</span>
              If Qdrant is unavailable, falls back to keyword search automatically
            </li>
          </ul>
        </div>
      )}
    </div>
  )
}
