import { useState, useEffect } from 'react'
import { rasterizePDF } from '../api'

const DPI_OPTIONS = [
  { value: 150, label: '150 DPI — smaller file, faster' },
  { value: 200, label: '200 DPI — balanced (recommended)' },
  { value: 300, label: '300 DPI — high quality, larger file' },
]

/**
 * RasterizePanel — shown when processing_method is "direct_parse".
 * Lets the user re-render the PDF as an image-only PDF to test OCR.
 *
 * Props:
 *   file — the original File object that was uploaded
 */
export default function RasterizePanel({ file }) {
  const [dpi, setDpi] = useState(200)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)   // { blobUrl, filename }

  // Revoke blob URL when panel unmounts or a new result is generated
  useEffect(() => {
    return () => {
      if (result?.blobUrl) URL.revokeObjectURL(result.blobUrl)
    }
  }, [result])

  async function handleRasterize() {
    if (!file) return
    setLoading(true)
    setError(null)
    if (result?.blobUrl) URL.revokeObjectURL(result.blobUrl)
    setResult(null)
    try {
      const r = await rasterizePDF(file, dpi)
      setResult(r)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  if (!file) return null

  return (
    <div className="panel rasterize-panel">
      <div className="panel-title">Rasterize PDF</div>
      <p className="rasterize-desc">
        This document was parsed directly — no OCR was needed. To test OCR on it,
        rasterize it first: each page is rendered to an image and packed into a
        new PDF with no text layer.
      </p>

      <div className="rasterize-controls">
        <div className="rasterize-field">
          <label className="field-label" htmlFor="dpi-select">Render quality</label>
          <select
            id="dpi-select"
            className="dpi-select"
            value={dpi}
            onChange={(e) => setDpi(Number(e.target.value))}
            disabled={loading}
          >
            {DPI_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </div>

        <button
          className="btn btn-secondary"
          onClick={handleRasterize}
          disabled={loading}
          id="rasterize-btn"
        >
          {loading
            ? <><span className="spinner spinner-dark" /> Rasterizing…</>
            : 'Rasterize & Download'}
        </button>
      </div>

      {error && (
        <div className="alert alert-error" style={{ marginTop: 12 }}>
          {error}
        </div>
      )}

      {result && (
        <div className="rasterize-result">
          <span className="rasterize-ok">✓</span>
          <span>Ready:</span>
          <a
            href={result.blobUrl}
            download={result.filename}
            className="btn btn-primary btn-sm"
            id="download-rasterized-btn"
          >
            Download {result.filename}
          </a>
          <span className="muted" style={{ fontSize: 12 }}>
            Upload this file back to test OCR.
          </span>
        </div>
      )}
    </div>
  )
}
