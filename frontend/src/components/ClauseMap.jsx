import { useState } from 'react'

/**
 * ClauseMap — Categorized clause cards with expandable details.
 * 
 * Groups clauses by category, showing plain-English explanations
 * and original text with page references. Each card is expandable
 * using accessible accordion pattern (aria-expanded, aria-controls).
 */
export default function ClauseMap({ clauses, docInfo }) {
  // Group clauses by category
  const grouped = {}
  for (const clause of clauses) {
    const cat = clause.category || 'general'
    if (!grouped[cat]) grouped[cat] = []
    grouped[cat].push(clause)
  }

  const categoryLabels = {
    compensation: '💰 Compensation',
    termination: '🚪 Termination',
    notice_period: '📅 Notice Period',
    probation: '⏱️ Probation',
    non_compete: '🚫 Non-Compete',
    confidentiality: '🔒 Confidentiality',
    liability: '⚖️ Liability',
    intellectual_property: '💡 Intellectual Property',
    dispute_resolution: '🤝 Dispute Resolution',
    governing_law: '📜 Governing Law',
    benefits: '🎁 Benefits',
    obligations: '📋 Obligations',
    restrictions: '🔐 Restrictions',
    indemnification: '🛡️ Indemnification',
    general: '📄 General',
  }

  return (
    <section aria-labelledby="clause-map-heading">
      <div style={{ marginBottom: 'var(--space-4)' }}>
        <h2 id="clause-map-heading" style={{ fontSize: 'var(--text-xl)', marginBottom: 'var(--space-2)' }}>
          Clause Map
        </h2>
        {docInfo && (
          <p style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-secondary)' }}>
            <strong>{docInfo.filename}</strong> — {docInfo.doc_type?.replace(/_/g, ' ')} • {docInfo.total_pages} pages • {docInfo.total_clauses} clauses
          </p>
        )}
      </div>

      {Object.entries(grouped).map(([category, categoryClauses]) => (
        <div key={category} style={{ marginBottom: 'var(--space-6)' }}>
          <h3 style={{ fontSize: 'var(--text-lg)', marginBottom: 'var(--space-3)', display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
            {categoryLabels[category] || `📄 ${category.replace(/_/g, ' ')}`}
            <span className="badge badge-category">{categoryClauses.length}</span>
          </h3>
          {categoryClauses.map((clause) => (
            <ClauseCard key={clause.id} clause={clause} />
          ))}
        </div>
      ))}
    </section>
  )
}

function ClauseCard({ clause }) {
  const [expanded, setExpanded] = useState(false)
  const contentId = `clause-content-${clause.id}`

  return (
    <article className="clause-card" id={`clause-${clause.id}`}>
      <button
        type="button"
        className="clause-card-header"
        aria-expanded={expanded}
        aria-controls={contentId}
        onClick={() => setExpanded(!expanded)}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', flex: 1 }}>
          <span className="badge badge-category">
            {clause.category?.replace(/_/g, ' ') || 'general'}
          </span>
          <span style={{ fontWeight: 600, fontSize: 'var(--text-sm)' }}>
            {clause.section}
          </span>
        </div>
        <span className="page-ref">p.{clause.page}</span>
        <span aria-hidden="true" style={{ fontSize: 'var(--text-xs)' }}>
          {expanded ? '▲' : '▼'}
        </span>
      </button>

      {expanded && (
        <div id={contentId} className="clause-card-body">
          {/* Plain-English explanation */}
          {clause.plain_explanation && (
            <div style={{ marginBottom: 'var(--space-3)' }}>
              <strong style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-secondary)' }}>
                In plain English:
              </strong>
              <p style={{ marginTop: 'var(--space-1)', fontSize: 'var(--text-sm)' }}>
                {clause.plain_explanation}
              </p>
            </div>
          )}

          {/* Original clause text */}
          <div>
            <strong style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-secondary)' }}>
              Original text (Page {clause.page}):
            </strong>
            <blockquote className="original-text">
              {clause.text}
            </blockquote>
          </div>

          <div style={{ marginTop: 'var(--space-2)', fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>
            ID: {clause.id} • Page {clause.page}
          </div>
        </div>
      )}
    </article>
  )
}
