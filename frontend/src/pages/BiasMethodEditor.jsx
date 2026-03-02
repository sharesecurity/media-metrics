import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2, ToggleLeft, ToggleRight, ChevronDown, ChevronUp, Save } from 'lucide-react'
import {
  getBiasMethods, createBiasMethod, updateBiasMethod,
  deleteBiasMethod, toggleBiasMethod
} from '../utils/api'

const DEFAULT_PROMPT = `Analyze the political bias of this news article.
Rate it on a scale from -1.0 (strongly left-leaning) to 1.0 (strongly right-leaning), where 0.0 is neutral/balanced.

Consider:
- Word choice and loaded language
- Which perspectives are given more prominence
- What facts are emphasized vs omitted
- Whose voices are quoted
- Framing of issues

Respond ONLY with valid JSON (no explanation outside JSON):
{
  "political_lean": <float -1.0 to 1.0>,
  "confidence": <float 0.0 to 1.0>,
  "primary_topic": "<string>",
  "key_indicators": ["<indicator1>", "<indicator2>"],
  "framing_notes": "<brief explanation>"
}`

function MethodCard({ method, onSaved, onDeleted }) {
  const [expanded, setExpanded] = useState(false)
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState({
    name: method.name,
    description: method.description || '',
    prompt_template: method.prompt_template || '',
  })
  const [saving, setSaving] = useState(false)
  const queryClient = useQueryClient()

  const toggleMutation = useMutation({
    mutationFn: () => toggleBiasMethod(method.id),
    onSuccess: () => queryClient.invalidateQueries(['bias-methods']),
  })

  const deleteMutation = useMutation({
    mutationFn: () => deleteBiasMethod(method.id),
    onSuccess: () => queryClient.invalidateQueries(['bias-methods']),
  })

  const handleSave = async () => {
    setSaving(true)
    try {
      await updateBiasMethod(method.id, form)
      queryClient.invalidateQueries(['bias-methods'])
      setEditing(false)
    } catch (e) {
      console.error(e)
    }
    setSaving(false)
  }

  return (
    <div className={`card border ${method.is_active ? 'border-blue-700/50' : 'border-gray-700'}`}>
      <div className="flex items-center gap-3">
        <button
          onClick={() => toggleMutation.mutate()}
          className={`transition-colors ${method.is_active ? 'text-blue-400' : 'text-gray-600'}`}
          title={method.is_active ? 'Deactivate' : 'Activate'}
        >
          {method.is_active ? <ToggleRight size={22} /> : <ToggleLeft size={22} />}
        </button>

        <div className="flex-1 min-w-0">
          {editing ? (
            <input
              className="input w-full text-sm font-semibold"
              value={form.name}
              onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
            />
          ) : (
            <span className="font-semibold text-white text-sm">{method.name}</span>
          )}
          <span className={`ml-2 text-xs px-2 py-0.5 rounded-full ${
            method.is_active ? 'bg-blue-900/60 text-blue-300' : 'bg-gray-800 text-gray-500'
          }`}>
            {method.is_active ? 'active' : 'inactive'}
          </span>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => { setEditing(e => !e); setExpanded(true) }}
            className="text-xs text-gray-400 hover:text-white px-2 py-1 rounded border border-gray-700 hover:border-gray-500 transition-colors"
          >
            {editing ? 'Cancel' : 'Edit'}
          </button>
          <button
            onClick={() => deleteMutation.mutate()}
            className="text-gray-600 hover:text-red-400 transition-colors"
            title="Delete method"
          >
            <Trash2 size={14} />
          </button>
          <button
            onClick={() => setExpanded(e => !e)}
            className="text-gray-500 hover:text-gray-300 transition-colors"
          >
            {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </button>
        </div>
      </div>

      {expanded && (
        <div className="mt-4 space-y-3 border-t border-gray-800 pt-4">
          <div>
            <label className="text-xs text-gray-500 uppercase tracking-wider">Description</label>
            {editing ? (
              <input
                className="input w-full mt-1 text-sm"
                value={form.description}
                onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
                placeholder="What this method detects..."
              />
            ) : (
              <p className="text-sm text-gray-300 mt-1">{method.description || '—'}</p>
            )}
          </div>

          <div>
            <label className="text-xs text-gray-500 uppercase tracking-wider">Prompt Template</label>
            {editing ? (
              <textarea
                className="input w-full mt-1 text-xs font-mono"
                rows={14}
                value={form.prompt_template}
                onChange={e => setForm(f => ({ ...f, prompt_template: e.target.value }))}
                placeholder="The LLM prompt. Use {article_text} as the placeholder for the article."
              />
            ) : (
              <pre className="mt-1 text-xs text-gray-400 bg-gray-900 rounded-lg p-3 overflow-auto whitespace-pre-wrap max-h-48">
                {method.prompt_template || '(no prompt set — uses default)'}
              </pre>
            )}
          </div>

          {editing && (
            <button
              onClick={handleSave}
              disabled={saving}
              className="btn-primary flex items-center gap-2 text-sm"
            >
              <Save size={14} />
              {saving ? 'Saving...' : 'Save Changes'}
            </button>
          )}

          <p className="text-xs text-gray-600">
            Created: {method.created_at ? new Date(method.created_at).toLocaleDateString() : '—'}
            {method.modified_at && ` · Updated: ${new Date(method.modified_at).toLocaleDateString()}`}
          </p>
        </div>
      )}
    </div>
  )
}

function NewMethodForm({ onCreated }) {
  const [form, setForm] = useState({ name: '', description: '', prompt_template: DEFAULT_PROMPT })
  const [saving, setSaving] = useState(false)
  const queryClient = useQueryClient()

  const handleCreate = async () => {
    if (!form.name.trim()) return
    setSaving(true)
    try {
      await createBiasMethod(form)
      queryClient.invalidateQueries(['bias-methods'])
      setForm({ name: '', description: '', prompt_template: DEFAULT_PROMPT })
      onCreated()
    } catch (e) {
      console.error(e)
    }
    setSaving(false)
  }

  return (
    <div className="card border border-dashed border-gray-700 space-y-3">
      <h3 className="font-semibold text-white text-sm">New Bias Method</h3>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-xs text-gray-500">Name</label>
          <input
            className="input w-full mt-1 text-sm"
            value={form.name}
            onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
            placeholder="e.g. Emotional Language Detector"
          />
        </div>
        <div>
          <label className="text-xs text-gray-500">Description</label>
          <input
            className="input w-full mt-1 text-sm"
            value={form.description}
            onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
            placeholder="What this method measures..."
          />
        </div>
      </div>
      <div>
        <label className="text-xs text-gray-500">Prompt Template</label>
        <textarea
          className="input w-full mt-1 text-xs font-mono"
          rows={10}
          value={form.prompt_template}
          onChange={e => setForm(f => ({ ...f, prompt_template: e.target.value }))}
        />
      </div>
      <div className="flex gap-2">
        <button onClick={handleCreate} disabled={saving || !form.name.trim()} className="btn-primary text-sm flex items-center gap-2">
          <Plus size={14} />
          {saving ? 'Creating...' : 'Create Method'}
        </button>
        <button onClick={onCreated} className="btn-ghost text-sm border border-gray-700">Cancel</button>
      </div>
    </div>
  )
}

export default function BiasMethodEditor() {
  const [showNew, setShowNew] = useState(false)

  const { data: methods = [], isLoading } = useQuery({
    queryKey: ['bias-methods'],
    queryFn: getBiasMethods,
  })

  const active = methods.filter(m => m.is_active)
  const inactive = methods.filter(m => !m.is_active)

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Bias Methods</h1>
          <p className="text-gray-400 text-sm mt-1">
            Configure the LLM prompts used to detect political lean and other bias signals.
          </p>
        </div>
        <button
          onClick={() => setShowNew(s => !s)}
          className="btn-primary flex items-center gap-2 text-sm"
        >
          <Plus size={14} />
          New Method
        </button>
      </div>

      {showNew && <NewMethodForm onCreated={() => setShowNew(false)} />}

      {isLoading ? (
        <p className="text-gray-500 text-sm">Loading...</p>
      ) : methods.length === 0 ? (
        <div className="card text-center py-10">
          <p className="text-gray-500 text-sm">No bias methods defined yet.</p>
          <button onClick={() => setShowNew(true)} className="btn-primary mt-3 text-sm">
            Create First Method
          </button>
        </div>
      ) : (
        <div className="space-y-6">
          {active.length > 0 && (
            <div className="space-y-3">
              <h2 className="text-xs text-gray-500 uppercase tracking-wider">Active ({active.length})</h2>
              {active.map(m => <MethodCard key={m.id} method={m} />)}
            </div>
          )}
          {inactive.length > 0 && (
            <div className="space-y-3">
              <h2 className="text-xs text-gray-500 uppercase tracking-wider">Inactive ({inactive.length})</h2>
              {inactive.map(m => <MethodCard key={m.id} method={m} />)}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
