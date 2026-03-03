import { useQuery } from '@tanstack/react-query'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, Building2, Users, ExternalLink } from 'lucide-react'
import { getOrganization } from '../utils/api'

function LeanBadge({ value }) {
  if (value == null) return <span className="text-gray-500 text-xs">—</span>
  const color = value < -0.2 ? '#3b82f6' : value > 0.2 ? '#ef4444' : '#22c55e'
  return (
    <span className="text-sm font-medium" style={{ color }}>
      {value > 0 ? '+' : ''}{value.toFixed(2)}
    </span>
  )
}

function StatCard({ label, value }) {
  return (
    <div className="card text-center">
      <p className="text-xs text-gray-500 uppercase tracking-wider">{label}</p>
      <p className="text-2xl font-bold text-white mt-1">{value ?? '—'}</p>
    </div>
  )
}

export default function OrganizationDetail() {
  const { id } = useParams()

  const { data: org, isLoading } = useQuery({
    queryKey: ['organization', id],
    queryFn: () => getOrganization(id),
  })

  if (isLoading) return <div className="p-6 text-gray-400">Loading...</div>
  if (!org) return <div className="p-6 text-red-400">Organization not found</div>

  return (
    <div className="p-6 space-y-6 max-w-5xl">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Link to="/organizations" className="text-gray-500 hover:text-gray-300">
          <ArrowLeft size={18} />
        </Link>
        <Building2 size={20} className="text-gray-400" />
        <h1 className="text-xl font-bold text-white">{org.name}</h1>
        {org.org_type && (
          <span className="px-2 py-0.5 rounded text-xs bg-blue-900/40 text-blue-400">
            {org.org_type.replace('_', ' ')}
          </span>
        )}
        {org.wikipedia_url && (
          <a href={org.wikipedia_url} target="_blank" rel="noreferrer" className="text-gray-500 hover:text-blue-400">
            <ExternalLink size={14} />
          </a>
        )}
      </div>

      {/* Stats */}
      <div className="grid grid-cols-4 gap-4">
        <StatCard label="Articles" value={org.article_count} />
        <div className="card text-center">
          <p className="text-xs text-gray-500 uppercase tracking-wider">Avg Political Lean</p>
          <div className="mt-2">
            <LeanBadge value={org.avg_political_lean} />
          </div>
        </div>
        <StatCard label="Country" value={org.country} />
        <StatCard label="Domain" value={org.domain} />
      </div>

      {/* People / Career */}
      <div className="card p-0 overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-800 flex items-center gap-2">
          <Users size={16} className="text-gray-400" />
          <h2 className="font-semibold text-white">People ({org.people?.length ?? 0})</h2>
        </div>
        {!org.people?.length ? (
          <div className="text-center py-8 text-gray-600 text-sm">
            No people linked yet. Run entity seeding or add affiliations manually.
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800">
                {['Name', 'Role', 'Beat', 'From', 'To', 'Confidence'].map(h => (
                  <th key={h} className="text-left text-xs text-gray-500 uppercase tracking-wider px-4 py-3 font-medium">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {org.people.map(p => (
                <tr key={p.id} className="border-b border-gray-800/50 hover:bg-gray-800/30 transition-colors">
                  <td className="px-4 py-3">
                    <Link to={`/people/${p.id}`} className="text-white hover:text-blue-400">
                      {p.full_name}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-gray-400 text-xs">{p.role || '—'}</td>
                  <td className="px-4 py-3 text-gray-400 text-xs">{p.beat || '—'}</td>
                  <td className="px-4 py-3 text-gray-500 text-xs">{p.valid_from || '—'}</td>
                  <td className="px-4 py-3 text-gray-500 text-xs">{p.valid_to || 'present'}</td>
                  <td className="px-4 py-3 text-gray-500 text-xs">
                    {p.confidence != null ? (p.confidence * 100).toFixed(0) + '%' : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
