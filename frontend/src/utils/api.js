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

// Sources
export const getSources = () => api.get('/sources/').then(r => r.data)

// Search
export const searchArticles = (q, limit = 20) => api.get('/search/', { params: { q, limit } }).then(r => r.data)

// Ingest
export const startIngest = (source = 'gdelt', limit = 100) =>
  api.post('/ingest/start', { source, limit }).then(r => r.data)

// Chat
export const askChat = (message, context = '') =>
  api.post('/chat/ask', { message, context }).then(r => r.data)
