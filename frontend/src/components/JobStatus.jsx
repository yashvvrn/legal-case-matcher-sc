/**
 * JobStatus — Shows processing progress while the job is running,
 * and document summary once done.
 *
 * Props:
 *   job   — job object from GET /api/jobs/{id}
 */
export default function JobStatus({ job }) {
  if (!job) return null

  const isDone = job.status === 'done'
  const isFailed = job.status === 'failed'
  const isProcessing = job.status === 'processing' || job.status === 'queued'

  // Progress
  const progress = job.progress
  const progressPct = progress
    ? Math.round((progress.page_number / progress.total_pages) * 100)
    : 0

  // Method badge
  function MethodBadge({ method }) {
    if (!method) return <span className="muted">—</span>
    const map = {
      direct_parse: ['badge-parse', 'Direct Parse'],
      ocr:          ['badge-ocr', 'OCR'],
      hybrid:       ['badge-hybrid', 'Hybrid'],
    }
    const [cls, label] = map[method] || ['', method]
    return <span className={`badge ${cls}`}>{label}</span>
  }

  return (
    <div className="panel">
      <div className="panel-title">
        {isProcessing ? 'Processing' : isFailed ? 'Processing Failed' : 'Document Info'}
      </div>

      {/* Error state */}
      {isFailed && (
        <div className="alert alert-error">
          <strong>Error:</strong> {job.error || 'An unexpected error occurred.'}
        </div>
      )}

      {/* Progress bar */}
      {isProcessing && (
        <div className="progress-wrap">
          <div className="progress-bar-track">
            <div
              className="progress-bar-fill"
              style={{ width: `${Math.max(progressPct, 5)}%` }}
            />
          </div>
          <div className="progress-label">
            {progress ? progress.message : 'Queued…'}
          </div>
        </div>
      )}

      {/* Document info — shown once done */}
      {isDone && (
        <div className="doc-info">
          <div className="doc-info-item">
            <span className="label">Filename</span>
            <span className="value mono">{job.filename}</span>
          </div>
          <div className="doc-info-item">
            <span className="label">Pages</span>
            <span className="value">{job.page_count}</span>
          </div>
          <div className="doc-info-item">
            <span className="label">Processing Method</span>
            <span className="value">
              <MethodBadge method={job.processing_method} />
            </span>
          </div>
          <div className="doc-info-item">
            <span className="label">Processing Time</span>
            <span className="value">
              {job.processing_time_seconds != null
                ? `${job.processing_time_seconds.toFixed(2)}s`
                : '—'}
            </span>
          </div>
          <div className="doc-info-item">
            <span className="label">Review Threshold</span>
            <span className="value">{job.review_threshold}%</span>
          </div>
          <div className="doc-info-item">
            <span className="label">Needs Review</span>
            <span className="value">
              {job.pages.filter(p => p.status === 'needs_review').length} page(s)
            </span>
          </div>
        </div>
      )}
    </div>
  )
}
