import { useState, useEffect } from 'react'
import { getPageDetail, markReviewed, updatePageText } from '../api'

/**
 * ReviewModal — Manual review panel for a single OCR page.
 *
 * Shows:
 *   - Rendered page image
 *   - Editable OCR text
 *   - Confidence + current status
 *   - "Mark as Reviewed" and "Save Text" buttons
 *
 * Props:
 *   jobId         — job ID
 *   page          — page summary object (from PageStatusTable)
 *   onClose()     — close callback
 *   onReviewed()  — called after successful review action (to refresh parent)
 */
export default function ReviewModal({ jobId, page, onClose, onReviewed }) {
  const [detail, setDetail] = useState(null)
  const [editedText, setEditedText] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [savedMsg, setSavedMsg] = useState(null)

  // Load full page detail (including image)
  useEffect(() => {
    if (!page) return
    setLoading(true)
    setError(null)
    getPageDetail(jobId, page.page_number)
      .then((d) => {
        setDetail(d)
        setEditedText(d.text || '')
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [jobId, page?.page_number])

  // Close on Escape
  useEffect(() => {
    function onKey(e) {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  async function handleMarkReviewed() {
    setSaving(true)
    setError(null)
    try {
      await markReviewed(jobId, page.page_number)
      setSavedMsg('Page marked as reviewed.')
      onReviewed()
    } catch (e) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  async function handleSaveText() {
    setSaving(true)
    setError(null)
    try {
      await updatePageText(jobId, page.page_number, editedText)
      setSavedMsg('Text saved.')
      onReviewed()
    } catch (e) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  if (!page) return null

  return (
    <div
      className="modal-overlay"
      onClick={(e) => e.target === e.currentTarget && onClose()}
      role="dialog"
      aria-modal="true"
      aria-label={`Review page ${page.page_number}`}
    >
      <div className="modal">
        {/* Header */}
        <div className="modal-header">
          <div>
            <h2>Review — Page {page.page_number}</h2>
            <div className="modal-meta" style={{ marginTop: 4 }}>
              <span>
                Confidence:{' '}
                <strong>
                  {page.confidence_display || 'N/A'}
                </strong>
              </span>
              <span>
                Status:{' '}
                <strong style={{ color: page.status === 'needs_review' ? '#854d0e' : '#166534' }}>
                  {page.status === 'needs_review' ? 'Needs Review' : 'Passed'}
                </strong>
              </span>
              {detail?.reviewed && (
                <span className="reviewed-tag">✓ Manually reviewed</span>
              )}
            </div>
          </div>
          <button className="close-btn" onClick={onClose} aria-label="Close review panel">×</button>
        </div>

        {/* Error */}
        {error && (
          <div className="alert alert-error" style={{ marginBottom: 16 }}>
            {error}
          </div>
        )}
        {savedMsg && (
          <div className="alert alert-info" style={{ marginBottom: 16 }}>
            {savedMsg}
          </div>
        )}

        {loading ? (
          <div style={{ padding: '40px 0', textAlign: 'center', color: 'var(--text-muted)' }}>
            <span className="spinner spinner-dark" style={{ marginRight: 8 }} />
            Loading page…
          </div>
        ) : (
          <>
            <div className="modal-body">
              {/* Page image */}
              <div>
                <div className="modal-section-title">Rendered Page</div>
                <div className="page-image-wrap">
                  {detail?.image_base64 ? (
                    <img
                      src={`data:image/png;base64,${detail.image_base64}`}
                      alt={`Rendered page ${page.page_number}`}
                    />
                  ) : (
                    <div className="no-image">
                      Image not available
                    </div>
                  )}
                </div>
              </div>

              {/* OCR text editor */}
              <div>
                <div className="modal-section-title">
                  OCR Text{' '}
                  <span className="muted" style={{ fontStyle: 'normal', textTransform: 'none', fontSize: 11 }}>
                    (editable)
                  </span>
                </div>
                <textarea
                  className="ocr-text-editor"
                  value={editedText}
                  onChange={(e) => setEditedText(e.target.value)}
                  aria-label="OCR text editor"
                  id="ocr-text-area"
                  placeholder="No text was extracted for this page."
                />
              </div>
            </div>

            {/* Footer */}
            <div className="modal-footer">
              <button
                className="btn btn-primary"
                onClick={handleMarkReviewed}
                disabled={saving}
                id="mark-reviewed-btn"
              >
                {saving ? <><span className="spinner" /> Saving…</> : 'Mark as Reviewed'}
              </button>
              <button
                className="btn btn-secondary"
                onClick={handleSaveText}
                disabled={saving}
                id="save-text-btn"
              >
                Save Text
              </button>
              <div className="spacer" />
              <button className="btn btn-secondary" onClick={onClose}>
                Close
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
