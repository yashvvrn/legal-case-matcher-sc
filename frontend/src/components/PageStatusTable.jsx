/**
 * PageStatusTable — Tabular view of per-page processing results.
 *
 * Props:
 *   pages         — array of page objects from the job
 *   onReviewClick — called with page object when a "needs_review" row is clicked
 */
export default function PageStatusTable({ pages, onReviewClick }) {
  if (!pages || pages.length === 0) return null

  function MethodCell({ method }) {
    if (method === 'direct_parse') {
      return <span className="badge badge-parse">Direct Parse</span>
    }
    return <span className="badge badge-ocr">OCR</span>
  }

  function StatusCell({ page }) {
    if (page.error) {
      return (
        <span className="status-pill error" title={page.error}>
          ⚠ Error
        </span>
      )
    }
    if (page.status === 'needs_review') {
      return (
        <span className="status-pill needs-review">
          ⚑ Needs Review
        </span>
      )
    }
    return (
      <span className="status-pill passed">
        ✓ Passed
      </span>
    )
  }

  function ConfidenceCell({ page }) {
    if (page.method === 'direct_parse') {
      return <span className="muted">—</span>
    }
    if (page.confidence_display) {
      return <span>{page.confidence_display}</span>
    }
    return <span className="muted">N/A</span>
  }

  return (
    <div className="panel">
      <div className="panel-title">Page Results</div>
      <table className="status-table" role="table" aria-label="Page processing results">
        <thead>
          <tr>
            <th>Page</th>
            <th>Method</th>
            <th>Confidence</th>
            <th>Status</th>
            <th>Reviewed</th>
          </tr>
        </thead>
        <tbody>
          {pages.map((page) => {
            const isReview = page.status === 'needs_review'
            const rowCls = isReview ? 'review-row' : 'passed-row'
            return (
              <tr
                key={page.page_number}
                className={rowCls}
                onClick={isReview ? () => onReviewClick(page) : undefined}
                title={isReview ? 'Click to open review panel' : undefined}
                role={isReview ? 'button' : undefined}
                tabIndex={isReview ? 0 : undefined}
                onKeyDown={isReview
                  ? (e) => e.key === 'Enter' && onReviewClick(page)
                  : undefined}
              >
                <td>{page.page_number}</td>
                <td><MethodCell method={page.method} /></td>
                <td><ConfidenceCell page={page} /></td>
                <td><StatusCell page={page} /></td>
                <td>
                  {page.reviewed
                    ? <span className="reviewed-tag">✓ reviewed</span>
                    : <span className="muted">—</span>}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
