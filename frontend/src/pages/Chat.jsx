import { useState, useRef, useEffect } from 'react'
import { askChat } from '../utils/api'
import { Send, Bot, User } from 'lucide-react'

const EXAMPLES = [
  "Which news source in our dataset has the most negative sentiment?",
  "What topics are most covered in the articles?",
  "Compare the bias scores between Fox News and NPR articles.",
  "What is political lean and how is it measured?",
  "Which articles have the most extreme political lean scores?",
]

export default function Chat() {
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content: "Hello! I'm your Media Metrics AI assistant. Ask me anything about the news articles and bias analysis in your dataset. I can help you interpret results, compare sources, or explain methodology."
    }
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const send = async (text) => {
    const msg = text || input.trim()
    if (!msg || loading) return
    setInput('')
    setMessages(prev => [...prev, { role: 'user', content: msg }])
    setLoading(true)
    try {
      const res = await askChat(msg)
      setMessages(prev => [...prev, { role: 'assistant', content: res.response }])
    } catch (e) {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: `Error: ${e.message}. Make sure Ollama is running and deepseek-r1:8b is pulled.`
      }])
    }
    setLoading(false)
  }

  return (
    <div className="flex flex-col h-full">
      <div className="p-6 border-b border-gray-800">
        <h1 className="text-2xl font-bold text-white">AI Chat</h1>
        <p className="text-gray-400 text-sm mt-1">Ask questions about your news data (powered by Ollama · deepseek-r1:8b)</p>
      </div>

      <div className="flex-1 overflow-y-auto p-6 space-y-4">
        {/* Example prompts when only welcome message */}
        {messages.length === 1 && (
          <div className="space-y-2">
            <p className="text-xs text-gray-600 uppercase tracking-wider">Try asking:</p>
            <div className="flex flex-wrap gap-2">
              {EXAMPLES.map((ex, i) => (
                <button key={i} onClick={() => send(ex)}
                  className="text-xs bg-gray-800 hover:bg-gray-700 text-gray-300 px-3 py-2 rounded-lg text-left transition-colors">
                  {ex}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m, i) => (
          <div key={i} className={`flex gap-3 ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            {m.role === 'assistant' && (
              <div className="w-7 h-7 rounded-full bg-blue-600 flex items-center justify-center shrink-0 mt-0.5">
                <Bot size={14} />
              </div>
            )}
            <div className={`max-w-2xl px-4 py-3 rounded-xl text-sm leading-relaxed whitespace-pre-wrap ${
              m.role === 'user'
                ? 'bg-blue-600 text-white'
                : 'bg-gray-800 text-gray-200'
            }`}>
              {m.content}
            </div>
            {m.role === 'user' && (
              <div className="w-7 h-7 rounded-full bg-gray-700 flex items-center justify-center shrink-0 mt-0.5">
                <User size={14} />
              </div>
            )}
          </div>
        ))}

        {loading && (
          <div className="flex gap-3">
            <div className="w-7 h-7 rounded-full bg-blue-600 flex items-center justify-center shrink-0">
              <Bot size={14} />
            </div>
            <div className="bg-gray-800 px-4 py-3 rounded-xl text-sm text-gray-500">
              <span className="animate-pulse">Thinking...</span>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="p-4 border-t border-gray-800">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && !e.shiftKey && send()}
            placeholder="Ask about bias, sentiment, topics, sources..."
            className="flex-1 bg-gray-800 border border-gray-700 rounded-xl px-4 py-3 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
          />
          <button
            onClick={() => send()}
            disabled={!input.trim() || loading}
            className="btn-primary w-11 h-11 flex items-center justify-center disabled:opacity-50"
          >
            <Send size={15} />
          </button>
        </div>
      </div>
    </div>
  )
}
