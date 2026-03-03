import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Users } from 'lucide-react'
import { getPeople } from '../utils/api'

const GENDER_COLORS = {
  male: '#3b82f6', female: '#ec4899', mostly_male: '#60a5fa',
  mostly_female: '#f472b6', unknown: '#6b7280',
}
const ETHNICITY_COLORS = {
  white: '#a78bfa', black: '#fbbf24', asian: '#34d399',
  hispanic: '#f97316', unknown: '#6b7280',
}

function DemoBadge({ value, colorMap }) {
  if (!value) return <span className="text-gray-600 text-xs">—</span>
  const color = colorMap[value] || '#6b7280'
  return (
    <span
      className="px-2 py-0.5 rounded text-xs font-medium capitalize"
      style={{ background: color + '33', color }}
    >
      {value.replace('_', ' ')}
    </span>
  )
}

export default function People() {
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(0)
  const limit = 100

  const { data, isLoading } = useQuery({
    queryKey: ['people', page],
    queryFn: () => getPeople({ limit, offset: page * limit }),
  })

  const people = data?.people ?? []
  const total = data?.total ?? 0

  const filtered = search
    ? people.filter(p => p.full_name.toLowerCase().includes(search.toLowerCase()))
    : people

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Users size={20} className="text-gray-400" />
          <h1 className="text-xl font-bold text-white">People</h1>
          <span className="text-sm text-gray-500">{total} total journalists &amp; editors</span>
        </div>
      </div>

      <div className="flex gap-3">
        <input
          type="text"
          placeholder="Search by name..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="input flex-1 max-w-xs"
        />
      </div>

      <div className="card p-0 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800">
              {['Name', 'Gender', 'Ethnicity', 'Known Bylines'].map(h => (
                <th key={h} className="text-left text-xs text-gray-500 uppercase tracking-wider px-4 py-3 font-medium">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr><td colSpan={4} className="text-center py-8 text-gray-600">Loading...</td></tr>
            )}
            {!isLoading && filtered.length === 0 && (
              <tr><td colSpan={4} className="text-center py-8 text-gray-600">No people found.</td></tr>
            )}
            {filtered.map(p => (
              <tr key={p.id} className="border-b border-gray-800/50 hover:bg-gray-800/30 transition-colors">
                <td className="px-4 py-3">
                  <Link to={`/people/${p.id}`} className="text-white hover:text-blue-400 font-medium">
                    {p.full_name}
                  </Link>
                </td>
                <td className="px-4 py-3">
                  <DemoBadge value={p.gender} colorMap={GENDER_COLORS} />
                </td>
                <td className="px-4 py-3">
                  <DemoBadge value={p.ethnicity} colorMap={ETHNICITY_COLORS} />
                </td>
                <td className="px-4 py-3 text-gray-500 text-xs">
                  {p.byline_variants?.slice(0, 2).join(', ') || '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {total > limit && (
        <div className="flex items-center gap-3 text-sm text-gray-400">
          <button
            onClick={() => setPage(p => Math.max(0, p - 1))}
            disabled={page === 0}
            className="px-3 py-1 bg-gray-800 rounded disabled:opacity-30 hover:bg-gray-700"
          >
            ← Prev
          </button>
          <span>{page * limit + 1}–{Math.min((page + 1) * limit, total)} of {total}</span>
          <button
            onClick={() => setPage(p => p + 1)}
            disabled={(page + 1) * limit >= total}
            className="px-3 py-1 bg-gray-800 rounded disabled:opacity-30 hover:bg-gray-700"
          >
            Next →
          </button>
        </div>
      )}
    </div>
  )
}
