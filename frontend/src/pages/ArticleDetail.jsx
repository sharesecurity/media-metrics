import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useParams, Link } from 'react-router-dom'
import { getArticle, runAnalysis, getBiasMethods, compareMethodsOnArticle } from '../utils/api'
import { ArrowLeft, Play, ExternalLink, GitCompare, CheckSquare, Square } from 'lucide-react'

const MetricCard = ({ label, value, unit = '', color = 'text-white' }) => (
  <div className="card text-center">
    <p className="text-xs text-gray-500 uppercase tracking-wider">{label}</p>
    <p className={`text-2xl font-bold mt-1 ${color}`}>
      {value != null ? `${value}${unit}` : '—'}
    </p>
  </div>
)

const PoliticalBar = ({ value, small = false }) => {
  if (value == null) return null
  const pct = ((value + 1) / 2) * 100
  return (
    <div className={`space-y-1 ${small ? '' : 'space-y-2'}`}>
      {!small && (
        <div className="flex justify-between text-xs text-gray-500">
          <span>Far Left (−1.0)</span>
          <span>Neutral (0.0)</span>
          <span>Far Right (+1.0)</span>
        </div>
      )}
      <div className={`relative ${small ? 'h-3' : 'h-4'} rounded-full overflow-visible`}
        style={{ background: 'linear-gradient(to right, #3b82f6, #22c55e, #ef4444)' }}>
        <div
          className={`absolute top-1/2 -translate-y-1/2 ${small ? 'w-3 h-3' : 'w-5 h-5'} rounded-full bg-white border-2 border-gray-900 shadow-lg`}
          style={{ left: `calc(${pct}% - ${small ? 6 : 10}px)` }}
          title={`Score: ${value.toFixed(3)}`}
        />
      </div>
      {!small && (
        <div className="text-center text-sm font-semibold">
          {value < -0.4 ? '🔵 Left-leaning' :
           value > 0.4 ? '🔴 Right-leaning' :
           value < -0.1 ? '🔵 Slightly Left' :
           value > 0.1 ? '🔴 Slightly Right' :
           '🟢 Center / Neutral'}
          <span className="text-gray-500 ml-2">({value > 0 ? '+' : ''}{value.toFixed(3)})</span>
        </div>
      )}
    </div>
  )
}

function LeanBadge({ value }) {
  if (value == null) return <span className="text-gray-500 text-sm">—</span>
  const color = value < -0.3 ? 'text-blue-400' : value > 0.3 ? 'text-red-400' : 'text-green-400'
  return (
    <span className={`font-bold text-lg ${color}`}>
      {value > 0 ? '+' : ''}{value.toFixed(2)}
    </span>
  )
}

export default function ArticleDetail() {
  const { id } = useParams()
  const queryClient = useQueryClient()
  const [showCompare, setShowCompare] = useState(false)
  const [selectedMethods, setSelectedMethods] = useState([])
  const [compareResults, setCompareResults] = useState(null)

  const { data: article, isLoading, refetch } = useQuery({
    queryKey: ['article', id],
    queryFn: () => getArticle(id),
  })

  const { data: biasMethods = [] } = useQuery({
    queryKey: ['bias-methods'],
    queryFn: getBiasMethods,
    enabled: showCompare,
  })

  const analyzeMutation = useMutation({
    mutationFn: () => runAnalysis(id),
    onSuccess: () => {
      setTimeout(() => refetch(), 3000)
    }
  })

  const compareMutation = useMutation({
    mutationFn: () => compareMethodsOnArticle(id, selectedMethods.length > 0 ? selectedMethods : null),
    onSuccess: (data) => {
      setCompareResults(data)
    },
  })

  if (isLoading) return <div className="p-6 text-gray-400">Loading...</div>
  if (!article) return <div className="p-6 text-red-400">Article not found</div>

  const latest = article.analyses?.[0]

  const toggleMethod = (mid) => {
    setSelectedMethods(prev =>
      prev.includes(mid) ? prev.filter(x => x !== mid) : [...prev, mid]
    )
  }

  return (
    <div className="p-6 space-y-6 max-w-4xl">
      <div className="flex items-center gap-3">
        <Link to="/articles" className="text-gray-500 hover:text-gray-300">
          <ArrowLeft size={18} />
        </Link>
        <h1 className="text-xl font-bold text-white flex-1">{article.title}</h1>
        {article.url && (
          <a href={article.url} target="_blank" rel="noreferrer"
            className="text-gray-500 hover:text-gray-300">
            <ExternalLink size={16} />
          </a>
        )}
      </div>

      {/* Metadata */}
      <div className="flex gap-4 text-sm text-gray-500">
        <span>{article.source_name || 'Unknown source'}</span>
        {article.published_at && <span>· {new Date(article.published_at).toLocaleDateString()}</span>}
        {article.word_count && <span>· {article.word_count} words</span>}
        {article.section && <span>· {article.section}</span>}
      </div>

      {/* Analysis trigger */}
      {!latest && (
        <div className="card flex items-center justify-between">
          <p className="text-gray-400 text-sm">This article hasn't been analyzed yet.</p>
          <button
            onClick={() => analyzeMutation.mutate()}
            disabled={analyzeMutation.isPending}
            className="btn-primary flex items-center gap-2 text-sm"
          >
            <Play size={13} />
            {analyzeMutation.isPending ? 'Queued...' : 'Analyze Now'}
          </button>
        </div>
      )}

      {/* Analysis results */}
      {latest && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold text-white">Analysis Results</h2>
            <div className="flex items-center gap-3">
              <span className="text-xs text-gray-600">
                {latest.model_used} · {latest.analyzed_at ? new Date(latest.analyzed_at).toLocaleString() : ''}
              </span>
              <button
                onClick={() => analyzeMutation.mutate()}
                className="btn-ghost text-xs border border-gray-700"
              >
                Re-analyze
              </button>
              <button
                onClick={() => { setShowCompare(!showCompare); setCompareResults(null) }}
                className="btn-ghost text-xs border border-gray-700 flex items-center gap-1"
              >
                <GitCompare size={12} />
                Multi-method
              </button>
            </div>
          </div>

          <div className="grid grid-cols-4 gap-3">
            <MetricCard label="Sentiment" value={latest.sentiment_label}
              color={latest.sentiment_score > 0.05 ? 'text-green-400' :
                     latest.sentiment_score < -0.05 ? 'text-red-400' : 'text-yellow-400'} />
            <MetricCard label="Sentiment Score" value={latest.sentiment_score?.toFixed(3)} />
            <MetricCard label="Reading Level" value={latest.reading_level?.toFixed(1)} unit=" grade" />
            <MetricCard label="Primary Topic" value={latest.primary_topic} />
          </div>

          {/* Political lean bar */}
          {latest.political_lean != null && (
            <div className="card">
              <h3 className="text-sm font-medium text-gray-300 mb-4">Political Lean</h3>
              <PoliticalBar value={latest.political_lean} />
              {latest.raw_analysis?.llm?.framing_notes && (
                <p className="text-sm text-gray-400 mt-4 italic">
                  "{latest.raw_analysis.llm.framing_notes}"
                </p>
              )}
              {latest.raw_analysis?.llm?.key_indicators?.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-2">
                  {latest.raw_analysis.llm.key_indicators.map((ind, i) => (
                    <span key={i} className="text-xs bg-gray-800 text-gray-400 px-2 py-1 rounded">
                      {ind}
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Lexical bias */}
          {latest.raw_analysis?.lexical && (
            <div className="card">
              <h3 className="text-sm font-medium text-gray-300 mb-3">Lexical Bias Analysis</h3>
              <div className="grid grid-cols-3 gap-4 text-sm">
                <div>
                  <p className="text-gray-500 text-xs">Bias Score (0-10)</p>
                  <p className="text-xl font-bold text-white">{latest.raw_analysis.lexical.score ?? '—'}</p>
                </div>
                <div>
                  <p className="text-gray-500 text-xs">Charged Words/1000</p>
                  <p className="text-xl font-bold text-white">{latest.raw_analysis.lexical.charged_ratio_per_1000 ?? '—'}</p>
                </div>
                <div>
                  <p className="text-gray-500 text-xs">Hedge Words Found</p>
                  <p className="text-sm text-gray-400">{latest.raw_analysis.lexical.hedge_words_found?.join(', ') || 'none'}</p>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Multi-method comparison panel */}
      {showCompare && (
        <div className="card space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold text-white flex items-center gap-2">
              <GitCompare size={16} />
              Multi-Method Comparison
            </h3>
            <p className="text-xs text-gray-500">
              Run this article through multiple bias detection methods simultaneously
            </p>
          </div>

          {biasMethods.length === 0 ? (
            <p className="text-gray-500 text-sm">No bias methods found. Create some in the Bias Methods editor.</p>
          ) : (
            <div className="space-y-2">
              <p className="text-sm text-gray-400">Select methods to compare (leave empty = all active):</p>
              <div className="grid grid-cols-2 gap-2">
                {biasMethods.map(m => (
                  <button
                    key={m.id}
                    onClick={() => toggleMethod(m.id)}
                    className={`flex items-center gap-2 p-2 rounded text-sm text-left transition-colors ${
                      selectedMethods.includes(m.id)
                        ? 'bg-blue-900 text-blue-300'
                        : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                    }`}
                  >
                    {selectedMethods.includes(m.id)
                      ? <CheckSquare size={14} />
                      : <Square size={14} />}
                    <span className="flex-1">{m.name}</span>
                    {!m.is_active && <span className="text-xs text-gray-600">(inactive)</span>}
                  </button>
                ))}
              </div>
            </div>
          )}

          <button
            onClick={() => compareMutation.mutate()}
            disabled={compareMutation.isPending}
            className="btn-primary flex items-center gap-2 text-sm"
          >
            <Play size={13} />
            {compareMutation.isPending
              ? `Running ${selectedMethods.length || biasMethods.filter(m => m.is_active).length} methods...`
              : `Compare ${selectedMethods.length > 0 ? selectedMethods.length : 'All Active'} Methods`}
          </button>

          {compareMutation.isPending && (
            <p className="text-xs text-gray-500 animate-pulse">
              Calling Ollama for each method... This may take a minute or two.
            </p>
          )}

          {/* Results table */}
          {compareResults && (
            <div className="space-y-3">
              <p className="text-xs text-gray-500">{compareResults.methods_run} methods completed</p>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-700 text-gray-400 text-left">
                      <th className="py-2 pr-4">Method</th>
                      <th className="py-2 pr-4">Political Lean</th>
                      <th className="py-2 pr-4">Confidence</th>
                      <th className="py-2">Primary Topic</th>
                    </tr>
                  </thead>
                  <tbody>
                    {compareResults.results.map(r => (
                      <tr key={r.method_id} className="border-b border-gray-800">
                        <td className="py-3 pr-4 font-medium text-white">{r.method_name}</td>
                        <td className="py-3 pr-4">
                          {r.error ? (
                            <span className="text-red-400 text-xs">{r.error}</span>
                          ) : (
                            <div className="space-y-1">
                              <LeanBadge value={r.political_lean} />
                              <PoliticalBar value={r.political_lean} small />
                            </div>
                          )}
                        </td>
                        <td className="py-3 pr-4 text-gray-400">
                          {r.confidence != null ? `${(r.confidence * 100).toFixed(0)}%` : '—'}
                        </td>
                        <td className="py-3 text-gray-400 text-xs max-w-xs">{r.primary_topic || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Framing notes */}
              {compareResults.results.some(r => r.framing_notes) && (
                <div className="space-y-2">
                  <p className="text-xs text-gray-500 uppercase tracking-wider">Framing Notes by Method</p>
                  {compareResults.results.filter(r => r.framing_notes).map(r => (
                    <div key={r.method_id} className="bg-gray-800 rounded p-3">
                      <p className="text-xs text-blue-400 font-medium mb-1">{r.method_name}</p>
                      <p className="text-xs text-gray-400 italic">"{r.framing_notes}"</p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Article text */}
      {article.raw_text && (
        <div className="card">
          <h3 className="text-sm font-medium text-gray-300 mb-3">Article Text</h3>
          <p className="text-gray-400 text-sm leading-relaxed whitespace-pre-wrap">
            {article.raw_text}
          </p>
        </div>
      )}
    </div>
  )
}
