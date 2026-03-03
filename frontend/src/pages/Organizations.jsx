import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Building2 } from 'lucide-react'
import { getOrganizations } from '../utils/api'

const ORG_TYPE_COLORS = {
  publisher:     { bg: '#3b82f633', text: '#3b82f6' },
  wire_service:  { bg: '#10b98133', text: '#10b981' },
  parent_company:{ bg: '#f59e0b33', text: '#f59e0b' },
  investor:      { bg: '#8b5cf633', text: '#8b5cf6' },
}

function LeanBar({ value }) {
  if (value == null) return <span className="text-gray-600 text-xs">—</span>
  const pct = ((value + 1) / 2) * 100
  const color = value < -0.2 ? '#3b82f6' : value > 0.2 ? '#ef4444' : '#22c55e'
  return (
    <div className="flex items-center gap-2">
      <div className="w-20 h-2 bg-gray-800 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full"
          style={{ width: `${pct}%`, background: color }}
        />
      </div>
      <span className="text-xs" style={{ color }}>
        {value > 0 ? '+' : ''}{value.toFixed(2)}
      </span>
    </div>
  )
}

export default function Organizations() {
  const [filter, setFilter] = useState('')
  const [typeFilter, setTypeFilter] = useState('all')

  const { data: orgs = [], isLoading } = useQuery({
    queryKey: ['organizations'],
    queryFn: () => getOrganizations(),
  })

  const filtered = orgs.filter(o => {
    const matchText = !filter || o.name.toLowerCase().includes(filter.toLowerCase())
    const matchType = typeFilter === 'all' || o.org_type === typeFilter
    return matchText && matchType
  })

  const types = ['all', ...Array.from(new Set(orgs.map(o => o.org_type).filter(Boolean)))]

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Building2 size={20} className="text-gray-400" />
          <h1 className="text-xl font-bold text-white">Organizations</h1>
          <span className="text-sm text-gray-500">{orgs.length} total</span>
        </div>
      </div>

      {/* Filters */}
      <div className="flex gap-3">
        <input
          type="text"
          placeholder="Search organizations..."
          value={filter}
          onChange={e => setFilter(e.target.value)}
          className="input flex-1 max-w-xs"
        />
        <select
          value={typeFilter}
          onChange={e => setTypeFilter(e.target.value)}
          className="input"
        >
          {types.map(t => (
            <option key={t} value={t}>{t === 'all' ? 'All Types' : t.replace('_', ' ')}</option>
          ))}
        </select>
      </div>

      {/* Table */}
      <div className="card p-0 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800">
              {['Name', 'Type', 'Domain', 'Country', 'Political Lean'].map(h => (
                <th key={h} className="text-left text-xs text-gray-500 uppercase tracking-wider px-4 py-3 font-medium">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr><td colSpan={5} className="text-center py-8 text-gray-600">Loading...</td></tr>
            )}
            {!isLoading && filtered.length === 0 && (
              <tr><td colSpan={5} className="text-center py-8 text-gray-600">No organizations found.</td></tr>
            )}
            {filtered.map(o => {
              const typeStyle = ORG_TYPE_COLORS[o.org_type] || { bg: '#6b728033', text: '#6b7280' }
              return (
                <tr key={o.id} className="border-b border-gray-800/50 hover:bg-gray-800/30 transition-colors">
                  <td className="px-4 py-3">
                    <Link to={`/organizations/${o.id}`} className="text-white hover:text-blue-400 font-medium">
                      {o.name}
                    </Link>
                  </td>
                  <td className="px-4 py-3">
                    {o.org_type ? (
                      <span
                        className="px-2 py-0.5 rounded text-xs font-medium"
                        style={{ background: typeStyle.bg, color: typeStyle.text }}
                      >
                        {o.org_type.replace('_', ' ')}
                      </span>
                    ) : <span className="text-gray-600 text-xs">—</span>}
                  </td>
                  <td className="px-4 py-3 text-gray-400 text-xs">{o.domain || '—'}</td>
                  <td className="px-4 py-3 text-gray-400 text-xs">{o.country || '—'}</td>
                  <td className="px-4 py-3"><LeanBar value={o.political_lean} /></td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
