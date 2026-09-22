import React, { useState, useRef, useEffect, useCallback } from 'react'
import { API_BASE } from '../apiConfig'

/**
 * ChatPanel — Evidence-grounded Q&A chat interface.
 * 
 * Sends questions to the backend, displays responses with:
 * - Three-way distinction (stated / interpreted / not_established)
 * - Source clause citations (clickable to scroll to clause)
 * - Certainty badges with icon + text (never color alone)
 * 
 * Efficiency: Uses useCallback and React.memo to minimize re-render latency.
 * 
 * Accessibility:
 * - role="log" with aria-live for screen reader announcements
 * - Focus management on message submission
 */
function ChatPanel({ sessionId, clauses }) {
  const [messages, setMessages] = useState([{
    id: 'welcome',
    sender: 'assistant',
    text: 'I\'ve analyzed your document. Ask me anything about it! Try questions like:\n• "What are my notice period obligations?"\n• "What happens if I resign during probation?"\n• "Are there any non-compete restrictions?"',
  }])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const messagesEndRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const sendQuestion = useCallback(async (e) => {
    e.preventDefault()
    const question = input.trim()
    if (!question || isLoading) return

    const userMsg = { id: `user-${Date.now()}`, sender: 'user', text: question }
    setMessages(prev => [...prev, userMsg])
    setInput('')
    setIsLoading(true)

    try {
      const res = await fetch(`${API_BASE}/api/chat/${sessionId}/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question }),
      })

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Request failed' }))
        throw new Error(err.detail || `Error (${res.status})`)
      }

      const data = await res.json()
      const assistantMsg = {
        id: `assistant-${Date.now()}`,
        sender: 'assistant',
        text: data.answer,
        qaData: data,
      }
      setMessages(prev => [...prev, assistantMsg])
    } catch (err) {
      setMessages(prev => [...prev, {
        id: `error-${Date.now()}`,
        sender: 'assistant',
        text: `Sorry, I couldn't process your question: ${err.message}`,
        isError: true,
      }])
    } finally {
      setIsLoading(false)
      inputRef.current?.focus()
    }
  }, [input, isLoading, sessionId])

  const scrollToClause = useCallback((clauseId) => {
    const el = document.getElementById(`clause-${clauseId}`)
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' })
      const btn = el.querySelector('button[aria-expanded="false"]')
      if (btn) btn.click()
    }
  }, [])

  return (
    <section className="chat-panel" aria-labelledby="chat-heading">
      <header style={{ padding: 'var(--space-3) var(--space-4)', borderBottom: '1px solid var(--color-border)' }}>
        <h2 id="chat-heading" style={{ fontSize: 'var(--text-base)', fontWeight: 700 }}>
          💬 Document Q&A
        </h2>
      </header>

      {/* Message feed */}
      <div
        className="chat-messages"
        role="log"
        aria-live="polite"
        aria-label="Conversation history"
      >
        {messages.map((msg) => (
          <div key={msg.id} className={`message message-${msg.sender}`} role="article">
            <p>{msg.text}</p>
            {msg.qaData && <ResponseDisplay data={msg.qaData} onCitationClick={scrollToClause} />}
          </div>
        ))}

        {isLoading && (
          <div className="message message-assistant" role="status" aria-label="Analyzing your question">
            <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
              <div className="spinner" aria-hidden="true" />
              <span>Analyzing relevant clauses...</span>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <form className="chat-input-area" onSubmit={sendQuestion} role="search">
        <label htmlFor="chat-input" className="sr-only" style={{ position: 'absolute', width: '1px', height: '1px', overflow: 'hidden', clip: 'rect(0,0,0,0)' }}>
          Ask a question about the document
        </label>
        <input
          ref={inputRef}
          id="chat-input"
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about your contract..."
          disabled={isLoading}
          autoComplete="off"
          aria-label="Ask a question about the contract"
        />
        <button type="submit" disabled={isLoading || !input.trim()} aria-label="Send question">
          Send
        </button>
      </form>
    </section>
  )
}

/**
 * ResponseDisplay — Renders the three-way distinction and citations.
 * Efficiency: Memoized component.
 */
const ResponseDisplay = React.memo(function ResponseDisplay({ data, onCitationClick }) {
  const certaintyConfig = {
    stated: { label: '✓ Stated in Document', className: 'badge-stated' },
    interpreted: { label: '◐ Interpretation', className: 'badge-interpreted' },
    not_established: { label: '✗ Not Established', className: 'badge-not-established' },
  }

  const config = certaintyConfig[data.certainty] || certaintyConfig.not_established

  return (
    <div style={{ marginTop: 'var(--space-3)' }}>
      {/* Certainty badge */}
      <span className={`badge ${config.className}`} role="status">
        {config.label}
      </span>

      {/* Three-way distinction blocks */}
      {data.stated && (
        <div className="distinction-block distinction-stated" role="region" aria-label="What the document says">
          <strong>📗 What the document says:</strong>
          <p style={{ marginTop: 'var(--space-1)' }}>{data.stated}</p>
        </div>
      )}
      {data.interpreted && (
        <div className="distinction-block distinction-interpreted" role="region" aria-label="Interpretation">
          <strong>📙 Interpretation:</strong>
          <p style={{ marginTop: 'var(--space-1)' }}>{data.interpreted}</p>
        </div>
      )}
      {data.not_established && (
        <div className="distinction-block distinction-not-established" role="region" aria-label="Not established">
          <strong>📕 Not established:</strong>
          <p style={{ marginTop: 'var(--space-1)' }}>{data.not_established}</p>
        </div>
      )}

      {/* Source citations */}
      {data.sources && data.sources.length > 0 && (
        <div style={{ marginTop: 'var(--space-2)', display: 'flex', flexWrap: 'wrap', gap: 'var(--space-1)' }}>
          <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', marginRight: 'var(--space-1)' }}>
            Sources:
          </span>
          {data.sources.map((id) => (
            <button
              key={id}
              className="citation"
              onClick={() => onCitationClick(id)}
              aria-label={`View source clause ${id}`}
              type="button"
            >
              📍 {id}
            </button>
          ))}
        </div>
      )}

      {/* Lawyer question suggestion */}
      {data.lawyer_question && (
        <div style={{
          marginTop: 'var(--space-3)',
          padding: 'var(--space-2) var(--space-3)',
          background: 'var(--color-info-light)',
          borderRadius: 'var(--radius)',
          fontSize: 'var(--text-sm)',
        }} role="note" aria-label="Suggested lawyer question">
          <strong>💡 Ask your lawyer:</strong> {data.lawyer_question}
        </div>
      )}
    </div>
  )
})

export default React.memo(ChatPanel)
