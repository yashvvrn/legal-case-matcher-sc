import { useState, useEffect, useCallback, useRef } from 'react'
import { uploadPDF, getJob } from './api'
import UploadPanel from './components/UploadPanel'
import JobStatus from './components/JobStatus'
import PageStatusTable from './components/PageStatusTable'
import TextViewer from './components/TextViewer'
import ReviewModal from './components/ReviewModal'
import RasterizePanel from './components/RasterizePanel'

const POLL_INTERVAL_MS = 1500

export default function App() {
  const [job, setJob] = useState(null)
  const [uploadedFile, setUploadedFile] = useState(null)
  const [error, setError] = useState(null)
  const [processing, setProcessing] = useState(false)
  const [reviewPage, setReviewPage] = useState(null)  // page object to review
  const pollRef = useRef(null)

  // -----------------------------------------------------------------------
  // Polling
  // -----------------------------------------------------------------------

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }, [])

  const startPolling = useCallback((jobId) => {
    stopPolling()
    pollRef.current = setInterval(async () => {
      try {
        const data = await getJob(jobId)
        setJob(data)
        if (data.status === 'done' || data.status === 'failed') {
          stopPolling()
          setProcessing(false)
        }
      } catch (e) {
        setError(`Failed to fetch job status: ${e.message}`)
        stopPolling()
        setProcessing(false)
      }
    }, POLL_INTERVAL_MS)
  }, [stopPolling])

  useEffect(() => () => stopPolling(), [stopPolling])

  // -----------------------------------------------------------------------
  // Upload + start job
  // -----------------------------------------------------------------------

  async function handleUpload(file, engine = 'openocr') {
    setError(null)
    setJob(null)
    setUploadedFile(file)
    setProcessing(true)
    try {
      const { job_id } = await uploadPDF(file, engine)
      // Immediately fetch first state
      const initial = await getJob(job_id)
      setJob(initial)
      startPolling(job_id)
    } catch (e) {
      setError(e.message)
      setProcessing(false)
    }
  }

  // -----------------------------------------------------------------------
  // Review
  // -----------------------------------------------------------------------

  function handleReviewClick(page) {
    setReviewPage(page)
  }

  function handleReviewClose() {
    setReviewPage(null)
  }

  async function handleReviewed() {
    // Refresh job to pick up updated page status
    if (job?.job_id) {
      try {
        const data = await getJob(job.job_id)
        setJob(data)
      } catch (_) {}
    }
  }

  // -----------------------------------------------------------------------
  // Render
  // -----------------------------------------------------------------------

  const isDone = job?.status === 'done'
  const isFailed = job?.status === 'failed'

  return (
    <div className="app">
      {/* Page header */}
      <header className="page-header">
        <h1>Document OCR</h1>
        <p>Extract text from native and scanned PDF documents.</p>
      </header>

      {/* Global error */}
      {error && (
        <div className="alert alert-error" role="alert">
          <strong>Error:</strong> {error}
          <button
            style={{ marginLeft: 12, background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline', fontSize: 13 }}
            onClick={() => setError(null)}
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Upload */}
      <UploadPanel onSubmit={handleUpload} disabled={processing} />

      {/* Job status / progress */}
      {job && <JobStatus job={job} />}

      {/* Rasterize tool — shown only for native-text PDFs */}
      {isDone && job.processing_method === 'direct_parse' && (
        <RasterizePanel file={uploadedFile} />
      )}

      {/* Page results table */}
      {isDone && job.pages.length > 0 && (
        <PageStatusTable
          pages={job.pages}
          onReviewClick={handleReviewClick}
        />
      )}

      {/* Extracted text viewer */}
      {isDone && job.pages.length > 0 && (
        <TextViewer
          jobId={job.job_id}
          pages={job.pages}
          summary={job.comparison_summary}
          engine={job.engine}
        />
      )}

      {/* Review modal */}
      {reviewPage && (
        <ReviewModal
          jobId={job.job_id}
          page={reviewPage}
          onClose={handleReviewClose}
          onReviewed={handleReviewed}
        />
      )}
    </div>
  )
}
