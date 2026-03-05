import { useQuery } from '@tanstack/react-query'
import { useParams, Link } from 'react-router-dom'
import { Layers, ExternalLink, ArrowLeft, TrendingUp, TrendingDown, Minus } from 'lucide-react'

const LEAN_COLOR = (v) => {
  if (v == null) return '#6b7280'
  if (v < -0.3) return '#3b82f6'
  if (v > 0.3) return '#ef4444'
  return '#22c55e'
}

const LEAN_LABEL = (v) => {
  if (v == null) return '—'
  const s = v > 0 ? '+' : ''
  return `${s}${v.toFixed(2)}`
}

const LeanBadge = ({ value, size = 'sm' }) => {
  if (value == null) return <span className="text-gray-600 text-xs">—</span>
  const color = value < -0.3 ? 'text-blue-400' : value > 0.3 ? 'text-red-400' : 'text-green-400'
  const label = value < -0.3 ? 'Left' : value > 0.3 ? 'Right' : 'Center'
  return (
    <span className={`font-mono text-xs ${color}`}>
      {label} {LEAN_LABEL(value)}
    </span>
  )
}

// Horizontal bar showing position on -1..+1 scale
const LeanBar = ({ value, showLabel = false }) => {
  if (value == null) return <div className="h-4 bg-gray-800 rounded text-xs text-gray-600 flex items-center px-2">no data</div>
  const pct = ((value + 1) / 2) * 100
  return (
    <div className="relative h-4 bg-gray-800 rounded overflow-hidden">
      {/* Center line */}
      <div className="absolute left-1/2 top-0 bottom-0 w-px bg-gray-600 z-10" />
      {/* Filled bar from center */}
      {value < 0 ? (
        <div
          className="absolute top-0 bottom-0 rounded-l"
          style={{ right: '50%', width: `${Math.abs(value) * 50}%`, backgroundColor: '#3b82f6', opacity: 0.75 }}
        />
      ) : (
        <div
          className="absolute top-0 bottom-0 rounded-r"
          style={{ left: '50%', width: `${value * 50}%`, backgroundColor: '#ef4444', opacity: 0.75 }}
        />
      )}
      {showLabel && (
        <span className="absolute inset-0 flex items-center justify-center text-xs font-mono text-white/80 z-20">
          {LEAN_LABEL(value)}
        </span>
      )}
    </div>
  )
}

// Divergence meter: shows spread from min to max across outlets
const DivergenceMeter = ({ divergence, perSource }) => {
  const analyzed = perSource.filter(s => s.avg_lean != null)
  if (!analyzed.length) return null
  const minLean = Math.min(...analyzed.map(s => s.avg_lean))
  const maxLean = Math.max(...analyzed.map(s => s.avg_lean))

  // Divergence color: 0=green, 0.5=yellow, 1+=red
  const div = divergence ?? 0
  const divColor = div < 0.3 ? '#22c55e' : div < 0.6 ? '#eab308' : div < 1.0 ? '#f97316' : '#ef4444'
  const divLabel = div < 0.3 ? 'Low' : div < 0.6 ? 'Moderate' : div < 1.0 ? 'High' : 'Extreme'

  return (
    <div className="card p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-white">Bias Divergence</h3>
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-500">spread across outlets:</span>
          <span className="text-sm font-mono font-bold" style={{ color: divColor }}>
            {divergence != null ? divergence.toFixed(2) : '—'}
          </span>
          <span className="text-xs px-2 py-0.5 rounded-full text-white" style={{ backgroundColor: divColor + '33', color: divColor }}>
            {divLabel}
          </span>
        </div>
      </div>

      {/* Full scale bar showing outlet positions */}
      <div className="relative h-6">
        {/* Background track */}
        <div className="absolute inset-y-1 inset-x-0 bg-gradient-to-r from-blue-900/50 via-gray-800 to-red-900/50 rounded" />
        {/* Center line */}
        <div className="absolute left-1/2 inset-y-0 w-0.5 bg-gray-600" />
        {/* Range bracket */}
        {analyzed.length >= 2 && (
          <div
            className="absolute inset-y-1 rounded opacity-20"
            style={{
              left: `${((minLean + 1) / 2) * 100}%`,
              width: `${((maxLean - minLean) / 2) * 100}%`,
              backgroundColor: divColor,
            }}
          />
        )}
        {/* Outlet dots */}
        {analyzed.map(s => (
          <div
            key={s.source_name}
            title={`${s.source_name}: ${LEAN_LABEL(s.avg_lean)}`}
            className="absolute top-1/2 -translate-y-1/2 w-2.5 h-2.5 rounded-full border-2 border-gray-900 cursor-help z-10"
            style={{ left: `${((s.avg_lean + 1) / 2) * 100}%`, marginLeft: '-5px', backgroundColor: LEAN_COLOR(s.avg_lean) }}
          />
        ))}
        {/* Labels */}
        <div className="absolute -bottom-5 left-0 text-xs text-gray-600">Far Left</div>
        <div className="absolute -bottom-5 left-1/2 -translate-x-1/2 text-xs text-gray-600">Center</div>
        <div className="absolute -bottom-5 right-0 text-xs text-gray-600">Far Right</div>
      </div>
      <div className="h-5" />
    </div>
  )
}

export default function ClusterDetail() {
  const { id } = useParams()

  const { data, isLoading, error } = useQuery({
    queryKey: ['cluster', id],
    queryFn: () => fetch(`/api/clusters/${id}`).then(r => {
      if (!r.ok) throw new Error('Not found')
      return r.json()
    }),
    staleTime: 60000,
  })

  if (isLoading) return (
    <div className="p-6 flex items-center gap-2 text-gray-500">
      <Layers size={16} className="animate-pulse" /> Loading cluster…
    </div>
  )
  if (error || !data) return (
    <div className="p-6 text-red-400">Cluster not found.</div>
  )

  const {
    topic_label, article_count, source_count, avg_lean, avg_sentiment,
    date_start, date_end, per_source = [], bias_divergence, articles = []
  } = data

  const dateRange = (() => {
    if (!date_start && !date_end) return null
    const fmt = (d) => d ? new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '?'
    if (date_start && date_end) {
      const s = new Date(date_start), e = new Date(date_end)
      if (Math.abs(s - e) < 86400000 * 2) return fmt(date_end)
      return `${fmt(date_start)} – ${fmt(date_end)}`
    }
    return fmt(date_end || date_start)
  })()

  // Sort articles by political lean (left → right), unanalyzed last
  const sortedArticles = [...articles].sort((a, b) => {
    if (a.political_lean == null && b.political_lean == null) return 0
    if (a.political_lean == null) return 1
    if (b.political_lean == null) return -1
    return a.political_lean - b.political_lean
  })

  return (
    <div className="p-6 space-y-5 max-w-5xl">
      {/* Back link */}
      <Link to="/clusters" className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-300 transition-colors">
        <ArrowLeft size={14} /> Back to Story Clusters
      </Link>

      {/* Header */}
      <div className="space-y-1">
        <div className="flex items-start gap-3">
          <Layers size={22} className="text-teal-400 mt-0.5 shrink-0" />
          <h1 className="text-xl font-bold text-white leading-snug">{topic_label || 'Story Cluster'}</h1>
        </div>
        <div className="flex flex-wrap items-center gap-3 text-sm text-gray-500 ml-9">
          <span>{article_count} articles</span>
          <span className="text-gray-700">·</span>
          <span>{source_count} outlets</span>
          {dateRange && (
            <>
              <span className="text-gray-700">·</span>
              <span>{dateRange}</span>
            </>
          )}
          {avg_lean != null && (
            <>
              <span className="text-gray-700">·</span>
              <LeanBadge value={avg_lean} />
              <span className="text-gray-600">avg lean</span>
            </>
          )}
        </div>
      </div>

      {/* Divergence meter */}
      {per_source.length >= 2 && (
        <DivergenceMeter divergence={bias_divergence} perSource={per_source} />
      )}

      {/* Per-source comparison */}
      {per_source.length > 0 && (
        <div className="card p-4 space-y-3">
          <h3 className="text-sm font-semibold text-white">Coverage by Outlet</h3>
          <div className="space-y-2">
            {per_source.map(s => (
              <div key={s.source_name} className="grid grid-cols-[180px_1fr_80px] items-center gap-3">
                <span className="text-sm text-gray-300 truncate">{s.source_name}</span>
                <LeanBar value={s.avg_lean} showLabel />
                <span className="text-xs text-gray-600 text-right">
                  {s.analyzed_count}/{s.article_count} analyzed
                </span>
              </div>
            ))}
          </div>
          <div className="flex justify-between text-xs text-gray-700 pt-1">
            <span>← Left</span>
            <span>Center</span>
            <span>Right →</span>
          </div>
        </div>
      )}

      {/* Articles table */}
      <div className="card p-0 overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-800">
          <h3 className="text-sm font-semibold text-white">
            Articles
            <span className="text-gray-500 font-normal ml-2">sorted left → right</span>
          </h3>
        </div>
        <div className="divide-y divide-gray-800/50">
          {sortedArticles.map(a => (
            <div key={a.id} className="px-4 py-3 flex items-start gap-3 hover:bg-gray-800/20 transition-colors">
              {/* Lean indicator dot */}
              <div
                className="w-2.5 h-2.5 rounded-full mt-1.5 shrink-0"
                style={{ backgroundColor: LEAN_COLOR(a.political_lean) }}
                title={LEAN_LABEL(a.political_lean)}
              />
              <div className="flex-1 min-w-0">
                <div className="flex items-start justify-between gap-2">
                  <Link
                    to={`/articles/${a.id}`}
                    className="text-sm text-gray-200 hover:text-blue-400 transition-colors line-clamp-2 leading-snug"
                  >
                    {a.title}
                  </Link>
                  {a.url && (
                    <a href={a.url} target="_blank" rel="noreferrer"
                      className="text-gray-600 hover:text-gray-400 shrink-0 mt-0.5">
                      <ExternalLink size={12} />
                    </a>
                  )}
                </div>
                <div className="flex items-center gap-3 mt-1">
                  <span className="text-xs text-gray-500">{a.source_name || '—'}</span>
                  {a.published_at && (
                    <>
                      <span className="text-gray-700 text-xs">·</span>
                      <span className="text-xs text-gray-600">
                        {new Date(a.published_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
                      </span>
                    </>
                  )}
                  {a.political_lean != null && (
                    <>
                      <span className="text-gray-700 text-xs">·</span>
                      <LeanBadge value={a.political_lean} />
                    </>
                  )}
                  {a.sentiment_label && (
                    <>
                      <span className="text-gray-700 text-xs">·</span>
                      <span className={`text-xs ${a.sentiment_label === 'positive' ? 'text-green-500' : a.sentiment_label === 'negative' ? 'text-red-500' : 'text-gray-500'}`}>
                        {a.sentiment_label}
                      </span>
                    </>
                  )}
                </div>
                {a.primary_topic && (
                  <p className="text-xs text-gray-600 mt-0.5 line-clamp-1">{a.primary_topic}</p>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
