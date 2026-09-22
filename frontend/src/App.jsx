import { useState } from 'react'
import './index.css'
import { API_BASE } from './apiConfig'
import FileUpload from './components/FileUpload'
import ClauseMap from './components/ClauseMap'
import ChatPanel from './components/ChatPanel'

/**
 * ClauseGuard — Main application component
 * 
 * Manages the core application state:
 * - sessionId: active document session
 * - clauses: extracted and categorized clauses
 * - activeTab: mobile view switching (clauses vs chat)
 */
function App() {
  const [sessionId, setSessionId] = useState(null)
  const [clauses, setClauses] = useState([])
  const [inconsistencies, setInconsistencies] = useState([])
  const [docInfo, setDocInfo] = useState(null)
  const [activeTab, setActiveTab] = useState('clauses')
  const [error, setError] = useState(null)

  const handleUploadSuccess = (data) => {
    setSessionId(data.session_id)
    setClauses(data.clauses)
    setDocInfo({
      filename: data.filename,
      doc_type: data.doc_type,
      total_pages: data.total_pages,
      total_clauses: data.total_clauses,
    })
    setError(null)

    // Fetch cross-clause inconsistencies asynchronously
    fetch(`${API_BASE}/api/documents/${data.session_id}/inconsistencies`)
      .then((res) => (res.ok ? res.json() : []))
      .then((items) => setInconsistencies(items))
      .catch(() => setInconsistencies([]))
  }

  const handleUploadError = (errMsg) => {
    setError(errMsg)
  }

  const handleDownloadBrief = async () => {
    if (!sessionId) return
    try {
      const res = await fetch(`${API_BASE}/api/documents/${sessionId}/brief`)
      if (!res.ok) throw new Error('Failed to generate brief')
      const text = await res.text()
      const blob = new Blob([text], { type: 'text/markdown' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'lawyer_prep_brief.md'
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      setError('Failed to generate lawyer prep brief')
    }
  }

  return (
    <>
      {/* Accessibility: Skip to main content link */}
      <a href="#main-content" className="skip-link">
        Skip to main content
      </a>

      <header className="app-header">
        <h1>
          <span aria-hidden="true">🛡️</span> ClauseGuard
        </h1>
        {sessionId && (
          <button className="btn btn-outline" onClick={handleDownloadBrief}>
            📋 Generate Lawyer Brief
          </button>
        )}
      </header>

      {/* Mobile tab switcher */}
      {sessionId && (
        <nav className="mobile-tabs" aria-label="Mobile View Selection">
          <button
            className={`mobile-tab ${activeTab === 'clauses' ? 'active' : ''}`}
            onClick={() => setActiveTab('clauses')}
            aria-pressed={activeTab === 'clauses'}
          >
            📋 Clauses
          </button>
          <button
            className={`mobile-tab ${activeTab === 'chat' ? 'active' : ''}`}
            onClick={() => setActiveTab('chat')}
            aria-pressed={activeTab === 'chat'}
          >
            💬 Q&A Chat
          </button>
        </nav>
      )}

      <main id="main-content" className="app-main">
        {error && (
          <div className="error-message" role="alert">
            <strong>Error:</strong> {error}
            <button
              onClick={() => setError(null)}
              style={{ marginLeft: '1rem', background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline', color: 'inherit' }}
              aria-label="Dismiss error"
            >
              Dismiss
            </button>
          </div>
        )}

        {/* Left column: Upload + Clause Map */}
        <section
          aria-label="Document analysis"
          style={{ display: activeTab === 'clauses' || window.innerWidth > 768 ? 'block' : 'none' }}
        >
          {!sessionId ? (
            <FileUpload onSuccess={handleUploadSuccess} onError={handleUploadError} />
          ) : (
            <ClauseMap clauses={clauses} docInfo={docInfo} sessionId={sessionId} inconsistencies={inconsistencies} />
          )}
        </section>

        {/* Right column: Chat */}
        {sessionId && (
          <aside
            aria-label="Document Q&A"
            style={{ display: activeTab === 'chat' || window.innerWidth > 768 ? 'block' : 'none' }}
          >
            <ChatPanel sessionId={sessionId} clauses={clauses} />
          </aside>
        )}

        {/* Show placeholder when no document is uploaded and on chat tab */}
        {!sessionId && (
          <section aria-label="Chat placeholder" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div style={{ textAlign: 'center', color: 'var(--color-text-muted)' }}>
              <p style={{ fontSize: 'var(--text-lg)', marginBottom: 'var(--space-2)' }}>💬 Document Q&A</p>
              <p>Upload a document to start asking questions</p>
            </div>
          </section>
        )}
      </main>
    </>
  )
}

export default App
