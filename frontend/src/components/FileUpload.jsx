import { useState, useRef } from 'react'

/**
 * FileUpload — Drag-and-drop file upload with validation feedback.
 * 
 * Accessibility:
 * - Keyboard navigable (label wraps hidden file input)
 * - aria-live region for status announcements
 * - Clear error states with actionable messages
 */
export default function FileUpload({ onSuccess, onError }) {
  const [isDragging, setIsDragging] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [statusMsg, setStatusMsg] = useState('')
  const fileInputRef = useRef(null)

  const MAX_SIZE_MB = 10
  const ALLOWED_TYPES = ['.pdf', '.docx']

  const validateFile = (file) => {
    if (!file) return 'No file selected'
    
    const ext = file.name.split('.').pop()?.toLowerCase()
    if (!ALLOWED_TYPES.includes(`.${ext}`)) {
      return `Unsupported file type (.${ext}). Only PDF and DOCX files are accepted.`
    }
    
    if (file.size > MAX_SIZE_MB * 1024 * 1024) {
      return `File exceeds ${MAX_SIZE_MB}MB size limit.`
    }
    
    return null
  }

  const uploadFile = async (file) => {
    const validationError = validateFile(file)
    if (validationError) {
      setStatusMsg(validationError)
      onError?.(validationError)
      return
    }

    setIsUploading(true)
    setStatusMsg(`Uploading and analyzing "${file.name}"... This may take a moment.`)

    try {
      const formData = new FormData()
      formData.append('file', file)

      const res = await fetch('/api/documents/upload', {
        method: 'POST',
        body: formData,
      })

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Upload failed' }))
        throw new Error(err.detail || `Server error (${res.status})`)
      }

      const data = await res.json()
      setStatusMsg(`✓ Analyzed "${file.name}": ${data.total_clauses} clauses found across ${data.total_pages} pages.`)
      onSuccess?.(data)
    } catch (err) {
      const msg = err.message || 'Upload failed. Please try again.'
      setStatusMsg(`Error: ${msg}`)
      onError?.(msg)
    } finally {
      setIsUploading(false)
    }
  }

  const handleDrop = (e) => {
    e.preventDefault()
    setIsDragging(false)
    const file = e.dataTransfer?.files?.[0]
    if (file) uploadFile(file)
  }

  const handleFileSelect = (e) => {
    const file = e.target.files?.[0]
    if (file) uploadFile(file)
  }

  return (
    <section aria-labelledby="upload-heading">
      <h2 id="upload-heading" style={{ marginBottom: 'var(--space-4)', fontSize: 'var(--text-xl)' }}>
        Upload Legal Document
      </h2>
      <p style={{ marginBottom: 'var(--space-4)', color: 'var(--color-text-secondary)', fontSize: 'var(--text-sm)' }}>
        Upload a contract or legal document (PDF or DOCX, up to 10MB) to analyze its clauses,
        get plain-English explanations, and ask questions.
      </p>

      {/* Drop zone */}
      <label
        htmlFor="doc-upload"
        className={`upload-area ${isDragging ? 'dragging' : ''}`}
        onDragOver={(e) => { e.preventDefault(); setIsDragging(true) }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={handleDrop}
        style={{ position: 'relative' }}
      >
        {isUploading ? (
          <div>
            <div className="spinner" style={{ marginBottom: 'var(--space-3)' }} />
            <p style={{ fontWeight: 600 }}>Analyzing document...</p>
            <p style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)', marginTop: 'var(--space-2)' }}>
              Extracting clauses, categorizing, and generating explanations
            </p>
          </div>
        ) : (
          <div>
            <span style={{ fontSize: '2rem' }} aria-hidden="true">📄</span>
            <p style={{ fontWeight: 600, marginTop: 'var(--space-2)' }}>
              Drag & drop your contract here
            </p>
            <p style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)', marginTop: 'var(--space-1)' }}>
              or <span style={{ color: 'var(--color-primary)', textDecoration: 'underline' }}>browse files</span>
            </p>
            <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', marginTop: 'var(--space-2)' }}>
              PDF or DOCX • Up to 10MB
            </p>
          </div>
        )}
        <input
          ref={fileInputRef}
          id="doc-upload"
          type="file"
          accept=".pdf,.docx"
          onChange={handleFileSelect}
          disabled={isUploading}
          aria-describedby="upload-status"
        />
      </label>

      {/* Status announcement — aria-live for screen readers */}
      <div
        id="upload-status"
        role="status"
        aria-live="polite"
        style={{
          marginTop: 'var(--space-3)',
          fontSize: 'var(--text-sm)',
          color: statusMsg.startsWith('Error') ? 'var(--color-danger)' : 'var(--color-text-secondary)'
        }}
      >
        {statusMsg}
      </div>
    </section>
  )
}
