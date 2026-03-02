import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useParams, Link } from 'react-router-dom'
import { getArticle, runAnalysis } from '../utils/api'
import { ArrowLeft, Play, ExternalLink } from 'lucide-react'

const MetricCard = ({ label, value, unit = '', color = 'text-white' }) => (
  <div className="card text-center">
    <p className="text-xs text-gray-500 uppercase tracking-wider">{label}</p>
    <p className={`text-2xl font-bold mt-1 ${color}`}>
      {value != null ? `${value}${unit}` : '—'}
    </p>
  </div>
)

const PoliticalBar = ({ value }) => {
  if (value == null) return null
  const pct = ((value + 1) / 2) * 100
  return (
    <div className="space-y-2">
      <div className="flex justify-between text-xs text-gray-500">
        <span>Far Left (−1.0)</span>
        <span>Neutral (0.0)</span>
        <span>Far Right (+1.0)</span>
      </div>
      <div className="relative h-4 rounded-full overflow-visible"
        style={{ background: 'linear-gradient(to right, #3b82f6, #22c55e, #ef4444)' }}>
        <div
          className="absolute top-1/2 -translate-y-1/2 w-5 h-5 rounded-full bg-white border-2 border-gray-900 shadow-lg"
          style={{ left: `calc(${pct}% - 10px)` }}
          title={`Score: ${value.toFixed(3)}`}
        />
      </div>
      <div className="text-center text-sm font-semibold">
        {value < -0.4 ? '🔵 Left-leaning' :
         value > 0.4 ? '🔴 Right-leaning' :
         value < -0.1 ? '🔵 Slightly Left' :
         value > 0.1 ? '🔴 Slightly Right' :
         '🟢 Center / Neutral'}
        <span className="text-gray-500 ml-2">({value > 0 ? '+' : ''}{value.toFixed(3)})</span>
      </div>
    </div>
  )
}

export default function ArticleDetail() {
  const { id } = useParams()
  const queryClient = useQueryClient()
  const { data: article, isLoading, refetch } = useQuery({
    queryKey: ['article', id],
    queryFn: () => getArticle(id),
  })

  const analyzeMutation = useMutation({
    mutationFn: () => runAnalysis(id),
    onSuccess: () => {
      setTimeout(() => refetch(), 3000)
    }
  })

  if (isLoading) return <div className="p-6 text-gray-400">Loading...</div>
  if (!article) return <div className="p-6 text-red-400">Article not found</div>

  const latest = article.analyses?.[0]

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
