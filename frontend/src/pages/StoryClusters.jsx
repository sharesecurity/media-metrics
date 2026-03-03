import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Layers, RefreshCw, ExternalLink, ChevronDown, ChevronRight, TrendingUp } from 'lucide-react'
import { getClusters, runClustering } from '../utils/api'

const BiasChip = ({ value }) => {
  if (value == null) return <span className="text-xs text-gray-600">—</span>
  const color = value < -0.2 ? 'text-blue-400' : value > 0.2 ? 'text-red-400' : 'text-green-400'
  const label = value < -0.3 ? 'L' : value > 0.3 ? 'R' : 'C'
  return (
    <span className={`text-xs font-mono ${color}`}>
      {label} {value > 0 ? '+' : ''}{value.toFixed(2)}
    </span>
  )
}

const LeanBar = ({ members }) => {
  if (!members?.length) return null
  const analyzed = members.filter(m => m.political_lean != null)
  if (!analyzed.length) return null
  return (
    <div className="flex gap-0.5 flex-wrap mt-2">
      {analyzed.map(m => {
        const pct = ((m.political_lean + 1) / 2) * 100
        const color = m.political_lean < -0.2 ? '#3b82f6' : m.political_lean > 0.2 ? '#ef4444' : '#22c55e'
        return (
          <div
            key={m.id}
            title={`${m.source_name}: ${m.political_lean?.toFixed(2)} — ${m.title?.slice(0, 60)}`}
            className="w-2 h-5 rounded-sm opacity-80 hover:opacity-100 cursor-help"
            style={{ backgroundColor: color }}
          />
        )
      })}
    </div>
  )
}

function ClusterRow({ cluster }) {
  const [open, setOpen] = useState(false)

  const { data: detail, isLoading: detailLoading } = useQuery({
    queryKey: ['cluster', cluster.id],
    queryFn: () => fetch(`/api/clusters/${cluster.id}`).then(r => r.json()),
    enabled: open,
    staleTime: 60000,
  })

  const leanColor = cluster.avg_lean == null ? 'text-gray-500'
    : cluster.avg_lean < -0.2 ? 'text-blue-400'
    : cluster.avg_lean > 0.2 ? 'text-red-400' : 'text-green-400'

  return (
    <div className="border-b border-gray-800/50 last:border-0">
      <button
        className="w-full text-left px-4 py-3 hover:bg-gray-800/30 transition-colors flex items-start gap-3"
        onClick={() => setOpen(v => !v)}
      >
        <span className="mt-0.5 text-gray-600 shrink-0">
          {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </span>
        <div className="flex-1 min-w-0">
          <p className="text-sm text-white line-clamp-1">{cluster.topic_label || 'Untitled cluster'}</p>
          <div className="flex items-center gap-3 mt-1">
            <span className="text-xs text-gray-500">{cluster.article_count} articles</span>
            <span className="text-xs text-gray-600">·</span>
            <span className="text-xs text-gray-500">{cluster.source_count} outlets</span>
            {cluster.date_end && (
              <>
                <span className="text-xs text-gray-600">·</span>
                <span className="text-xs text-gray-600">
                  {new Date(cluster.date_end).toLocaleDateString()}
                </span>
              </>
            )}
          </div>
          {cluster.sources?.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-1.5">
              {cluster.sources.map(s => (
                <span key={s} className="text-xs bg-gray-800 text-gray-400 px-1.5 py-0.5 rounded">
                  {s}
                </span>
              ))}
            </div>
          )}
        </div>
        <div className="shrink-0 text-right">
          <p className={`text-sm font-mono font-medium ${leanColor}`}>
            {cluster.avg_lean != null ? (cluster.avg_lean > 0 ? '+' : '') + cluster.avg_lean.toFixed(2) : '—'}
          </p>
          <p className="text-xs text-gray-600 mt-0.5">avg lean</p>
        </div>
      </button>

      {open && (
        <div className="px-8 pb-4">
          {detailLoading && <p className="text-xs text-gray-600 py-2">Loading articles...</p>}
          {detail && (
            <>
              <LeanBar members={detail.articles} />
              <div className="mt-3 space-y-1.5">
                {(detail.articles || []).map(a => (
                  <div key={a.id} className="flex items-start gap-2 text-xs">
                    <BiasChip value={a.political_lean} />
                    <span className="text-gray-500 w-28 shrink-0 truncate">{a.source_name || '—'}</span>
                    <Link
                      to={`/articles/${a.id}`}
                      className="text-gray-300 hover:text-blue-400 line-clamp-1 flex-1"
                    >
                      {a.title}
                    </Link>
                    {a.url && (
                      <a href={a.url} target="_blank" rel="noreferrer" className="text-gray-700 hover:text-gray-500 shrink-0">
                        <ExternalLink size={11} />
                      </a>
                    )}
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}

export default function StoryClusters() {
  const [minSources, setMinSources] = useState(1)
  const [running, setRunning] = useState(false)

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['clusters', minSources],
    queryFn: () => getClusters({ min_sources: minSources }),
    staleTime: 30000,
  })

  const handleRun = async () => {
    setRunning(true)
    try {
      await runClustering()
      setTimeout(() => { refetch(); setRunning(false) }, 8000)
    } catch {
      setRunning(false)
    }
  }

  const clusters = data?.clusters || []
  const total = data?.total ?? 0

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Layers size={20} className="text-teal-400" />
          <h1 className="text-2xl font-bold text-white">Story Clusters</h1>
          <span className="text-sm text-gray-500 ml-2">{total} clusters</span>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 text-sm">
            <span className="text-gray-500">Min outlets:</span>
            {[1, 2, 3, 4].map(n => (
              <button
                key={n}
                onClick={() => setMinSources(n)}
                className={`px-2.5 py-1 rounded text-xs transition-colors ${minSources === n ? 'bg-teal-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'}`}
              >
                {n}+
              </button>
            ))}
          </div>
          <button
            onClick={handleRun}
            disabled={running}
            className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-teal-700 hover:bg-teal-600 text-white text-sm transition-colors disabled:opacity-50"
          >
            <RefreshCw size={13} className={running ? 'animate-spin' : ''} />
            {running ? 'Clustering…' : 'Re-run'}
          </button>
        </div>
      </div>

      {/* Legend */}
      <div className="flex items-center gap-4 text-xs text-gray-500">
        <div className="flex items-center gap-1.5">
          <span className="w-3 h-3 rounded-sm bg-blue-500 inline-block" /> Left-leaning coverage
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-3 h-3 rounded-sm bg-green-500 inline-block" /> Centrist
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-3 h-3 rounded-sm bg-red-500 inline-block" /> Right-leaning coverage
        </div>
        <span className="text-gray-600">· Bars show outlet coverage range</span>
      </div>

      <div className="card p-0 overflow-hidden">
        {isLoading && (
          <p className="text-center text-gray-600 py-12">Loading clusters…</p>
        )}
        {!isLoading && !clusters.length && (
          <div className="text-center text-gray-600 py-12">
            <Layers size={32} className="mx-auto mb-3 opacity-30" />
            <p>No clusters yet.</p>
            <p className="text-xs mt-1">Run analysis on articles first, then click Re-run.</p>
          </div>
        )}
        {clusters.map(c => <ClusterRow key={c.id} cluster={c} />)}
      </div>

      {total > clusters.length && (
        <p className="text-xs text-gray-600 text-center">
          Showing {clusters.length} of {total} clusters · Adjust "Min outlets" filter to narrow results
        </p>
      )}
    </div>
  )
}
