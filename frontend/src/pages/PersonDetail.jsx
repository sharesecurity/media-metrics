import { useQuery } from '@tanstack/react-query'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, User, Building2, Briefcase } from 'lucide-react'
import { getPersonDetail, getPersonArticles } from '../utils/api'

const GENDER_COLORS = {
  male: '#3b82f6', female: '#ec4899', mostly_male: '#60a5fa',
  mostly_female: '#f472b6', unknown: '#6b7280',
}
const ETHNICITY_COLORS = {
  white: '#a78bfa', black: '#fbbf24', asian: '#34d399',
  hispanic: '#f97316', unknown: '#6b7280',
}

function DemoBadge({ value, colorMap }) {
  if (!value) return <span className="text-gray-600 text-sm">Unknown</span>
  const color = colorMap[value] || '#6b7280'
  return (
    <span
      className="px-3 py-1 rounded-full text-sm font-medium capitalize"
      style={{ background: color + '33', color }}
    >
      {value.replace('_', ' ')}
    </span>
  )
}

function LeanBadge({ value }) {
  if (value == null) return <span className="text-gray-500 text-xs">—</span>
  const color = value < -0.2 ? '#3b82f6' : value > 0.2 ? '#ef4444' : '#22c55e'
  return <span className="text-sm font-medium" style={{ color }}>{value > 0 ? '+' : ''}{value.toFixed(2)}</span>
}

function CareerTimeline({ career }) {
  if (!career?.length) {
    return (
      <div className="text-center py-6 text-gray-600 text-sm">
        No career history recorded yet. History is built from bylines and ingest data.
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {career.map((entry, i) => (
        <div key={i} className="flex items-start gap-4">
          {/* Timeline dot */}
          <div className="flex flex-col items-center mt-1">
            <div className={`w-3 h-3 rounded-full border-2 ${entry.valid_to ? 'border-gray-600 bg-gray-800' : 'border-blue-500 bg-blue-900'}`} />
            {i < career.length - 1 && <div className="w-px h-8 bg-gray-800 mt-1" />}
          </div>
          {/* Content */}
          <div className="flex-1 pb-2">
            <div className="flex items-center gap-2 flex-wrap">
              <Link to={`/organizations/${entry.org_id}`} className="font-medium text-white hover:text-blue-400">
                {entry.org_name}
              </Link>
              <span className="text-xs px-2 py-0.5 rounded bg-gray-800 text-gray-400">
                {entry.role}
              </span>
              {entry.beat && (
                <span className="text-xs text-gray-500 italic">{entry.beat}</span>
              )}
              {!entry.valid_to && (
                <span className="text-xs px-2 py-0.5 rounded bg-blue-900/40 text-blue-400">current</span>
              )}
            </div>
            <div className="text-xs text-gray-600 mt-1">
              {entry.valid_from || 'unknown start'} → {entry.valid_to || 'present'}
              {entry.confidence < 1.0 && (
                <span className="ml-2 text-yellow-700">(confidence: {(entry.confidence * 100).toFixed(0)}%)</span>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}

export default function PersonDetail() {
  const { id } = useParams()

  const { data: person, isLoading } = useQuery({
    queryKey: ['person', id],
    queryFn: () => getPersonDetail(id),
  })

  // Load articles via dedicated person endpoint (aggregates all linked author IDs)
  const { data: articles = [], isLoading: articlesLoading } = useQuery({
    queryKey: ['person-articles', id],
    queryFn: () => getPersonArticles(id, 50),
    enabled: !!person,
  })

  if (isLoading) return <div className="p-6 text-gray-400">Loading...</div>
  if (!person) return <div className="p-6 text-red-400">Person not found</div>

  return (
    <div className="p-6 space-y-6 max-w-4xl">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Link to="/people" className="text-gray-500 hover:text-gray-300">
          <ArrowLeft size={18} />
        </Link>
        <User size={20} className="text-gray-400" />
        <h1 className="text-xl font-bold text-white">{person.full_name}</h1>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-4 gap-4">
        <div className="card text-center">
          <p className="text-xs text-gray-500 uppercase tracking-wider">Articles</p>
          <p className="text-2xl font-bold text-white mt-1">{person.article_count}</p>
        </div>
        <div className="card text-center">
          <p className="text-xs text-gray-500 uppercase tracking-wider">Gender</p>
          <div className="mt-2">
            <DemoBadge value={person.gender} colorMap={GENDER_COLORS} />
          </div>
        </div>
        <div className="card text-center">
          <p className="text-xs text-gray-500 uppercase tracking-wider">Ethnicity</p>
          <div className="mt-2">
            <DemoBadge value={person.ethnicity} colorMap={ETHNICITY_COLORS} />
          </div>
        </div>
        <div className="card text-center">
          <p className="text-xs text-gray-500 uppercase tracking-wider">Avg Political Lean</p>
          <div className="text-2xl font-bold mt-1">
            <LeanBadge value={person.avg_political_lean} />
          </div>
        </div>
      </div>

      {/* Career timeline */}
      <div className="card">
        <div className="flex items-center gap-2 mb-4">
          <Briefcase size={16} className="text-gray-400" />
          <h2 className="font-semibold text-white">Career History</h2>
          <span className="text-xs text-gray-500">({person.career?.length ?? 0} positions)</span>
        </div>
        <CareerTimeline career={person.career} />
      </div>

      {/* Recent articles */}
      {articles.length > 0 && (
        <div className="card p-0 overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-800">
            <h2 className="font-semibold text-white">Recent Articles ({articles.length})</h2>
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
                <tr><td colSpan={4} className="text-center py-6 text-gray-600">Loading...</td></tr>
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
                    {a.political_lean != null ? <LeanBadge value={a.political_lean} /> : <span className="text-gray-600 text-xs">—</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
