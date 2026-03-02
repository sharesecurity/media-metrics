import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

// Articles
export const getArticles = (params) => api.get('/articles/', { params }).then(r => r.data)
export const getArticlesByAuthor = (author_id, limit = 50) =>
  api.get('/articles/', { params: { author_id, limit } }).then(r => r.data)
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
export const startIngest = (source = 'rss', limit = 20, sources = null, auto_analyze = false) =>
  api.post('/ingest/start', { source, limit, sources, auto_analyze }).then(r => r.data)
export const getIngestSources = () => api.get('/ingest/sources').then(r => r.data)

// Chat
export const askChat = (message, context = '') =>
  api.post('/chat/ask', { message, context }).then(r => r.data)

// Bias Methods
export const getBiasMethods = () => api.get('/bias-methods/').then(r => r.data)
export const getBiasMethod = (id) => api.get(`/bias-methods/${id}`).then(r => r.data)
export const createBiasMethod = (body) => api.post('/bias-methods/', body).then(r => r.data)
export const updateBiasMethod = (id, body) => api.put(`/bias-methods/${id}`, body).then(r => r.data)
export const deleteBiasMethod = (id) => api.delete(`/bias-methods/${id}`).then(r => r.data)
export const toggleBiasMethod = (id) => api.post(`/bias-methods/${id}/toggle`).then(r => r.data)
export const compareMethodsOnArticle = (article_id, method_ids = null) =>
  api.post('/bias-methods/compare', { article_id, method_ids }, { timeout: 300000 }).then(r => r.data)

// MinIO migration
export const migrateToMinio = (limit = 500) =>
  api.post('/articles/migrate-to-minio', null, { params: { limit } }).then(r => r.data)

// Authors / demographics
export const getAuthors = () => api.get('/authors/').then(r => r.data)
export const getAuthor = (id) => api.get(`/authors/${id}`).then(r => r.data)
export const getDemographicsSummary = () => api.get('/authors/demographics/summary').then(r => r.data)
export const inferAllDemographics = () => api.post('/authors/infer-demographics').then(r => r.data)
