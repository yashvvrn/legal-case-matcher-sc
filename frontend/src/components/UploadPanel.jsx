import { useState, useRef } from 'react'

/**
 * UploadPanel — PDF file picker with drag-and-drop support.
 *
 * Props:
 *   onSubmit(file) — called when user clicks "Process Document"
 *   disabled       — disables interaction while a job runs
 */
export default function UploadPanel({ onSubmit, disabled }) {
  const [file, setFile] = useState(null)
  const [engine, setEngine] = useState('openocr')
  const [dragOver, setDragOver] = useState(false)
  const inputRef = useRef(null)

  function handleFiles(files) {
    const f = files[0]
    if (f && f.type === 'application/pdf') {
      setFile(f)
    } else if (f) {
      alert('Please select a PDF file.')
    }
  }

  function handleDrop(e) {
    e.preventDefault()
    setDragOver(false)
    handleFiles(e.dataTransfer.files)
  }

  function handleSubmit() {
    if (file && !disabled) onSubmit(file, engine)
  }

  return (
    <div className="panel">
      <div className="panel-title">Upload Document</div>

      {/* Drop zone */}
      <div
        className={`upload-area${dragOver ? ' drag-over' : ''}`}
        onClick={() => !disabled && inputRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => e.key === 'Enter' && inputRef.current?.click()}
        aria-label="PDF upload area"
      >
        <span className="upload-icon">📄</span>
        <div className="upload-label">
          <strong>Choose PDF</strong> or drag and drop here
        </div>
        <div className="upload-hint">PDF files only · Max 100 MB</div>
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf"
          onChange={(e) => handleFiles(e.target.files)}
          id="pdf-file-input"
        />
      </div>

      {/* Selected file */}
      {file && (
        <div className="selected-file">
          <span>📎</span>
          <span className="file-name">{file.name}</span>
          <span className="muted" style={{ fontSize: 12 }}>
            ({(file.size / 1024 / 1024).toFixed(1)} MB)
          </span>
          <button
            className="remove-btn"
            onClick={(e) => { e.stopPropagation(); setFile(null) }}
            aria-label="Remove selected file"
            title="Remove"
          >
            ×
          </button>
        </div>
      )}

      {/* Engine Selection */}
      <div className="engine-selector-container">
        <span className="engine-selector-label">OCR Engine:</span>
        <div className="engine-button-group">
          <button
            type="button"
            className={`engine-btn ${engine === 'openocr' ? 'active' : ''}`}
            onClick={() => setEngine('openocr')}
            disabled={disabled}
          >
            OpenOCR
          </button>
          <button
            type="button"
            className={`engine-btn ${engine === 'paddleocr' ? 'active' : ''}`}
            onClick={() => setEngine('paddleocr')}
            disabled={disabled}
          >
            PaddleOCR
          </button>
          <button
            type="button"
            className={`engine-btn ${engine === 'compare' ? 'active' : ''}`}
            onClick={() => setEngine('compare')}
            disabled={disabled}
          >
            Compare Both
          </button>
        </div>
      </div>

      {/* Submit */}
      <div className="actions-row">
        <button
          className="btn btn-primary"
          onClick={handleSubmit}
          disabled={!file || disabled}
          id="process-btn"
        >
          {disabled ? (
            <><span className="spinner" /> Processing…</>
          ) : (
            `Process with ${engine === 'compare' ? 'A/B Comparison' : engine === 'paddleocr' ? 'PaddleOCR' : 'OpenOCR'}`
          )}
        </button>
        {!file && (
          <span className="muted" style={{ fontSize: 12 }}>
            Select a PDF to get started.
          </span>
        )}
      </div>
    </div>
  )
}
