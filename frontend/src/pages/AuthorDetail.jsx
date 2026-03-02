import { useQuery } from '@tanstack/react-query'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, User } from 'lucide-react'
import { getAuthor, getArticlesByAuthor } from '../utils/api'

const GENDER_COLORS = {
  male: '#3b82f6', female: '#ec4899', mostly_male: '#60a5fa',
  mostly_female: '#f472b6', unknown: '#6b7280',
}
const ETHNICITY_COLORS = {
  white: '#a78bfa', black: '#fbbf24', asian: '#34d399',
  hispanic: '#f97316', unknown: '#6b7280',
}
const GENDER_LABELS = {
  male: 'Male', female: 'Female', mostly_male: 'Mostly Male',
  mostly_female: 'Mostly Female', unknown: 'Unknown',
}
const ETHNICITY_LABELS = {
  white: 'White', black: 'Black', asian: 'Asian', hispanic: 'Hispanic', unknown: 'Unknown',
}

function DemoBadge({ value, colorMap, labelMap }) {
  if (!value) return <span className="text-gray-600 text-sm">Unknown</span>
  const color = colorMap[value] || '#6b7280'
  return (
    <span
      className="px-3 py-1 rounded-full text-sm font-medium"
      style={{ background: color + '33', color }}
    >
      {labelMap[value] || value}
    </span>
  )
}

function LeanBadge({ value }) {
  if (value == null) return <span className="text-gray-500 text-xs">—</span>
  const color = value < -0.2 ? 'text-blue-400' : value > 0.2 ? 'text-red-400' : 'text-green-400'
  return <span className={`text-xs font-medium ${color}`}>{value > 0 ? '+' : ''}{value.toFixed(2)}</span>
}

export default function AuthorDetail() {
  const { id } = useParams()

  const { data: author, isLoading: authorLoading } = useQuery({
    queryKey: ['author', id],
    queryFn: () => getAuthor(id),
  })

  const { data: articles = [], isLoading: articlesLoading } = useQuery({
    queryKey: ['articles-by-author', id],
    queryFn: () => getArticlesByAuthor(id, 100),
    enabled: !!id,
  })

  if (authorLoading) return <div className="p-6 text-gray-400">Loading...</div>
  if (!author) return <div className="p-6 text-red-400">Author not found</div>

  const analyzed = articles.filter(a => a.political_lean != null)
  const avgLean = analyzed.length
    ? analyzed.reduce((s, a) => s + a.political_lean, 0) / analyzed.length
    : null

  return (
    <div className="p-6 space-y-6 max-w-4xl">
      <div className="flex items-center gap-3">
        <Link to="/authors" className="text-gray-500 hover:text-gray-300">
          <ArrowLeft size={18} />
        </Link>
        <User size={20} className="text-gray-400" />
        <h1 className="text-xl font-bold text-white">{author.name}</h1>
      </div>

      {/* Author stats */}
      <div className="grid grid-cols-4 gap-4">
        <div className="card text-center">
          <p className="text-xs text-gray-500 uppercase tracking-wider">Articles</p>
          <p className="text-2xl font-bold text-white mt-1">{author.article_count ?? articles.length}</p>
        </div>
        <div className="card text-center">
          <p className="text-xs text-gray-500 uppercase tracking-wider">Gender</p>
          <div className="mt-2">
            <DemoBadge value={author.gender} colorMap={GENDER_COLORS} labelMap={GENDER_LABELS} />
          </div>
        </div>
        <div className="card text-center">
          <p className="text-xs text-gray-500 uppercase tracking-wider">Ethnicity</p>
          <div className="mt-2">
            <DemoBadge value={author.ethnicity} colorMap={ETHNICITY_COLORS} labelMap={ETHNICITY_LABELS} />
          </div>
        </div>
        <div className="card text-center">
          <p className="text-xs text-gray-500 uppercase tracking-wider">Avg Political Lean</p>
          <div className="text-2xl font-bold mt-1">
            {avgLean != null
              ? <span className={avgLean < -0.2 ? 'text-blue-400' : avgLean > 0.2 ? 'text-red-400' : 'text-green-400'}>
                  {avgLean > 0 ? '+' : ''}{avgLean.toFixed(2)}
                </span>
              : <span className="text-gray-600">—</span>
            }
          </div>
        </div>
      </div>

      {/* Articles list */}
      <div className="card p-0 overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-800">
          <h2 className="font-semibold text-white">Articles ({articles.length})</h2>
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800">
              {['Title', 'Source', 'Date', 'Political Lean'].map(h => (
                <th key={h} className="text-left text-xs text-gray-500 uppercase tracking-wider px-4 py-3 font-medium">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {articlesLoading && (
              <tr><td colSpan={4} className="text-center py-8 text-gray-600">Loading...</td></tr>
            )}
            {!articlesLoading && articles.length === 0 && (
              <tr><td colSpan={4} className="text-center py-8 text-gray-600">No articles found for this author.</td></tr>
            )}
            {articles.map(a => (
              <tr key={a.id} className="border-b border-gray-800/50 hover:bg-gray-800/30 transition-colors">
                <td className="px-4 py-3 max-w-xs">
                  <Link to={`/articles/${a.id}`} className="text-white hover:text-blue-400 line-clamp-2">
                    {a.title}
                  </Link>
                </td>
                <td className="px-4 py-3 text-gray-400 text-xs whitespace-nowrap">{a.source_name || '—'}</td>
                <td className="px-4 py-3 text-gray-500 text-xs whitespace-nowrap">
                  {a.published_at ? new Date(a.published_at).toLocaleDateString() : '—'}
                </td>
                <td className="px-4 py-3">
                  <LeanBadge value={a.political_lean} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
