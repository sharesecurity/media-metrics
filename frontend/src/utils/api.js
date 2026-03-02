import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

// Articles
export const getArticles = (params) => api.get('/articles/', { params }).then(r => r.data)
export const getArticle = (id) => api.get(`/articles/${id}`).then(r => r.data)
export const getArticleStats = () => api.get('/articles/stats').then(r => r.data)

// Analysis
export const runAnalysis = (article_id) => api.post('/analysis/run', { article_id }).then(r => r.data)
export const runAllAnalysis = () => api.post('/analysis/run-all').then(r => r.data)
export const getAnalysisResults = (article_id) => api.get(`/analysis/results/${article_id}`).then(r => r.data)
export const getTrends = (params) => api.get('/analysis/trends', { params }).then(r => r.data)
export const getTrendsBySource = (metric = 'political_lean') =>
  api.get('/analysis/trends/by-source', { params: { metric } }).then(r => r.data)

// Sources
export const getSources = () => api.get('/sources/').then(r => r.data)

// Search — keyword
export const searchArticles = (q, limit = 20) => api.get('/search/', { params: { q, limit } }).then(r => r.data)

// Search — semantic (vector)
export const semanticSearch = (q, limit = 15, source = null) => {
  const params = { q, limit }
  if (source) params.source = source
  return api.get('/search/semantic', { params }).then(r => r.data)
}

// Ingest
export const startIngest = (source = 'rss', limit = 20, sources = null) =>
  api.post('/ingest/start', { source, limit, sources }).then(r => r.data)
export const getIngestSources = () => api.get('/ingest/sources').then(r => r.data)

// Chat
export const askChat = (message, context = '') =>
  api.post('/chat/ask', { message, context }).then(r => r.data)
