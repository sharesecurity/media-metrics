import { Routes, Route, NavLink, useLocation } from 'react-router-dom'
import { LayoutDashboard, Newspaper, BarChart2, MessageSquare, TrendingUp, Search, Settings } from 'lucide-react'
import Dashboard from './pages/Dashboard'
import Articles from './pages/Articles'
import ArticleDetail from './pages/ArticleDetail'
import BiasAnalysis from './pages/BiasAnalysis'
import Chat from './pages/Chat'
import Trends from './pages/Trends'
import SemanticSearch from './pages/SemanticSearch'
import BiasMethodEditor from './pages/BiasMethodEditor'

const NAV = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/articles', icon: Newspaper, label: 'Articles' },
  { to: '/bias', icon: BarChart2, label: 'Bias Analysis' },
  { to: '/trends', icon: TrendingUp, label: 'Trends' },
  { to: '/search', icon: Search, label: 'Semantic Search' },
  { to: '/chat', icon: MessageSquare, label: 'AI Chat' },
  { to: '/bias-methods', icon: Settings, label: 'Bias Methods' },
]

export default function App() {
  return (
    <div className="flex h-screen overflow-hidden">
      {/* Sidebar */}
      <aside className="w-56 bg-gray-900 border-r border-gray-800 flex flex-col shrink-0">
        <div className="p-5 border-b border-gray-800">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center">
              <BarChart2 size={16} />
            </div>
            <span className="font-bold text-white">Media Metrics</span>
          </div>
          <p className="text-xs text-gray-500 mt-1">News Bias Analysis</p>
        </div>

        <nav className="flex-1 p-3 space-y-1">
          {NAV.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                  isActive
                    ? 'bg-blue-600 text-white'
                    : 'text-gray-400 hover:text-white hover:bg-gray-800'
                }`
              }
            >
              <Icon size={16} />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="p-3 border-t border-gray-800 text-xs text-gray-600 text-center">
          v0.2.0 · deepseek-r1:8b
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 overflow-auto">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/articles" element={<Articles />} />
          <Route path="/articles/:id" element={<ArticleDetail />} />
          <Route path="/bias" element={<BiasAnalysis />} />
          <Route path="/trends" element={<Trends />} />
          <Route path="/search" element={<SemanticSearch />} />
          <Route path="/chat" element={<Chat />} />
          <Route path="/bias-methods" element={<BiasMethodEditor />} />
        </Routes>
      </main>
    </div>
  )
}
