import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid } from 'recharts'
import { Users, RefreshCw, User } from 'lucide-react'
import { Link } from 'react-router-dom'
import { getAuthors, getDemographicsSummary, inferAllDemographics } from '../utils/api'

const GENDER_COLORS = {
  male: '#3b82f6',
  female: '#ec4899',
  mostly_male: '#60a5fa',
  mostly_female: '#f472b6',
  unknown: '#6b7280',
}

const ETHNICITY_COLORS = {
  white: '#a78bfa',
  black: '#fbbf24',
  asian: '#34d399',
  hispanic: '#f97316',
  unknown: '#6b7280',
}

const GENDER_LABELS = {
  male: 'Male',
  female: 'Female',
  mostly_male: 'Mostly Male',
  mostly_female: 'Mostly Female',
  unknown: 'Unknown',
}

const ETHNICITY_LABELS = {
  white: 'White',
  black: 'Black',
  asian: 'Asian',
  hispanic: 'Hispanic',
  unknown: 'Unknown',
}

export default function Authors() {
  const [search, setSearch] = useState('')
  const [inferred, setInferred] = useState(false)

  const { data: authors = [], refetch: refetchAuthors, isLoading: authorsLoading } =
    useQuery({ queryKey: ['authors'], queryFn: getAuthors })

  const { data: summary, refetch: refetchSummary, isLoading: summaryLoading } =
    useQuery({ queryKey: ['demographics-summary'], queryFn: getDemographicsSummary })

  const inferMutation = useMutation({
    mutationFn: inferAllDemographics,
    onSuccess: (data) => {
      setInferred(true)
      setTimeout(() => {
        refetchAuthors()
        refetchSummary()
      }, 3000)
    },
  })

  const filtered = authors.filter(a =>
    !search || a.name.toLowerCase().includes(search.toLowerCase())
  )

  // Prepare chart data
  const genderData = summary
    ? Object.entries(summary.by_gender).map(([k, v]) => ({
        name: GENDER_LABELS[k] || k,
        value: v,
        key: k,
      }))
    : []

  const ethnicityData = summary
    ? Object.entries(summary.by_ethnicity).map(([k, v]) => ({
        name: ETHNICITY_LABELS[k] || k,
        value: v,
        key: k,
      }))
    : []

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Users size={24} />
            Authors
          </h1>
          <p className="text-gray-400 mt-1">
            {summary?.total_authors ?? authors.length} authors · demographic breakdown
          </p>
        </div>
        <button
          onClick={() => inferMutation.mutate()}
          disabled={inferMutation.isPending}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-lg text-sm transition-colors"
        >
          <RefreshCw size={14} className={inferMutation.isPending ? 'animate-spin' : ''} />
          {inferMutation.isPending ? 'Inferring...' : 'Infer Demographics'}
        </button>
      </div>

      {inferMutation.isSuccess && (
        <div className="bg-green-900/30 border border-green-700 rounded-lg p-3 text-green-300 text-sm">
          Demographics inference started for {inferMutation.data?.count} authors. Charts will update shortly.
        </div>
      )}

      {/* Charts */}
      {summary && (
        <div className="grid grid-cols-2 gap-6">
          <div className="bg-gray-900 rounded-xl p-5">
            <h2 className="text-white font-semibold mb-4">Gender Distribution</h2>
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie data={genderData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={80} label={({ name, percent }) => `${name} ${(percent*100).toFixed(0)}%`}>
                  {genderData.map((entry) => (
                    <Cell key={entry.key} fill={GENDER_COLORS[entry.key] || '#6b7280'} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </div>

          <div className="bg-gray-900 rounded-xl p-5">
            <h2 className="text-white font-semibold mb-4">Ethnicity Distribution</h2>
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie data={ethnicityData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={80} label={({ name, percent }) => `${name} ${(percent*100).toFixed(0)}%`}>
                  {ethnicityData.map((entry) => (
                    <Cell key={entry.key} fill={ETHNICITY_COLORS[entry.key] || '#6b7280'} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Author table */}
      <div className="bg-gray-900 rounded-xl overflow-hidden">
        <div className="p-4 border-b border-gray-800 flex items-center gap-3">
          <input
            type="text"
            placeholder="Search authors..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="input flex-1"
          />
          <span className="text-gray-500 text-sm">{filtered.length} shown</span>
        </div>

        {authorsLoading ? (
          <div className="p-8 text-center text-gray-500">Loading authors...</div>
        ) : filtered.length === 0 ? (
          <div className="p-8 text-center text-gray-500">
            No authors found.{' '}
            {authors.length === 0 && 'Ingest and analyze articles first.'}
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800 text-gray-400 text-left">
                <th className="px-4 py-3">Author</th>
                <th className="px-4 py-3">Outlet</th>
                <th className="px-4 py-3">Gender</th>
                <th className="px-4 py-3">Ethnicity</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(author => (
                <tr key={author.id} className="border-b border-gray-800 hover:bg-gray-800/50 transition-colors">
                  <td className="px-4 py-3">
                    <Link to={`/authors/${author.id}`} className="flex items-center gap-2 hover:text-blue-400">
                      <User size={14} className="text-gray-500" />
                      <span className="text-white">{author.name}</span>
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-gray-400 text-xs">{author.source_name || '—'}</td>
                  <td className="px-4 py-3">
                    {author.gender ? (
                      <span
                        className="px-2 py-0.5 rounded text-xs font-medium"
                        style={{
                          background: (GENDER_COLORS[author.gender] || '#6b7280') + '33',
                          color: GENDER_COLORS[author.gender] || '#6b7280',
                        }}
                      >
                        {GENDER_LABELS[author.gender] || author.gender}
                      </span>
                    ) : (
                      <span className="text-gray-600 text-xs">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {author.ethnicity ? (
                      <span
                        className="px-2 py-0.5 rounded text-xs font-medium"
                        style={{
                          background: (ETHNICITY_COLORS[author.ethnicity] || '#6b7280') + '33',
                          color: ETHNICITY_COLORS[author.ethnicity] || '#6b7280',
                        }}
                      >
                        {ETHNICITY_LABELS[author.ethnicity] || author.ethnicity}
                      </span>
                    ) : (
                      <span className="text-gray-600 text-xs">—</span>
                    )}
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
