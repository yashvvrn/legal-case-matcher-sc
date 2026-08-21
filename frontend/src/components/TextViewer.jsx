import { useState, useRef } from 'react'
import { exportTxtUrl, exportJsonUrl } from '../api'

/**
 * TextViewer — Displays extracted text, multi-engine comparison, 3 output layers,
 * metrics summary, and raw JSON export options.
 */
export default function TextViewer({ jobId, pages, summary, engine }) {
  const [viewMode, setViewMode] = useState(engine === 'compare' ? 'side_by_side' : 'single')
  const [singleEngine, setSingleEngine] = useState(engine === 'paddleocr' ? 'paddleocr' : 'openocr')
  const [textLayer, setTextLayer] = useState('final_text') // 'raw_text' | 'geometry_text' | 'final_text'
  const viewerRef = useRef(null)

  if (!pages || pages.length === 0) return null

  const isComparisonMode = engine === 'compare' || pages.some(p => p.comparison_data)

  function getPageLayerText(pageObj, engineKey, layerKey) {
    if (!pageObj) return ''
    if (pageObj.comparison_data && pageObj.comparison_data[engineKey]) {
      const engData = pageObj.comparison_data[engineKey]
      return engData[layerKey] || engData.final_text || engData.text || ''
    }
    return pageObj[layerKey] || pageObj.text || ''
  }

  function buildFullText() {
    return pages.map((page) => {
      const sepBase = `${'='.repeat(16)} PAGE ${page.page_number} ${'='.repeat(16)}`
      const sep = page.status === 'needs_review' ? `${sepBase}  [NEEDS REVIEW]` : sepBase
      let body = ''
      if (viewMode === 'side_by_side') {
        const openTxt = getPageLayerText(page, 'openocr', textLayer)
        const paddleTxt = getPageLayerText(page, 'paddleocr', textLayer)
        body = `--- OPENOCR ---\n${openTxt}\n\n--- PADDLEOCR ---\n${paddleTxt}`
      } else {
        body = getPageLayerText(page, singleEngine, textLayer)
      }
      return `${sep}\n\n${body}`
    }).join('\n\n')
  }

  async function copyText() {
    const text = buildFullText()
    try {
      await navigator.clipboard.writeText(text)
    } catch (_) {
      const ta = document.createElement('textarea')
      ta.value = text
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      document.body.removeChild(ta)
    }
  }

  return (
    <div className="panel section-gap">
      <div className="panel-header-row">
        <div className="panel-title">Extracted Text & OCR Engine Inspection</div>
      </div>

      {/* Comparison Metrics Summary */}
      {summary && summary.openocr_metrics && summary.paddleocr_metrics && (
        <div className="metrics-comparison-container">
          <div className="metrics-card openocr-card">
            <div className="metrics-card-header">OpenOCR Metrics</div>
            <div className="metrics-grid">
              <div className="metric-item">
                <span className="metric-label">Total Time:</span>
                <span className="metric-val">{summary.openocr_metrics.total_processing_time_seconds}s</span>
              </div>
              <div className="metric-item">
                <span className="metric-label">Avg Time / Page:</span>
                <span className="metric-val">{summary.openocr_metrics.avg_time_per_page_seconds}s</span>
              </div>
              <div className="metric-item">
                <span className="metric-label">Avg Confidence:</span>
                <span className="metric-val">{summary.openocr_metrics.avg_confidence ? `${summary.openocr_metrics.avg_confidence}%` : 'N/A'}</span>
              </div>
              <div className="metric-item">
                <span className="metric-label">Words / Chars:</span>
                <span className="metric-val">{summary.openocr_metrics.total_words} / {summary.openocr_metrics.total_chars}</span>
              </div>
            </div>
          </div>

          <div className="metrics-card paddleocr-card">
            <div className="metrics-card-header">PaddleOCR Metrics</div>
            <div className="metrics-grid">
              <div className="metric-item">
                <span className="metric-label">Total Time:</span>
                <span className="metric-val">{summary.paddleocr_metrics.total_processing_time_seconds}s</span>
              </div>
              <div className="metric-item">
                <span className="metric-label">Avg Time / Page:</span>
                <span className="metric-val">{summary.paddleocr_metrics.avg_time_per_page_seconds}s</span>
              </div>
              <div className="metric-item">
                <span className="metric-label">Avg Confidence:</span>
                <span className="metric-val">{summary.paddleocr_metrics.avg_confidence ? `${summary.paddleocr_metrics.avg_confidence}%` : 'N/A'}</span>
              </div>
              <div className="metric-item">
                <span className="metric-label">Words / Chars:</span>
                <span className="metric-val">{summary.paddleocr_metrics.total_words} / {summary.paddleocr_metrics.total_chars}</span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Control Tabs Bar */}
      <div className="text-viewer-toolbar">
        {/* View Mode Tabs */}
        {isComparisonMode && (
          <div className="tab-group">
            <button
              className={`tab-btn ${viewMode === 'side_by_side' ? 'active' : ''}`}
              onClick={() => setViewMode('side_by_side')}
            >
              Side-by-Side
            </button>
            <button
              className={`tab-btn ${viewMode === 'single' && singleEngine === 'openocr' ? 'active' : ''}`}
              onClick={() => { setViewMode('single'); setSingleEngine('openocr'); }}
            >
              OpenOCR
            </button>
            <button
              className={`tab-btn ${viewMode === 'single' && singleEngine === 'paddleocr' ? 'active' : ''}`}
              onClick={() => { setViewMode('single'); setSingleEngine('paddleocr'); }}
            >
              PaddleOCR
            </button>
            <button
              className={`tab-btn ${viewMode === 'raw_json' ? 'active' : ''}`}
              onClick={() => setViewMode('raw_json')}
            >
              Raw JSON
            </button>
          </div>
        )}

        {/* Text Layer Selector */}
        {viewMode !== 'raw_json' && (
          <div className="layer-selector-group">
            <span className="layer-label">Layer:</span>
            <button
              className={`layer-btn ${textLayer === 'raw_text' ? 'active' : ''}`}
              onClick={() => setTextLayer('raw_text')}
              title="1. RAW OCR text before post-processing"
            >
              Raw OCR
            </button>
            <button
              className={`layer-btn ${textLayer === 'geometry_text' ? 'active' : ''}`}
              onClick={() => setTextLayer('geometry_text')}
              title="2. Spatial Bounding Box Geometry Reconstructed Text"
            >
              Geometry Reconstruction
            </button>
            <button
              className={`layer-btn ${textLayer === 'final_text' ? 'active' : ''}`}
              onClick={() => setTextLayer('final_text')}
              title="3. Final Clean Text with legal formatting"
            >
              Final Clean Text
            </button>
          </div>
        )}

        <div className="spacer" />

        {/* Action Buttons */}
        <div className="action-buttons-group">
          <button className="btn btn-secondary btn-sm" onClick={copyText}>
            Copy Text
          </button>
          <a className="btn btn-secondary btn-sm" href={exportTxtUrl(jobId)} download>
            Download TXT
          </a>
          <a className="btn btn-secondary btn-sm" href={exportJsonUrl(jobId)} download>
            Download Raw JSON
          </a>
        </div>
      </div>

      {/* Main Text Content Display */}
      {viewMode === 'raw_json' ? (
        <div className="raw-json-viewer">
          <pre>{JSON.stringify(pages.map(p => p.raw_json || p.comparison_data || p), null, 2)}</pre>
        </div>
      ) : viewMode === 'side_by_side' && isComparisonMode ? (
        <div className="side-by-side-container">
          {pages.map((page) => {
            const openText = getPageLayerText(page, 'openocr', textLayer)
            const paddleText = getPageLayerText(page, 'paddleocr', textLayer)
            const openConf = page.comparison_data?.openocr?.confidence
            const paddleConf = page.comparison_data?.paddleocr?.confidence

            return (
              <div key={page.page_number} className="side-by-side-page-block">
                <div className="side-by-side-page-title">PAGE {page.page_number} SIDE-BY-SIDE COMPARISON</div>
                <div className="side-by-side-columns">
                  <div className="engine-column openocr-column">
                    <div className="column-header">
                      <span>OpenOCR ({textLayer})</span>
                      <span className="conf-badge">{openConf !== undefined ? `Conf: ${openConf}%` : ''}</span>
                    </div>
                    <pre className="text-box">{openText || '(no text extracted)'}</pre>
                  </div>

                  <div className="engine-column paddleocr-column">
                    <div className="column-header">
                      <span>PaddleOCR ({textLayer})</span>
                      <span className="conf-badge">{paddleConf !== undefined ? `Conf: ${paddleConf}%` : ''}</span>
                    </div>
                    <pre className="text-box">{paddleText || '(no text extracted)'}</pre>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      ) : (
        <div className="text-viewer" ref={viewerRef} role="region" aria-label="Extracted text">
          {pages.map((page, idx) => {
            const textToDisplay = getPageLayerText(page, singleEngine, textLayer)
            const sepCls = page.status === 'needs_review' ? 'page-separator review-separator' : 'page-separator'
            const sepLabel = page.status === 'needs_review'
              ? `${'='.repeat(16)} PAGE ${page.page_number} (${singleEngine.toUpperCase()} - ${textLayer}) ${'='.repeat(16)} [NEEDS REVIEW]`
              : `${'='.repeat(16)} PAGE ${page.page_number} (${singleEngine.toUpperCase()} - ${textLayer}) ${'='.repeat(16)}`

            return (
              <div key={page.page_number} className="page-block">
                <span className={sepCls}>{sepLabel}</span>
                {'\n\n'}
                {page.error
                  ? <span style={{ color: '#991b1b' }}>[ERROR: {page.error}]</span>
                  : (textToDisplay || <span className="muted">(no text extracted)</span>)}
                {idx < pages.length - 1 ? '\n\n' : ''}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
