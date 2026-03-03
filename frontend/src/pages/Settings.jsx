import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getSettings,
  updateLogSettings,
  scaleCelery,
  getCeleryStatus,
} from '../utils/api'
import {
  Settings as SettingsIcon,
  FileText,
  Cpu,
  Save,
  CheckCircle,
  AlertCircle,
  ChevronDown,
  ChevronUp,
} from 'lucide-react'

// ── helpers ────────────────────────────────────────────────────────────────────

const Badge = ({ children, color = 'blue' }) => {
  const cls = {
    blue:   'bg-blue-900/40 text-blue-300 border-blue-700',
    green:  'bg-green-900/40 text-green-300 border-green-700',
    yellow: 'bg-yellow-900/40 text-yellow-300 border-yellow-700',
    gray:   'bg-gray-800 text-gray-400 border-gray-600',
  }[color] ?? 'bg-gray-800 text-gray-300 border-gray-600'
  return (
    <span className={`px-2 py-0.5 rounded border text-xs font-mono ${cls}`}>
      {children}
    </span>
  )
}

const SectionHeader = ({ icon: Icon, title, subtitle }) => (
  <div className="flex items-start gap-3 mb-6">
    <div className="p-2 bg-blue-900/30 rounded-lg mt-0.5">
      <Icon size={18} className="text-blue-400" />
    </div>
    <div>
      <h2 className="text-lg font-semibold text-white">{title}</h2>
      {subtitle && <p className="text-sm text-gray-400 mt-0.5">{subtitle}</p>}
    </div>
  </div>
)

const SaveBar = ({ dirty, onSave, saving, saved, error }) => (
  <div className={`flex items-center gap-3 mt-6 pt-4 border-t border-gray-700 transition-opacity ${dirty ? 'opacity-100' : 'opacity-0 pointer-events-none'}`}>
    <button
      onClick={onSave}
      disabled={saving}
      className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-blue-800 rounded-lg text-sm font-medium transition-colors"
    >
      <Save size={14} />
      {saving ? 'Saving…' : 'Save Changes'}
    </button>
    {saved && (
      <span className="flex items-center gap-1.5 text-green-400 text-sm">
        <CheckCircle size={14} /> Saved
      </span>
    )}
    {error && (
      <span className="flex items-center gap-1.5 text-red-400 text-sm">
        <AlertCircle size={14} /> {error}
      </span>
    )}
  </div>
)

// ── Log Settings section ───────────────────────────────────────────────────────

function LogSettings({ settings }) {
  const qc = useQueryClient()

  const [form, setForm] = useState({
    log_level:        'info',
    log_output:       'file',
    log_dir:          '/app/logs',
    splunk_hec_url:   '',
    splunk_hec_token: '',
    splunk_hec_index: 'media_metrics',
  })
  const [dirty, setDirty]   = useState(false)
  const [saved, setSaved]   = useState(false)
  const [showSplunk, setShowSplunk] = useState(false)

  // Populate from loaded settings
  useEffect(() => {
    if (!settings) return
    const next = {
      log_level:        settings.log_level?.value        ?? 'info',
      log_output:       settings.log_output?.value       ?? 'file',
      log_dir:          settings.log_dir?.value          ?? '/app/logs',
      splunk_hec_url:   settings.splunk_hec_url?.value   ?? '',
      splunk_hec_token: settings.splunk_hec_token?.value ?? '',
      splunk_hec_index: settings.splunk_hec_index?.value ?? 'media_metrics',
    }
    setForm(next)
    setShowSplunk(['splunk', 'both'].includes(next.log_output))
  }, [settings])

  const set = (key, val) => {
    setForm(f => ({ ...f, [key]: val }))
    setDirty(true)
    setSaved(false)
    if (key === 'log_output') setShowSplunk(['splunk', 'both'].includes(val))
  }

  const mutation = useMutation({
    mutationFn: () => updateLogSettings(form),
    onSuccess: () => {
      setSaved(true)
      setDirty(false)
      qc.invalidateQueries(['settings'])
      setTimeout(() => setSaved(false), 3000)
    },
  })

  const LEVELS = [
    { value: 'debug', label: 'Debug', desc: 'All events including per-article ingestion details' },
    { value: 'info',  label: 'Info',  desc: 'Normal pipeline events (scrape, analysis start/complete)' },
    { value: 'error', label: 'Error', desc: 'Failures only — low volume' },
  ]

  const OUTPUTS = [
    { value: 'file',   label: 'File',         desc: 'Write to rotating log files on disk' },
    { value: 'splunk', label: 'Splunk HEC',    desc: 'Send to Splunk HTTP Event Collector' },
    { value: 'both',   label: 'File + Splunk', desc: 'Write to both simultaneously' },
  ]

  return (
    <div className="bg-gray-900 border border-gray-700 rounded-xl p-6">
      <SectionHeader
        icon={FileText}
        title="Logging"
        subtitle="JSON-structured logs with UTC timestamps. Each pipeline event (ingest, scrape, analysis) emits a record."
      />

      {/* Log Level */}
      <div className="mb-6">
        <label className="block text-sm font-medium text-gray-300 mb-3">Log Level</label>
        <div className="flex flex-col gap-2">
          {LEVELS.map(l => (
            <label
              key={l.value}
              className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                form.log_level === l.value
                  ? 'border-blue-500 bg-blue-900/20'
                  : 'border-gray-700 hover:border-gray-600'
              }`}
            >
              <input
                type="radio"
                name="log_level"
                value={l.value}
                checked={form.log_level === l.value}
                onChange={e => set('log_level', e.target.value)}
                className="mt-0.5 accent-blue-500"
              />
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-white">{l.label}</span>
                  <Badge color={l.value === 'error' ? 'yellow' : l.value === 'debug' ? 'gray' : 'blue'}>
                    {l.value}
                  </Badge>
                </div>
                <p className="text-xs text-gray-400 mt-0.5">{l.desc}</p>
              </div>
            </label>
          ))}
        </div>
      </div>

      {/* Log Output */}
      <div className="mb-6">
        <label className="block text-sm font-medium text-gray-300 mb-3">Output Destination</label>
        <div className="flex flex-col gap-2">
          {OUTPUTS.map(o => (
            <label
              key={o.value}
              className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                form.log_output === o.value
                  ? 'border-blue-500 bg-blue-900/20'
                  : 'border-gray-700 hover:border-gray-600'
              }`}
            >
              <input
                type="radio"
                name="log_output"
                value={o.value}
                checked={form.log_output === o.value}
                onChange={e => set('log_output', e.target.value)}
                className="mt-0.5 accent-blue-500"
              />
              <div>
                <span className="text-sm font-medium text-white">{o.label}</span>
                <p className="text-xs text-gray-400 mt-0.5">{o.desc}</p>
              </div>
            </label>
          ))}
        </div>
      </div>

      {/* File path */}
      {(form.log_output === 'file' || form.log_output === 'both') && (
        <div className="mb-6">
          <label className="block text-sm font-medium text-gray-300 mb-1">
            Log Directory (container path)
          </label>
          <p className="text-xs text-gray-500 mb-2">
            Backed by Docker volume <code className="text-gray-400">mm_logs</code>.
            Files rotate at 10 MB, keep 5 backups.
          </p>
          <input
            type="text"
            value={form.log_dir}
            onChange={e => set('log_dir', e.target.value)}
            className="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-sm font-mono text-white focus:outline-none focus:border-blue-500"
            placeholder="/app/logs"
          />
        </div>
      )}

      {/* Splunk HEC config */}
      {showSplunk && (
        <div className="mb-6 bg-gray-800/50 rounded-lg p-4 border border-gray-700">
          <button
            onClick={() => setShowSplunk(v => !v)}
            className="flex items-center gap-2 text-sm font-medium text-gray-300 w-full text-left mb-4"
          >
            Splunk HEC Configuration
            {showSplunk ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>
          <div className="space-y-3">
            <div>
              <label className="block text-xs text-gray-400 mb-1">HEC Endpoint URL</label>
              <input
                type="url"
                value={form.splunk_hec_url}
                onChange={e => set('splunk_hec_url', e.target.value)}
                className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm font-mono text-white focus:outline-none focus:border-blue-500"
                placeholder="https://splunk:8088/services/collector/event"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">HEC Token</label>
              <input
                type="password"
                value={form.splunk_hec_token}
                onChange={e => set('splunk_hec_token', e.target.value)}
                className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm font-mono text-white focus:outline-none focus:border-blue-500"
                placeholder="••••••••"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">Splunk Index</label>
              <input
                type="text"
                value={form.splunk_hec_index}
                onChange={e => set('splunk_hec_index', e.target.value)}
                className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm font-mono text-white focus:outline-none focus:border-blue-500"
                placeholder="media_metrics"
              />
            </div>
          </div>
        </div>
      )}

      {/* Events reference */}
      <div className="bg-gray-800/40 rounded-lg p-4 border border-gray-700/50">
        <p className="text-xs text-gray-400 font-medium mb-2">Logged Events</p>
        <div className="grid grid-cols-2 gap-x-6 gap-y-1">
          {[
            ['article_ingested',    'debug', 'New article added to DB'],
            ['article_scraped',     'info',  'Full text fetched successfully'],
            ['article_scrape_failed','info/error', 'Scrape failed or empty'],
            ['analysis_started',    'info',  'Bias analysis begins'],
            ['analysis_completed',  'info',  'Analysis saved with lean/sentiment'],
            ['analysis_failed',     'error', 'Analysis error'],
            ['batch_scrape_complete','info', 'Scrape batch finished'],
            ['kaggle_ingest_complete','info','Kaggle batch finished'],
            ['settings_updated',    'info',  'Settings changed'],
            ['celery_concurrency_changed','info','Worker pool adjusted'],
          ].map(([ev, lvl, desc]) => (
            <div key={ev} className="flex items-start gap-2 py-0.5">
              <Badge color={lvl === 'error' ? 'yellow' : lvl === 'debug' ? 'gray' : 'blue'}>
                {lvl}
              </Badge>
              <div>
                <code className="text-xs text-gray-300">{ev}</code>
                <p className="text-xs text-gray-500">{desc}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      <SaveBar
        dirty={dirty}
        onSave={() => mutation.mutate()}
        saving={mutation.isPending}
        saved={saved}
        error={mutation.isError ? String(mutation.error) : null}
      />
    </div>
  )
}

// ── Workers section ────────────────────────────────────────────────────────────

function WorkerSettings({ settings }) {
  const qc = useQueryClient()

  const { data: celery } = useQuery({
    queryKey: ['celery-status'],
    queryFn: getCeleryStatus,
    refetchInterval: 5000,
  })

  const storedConcurrency = parseInt(settings?.celery_concurrency?.value ?? '1', 10)
  const [concurrency, setConcurrency] = useState(storedConcurrency)
  const [dirty, setDirty] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    setConcurrency(storedConcurrency)
  }, [storedConcurrency])

  const adj = (delta) => {
    const next = Math.max(1, Math.min(16, concurrency + delta))
    setConcurrency(next)
    setDirty(next !== storedConcurrency)
    setSaved(false)
  }

  const mutation = useMutation({
    mutationFn: () => scaleCelery(concurrency),
    onSuccess: () => {
      setSaved(true)
      setDirty(false)
      qc.invalidateQueries(['settings'])
      qc.invalidateQueries(['celery-status'])
      setTimeout(() => setSaved(false), 3000)
    },
  })

  const workers = celery?.workers ?? []
  const totalActive = workers.reduce((s, w) => s + (w.active_tasks ?? 0), 0)

  return (
    <div className="bg-gray-900 border border-gray-700 rounded-xl p-6">
      <SectionHeader
        icon={Cpu}
        title="Celery Workers"
        subtitle="Adjust the number of concurrent analysis processes. Ollama handles one LLM request at a time, so 2–3 workers is usually enough."
      />

      {/* Live worker status */}
      <div className="mb-6">
        <p className="text-xs text-gray-400 font-medium uppercase tracking-wide mb-3">Live Status</p>
        {workers.length === 0 ? (
          <div className="text-sm text-gray-500">No workers connected</div>
        ) : (
          <div className="space-y-2">
            {workers.map(w => (
              <div key={w.name} className="bg-gray-800 rounded-lg p-3 flex items-center justify-between">
                <div>
                  <p className="text-sm font-mono text-gray-300">{w.name.split('@')[1] ?? w.name}</p>
                  <p className="text-xs text-gray-500">
                    {w.processes?.length ?? '?'} processes · {w.active_tasks} active task{w.active_tasks !== 1 ? 's' : ''}
                  </p>
                </div>
                <Badge color={w.active_tasks > 0 ? 'green' : 'gray'}>
                  concurrency {w.concurrency}
                </Badge>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Concurrency control */}
      <div className="mb-6">
        <label className="block text-sm font-medium text-gray-300 mb-1">
          Pool Concurrency
        </label>
        <p className="text-xs text-gray-500 mb-3">
          Sends a live <code className="text-gray-400">pool_grow</code> /
          <code className="text-gray-400">pool_shrink</code> signal to the running worker — no restart required.
          Persisted for the next startup via <code className="text-gray-400">CELERY_CONCURRENCY</code>.
        </p>
        <div className="flex items-center gap-4">
          <button
            onClick={() => adj(-1)}
            disabled={concurrency <= 1}
            className="w-9 h-9 flex items-center justify-center bg-gray-700 hover:bg-gray-600 disabled:opacity-30 rounded-lg text-lg font-bold transition-colors"
          >
            −
          </button>
          <div className="text-center">
            <div className="text-3xl font-bold text-white tabular-nums">{concurrency}</div>
            <div className="text-xs text-gray-500">processes</div>
          </div>
          <button
            onClick={() => adj(1)}
            disabled={concurrency >= 16}
            className="w-9 h-9 flex items-center justify-center bg-gray-700 hover:bg-gray-600 disabled:opacity-30 rounded-lg text-lg font-bold transition-colors"
          >
            +
          </button>
          {dirty && (
            <span className="text-xs text-yellow-400 ml-2">
              → was {storedConcurrency}
            </span>
          )}
        </div>
      </div>

      <div className="bg-gray-800/40 rounded-lg p-4 border border-gray-700/50 text-xs text-gray-400">
        <p className="font-medium text-gray-300 mb-1">Tips</p>
        <ul className="space-y-1 list-disc list-inside">
          <li>Ollama processes one LLM inference at a time — extra workers queue and wait</li>
          <li>2–3 workers can help overlap scraping + analysis tasks</li>
          <li>To run <em>multiple worker containers</em>, scale via <code className="text-gray-300">make up</code> after editing docker-compose</li>
          <li>Current active tasks: <span className="text-white font-medium">{totalActive}</span></li>
        </ul>
      </div>

      <SaveBar
        dirty={dirty}
        onSave={() => mutation.mutate()}
        saving={mutation.isPending}
        saved={saved}
        error={mutation.isError ? String(mutation.error) : null}
      />
    </div>
  )
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default function Settings() {
  const { data: settings, isLoading } = useQuery({
    queryKey: ['settings'],
    queryFn: getSettings,
    staleTime: 30_000,
  })

  if (isLoading) {
    return (
      <div className="p-8 text-gray-400">Loading settings…</div>
    )
  }

  return (
    <div className="p-6 max-w-3xl mx-auto">
      <div className="flex items-center gap-3 mb-8">
        <SettingsIcon size={24} className="text-blue-400" />
        <div>
          <h1 className="text-2xl font-bold text-white">Settings</h1>
          <p className="text-sm text-gray-400">Configure logging, worker concurrency, and other runtime options</p>
        </div>
      </div>

      <div className="space-y-6">
        <LogSettings settings={settings} />
        <WorkerSettings settings={settings} />
      </div>
    </div>
  )
}
