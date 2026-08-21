import React, { useState, useEffect, useRef } from 'react';
import { 
  FileText, UploadCloud, Cpu, AlertCircle, CheckCircle2, 
  Download, Copy, RefreshCw, Zap, Clock, Hash, Layers, Scale, Sparkles, Sliders
} from 'lucide-react';

export default function App() {
  const [health, setHealth] = useState({ status: 'checking' });
  const [selectedModel, setSelectedModel] = useState('gemma3:1b');

  const [uploadedDoc, setUploadedDoc] = useState(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState(null);

  const [isProcessing, setIsProcessing] = useState(false);
  const [progressMsg, setProgressMsg] = useState('');
  const [progressPercent, setProgressPercent] = useState(0);
  const [stepsLog, setStepsLog] = useState([]);

  const [summaryResult, setSummaryResult] = useState(null);
  const [benchmark, setBenchmark] = useState(null);
  const [copied, setCopied] = useState(false);

  const fileInputRef = useRef(null);

  // Check Ollama health status
  const checkHealth = async () => {
    setHealth({ status: 'checking' });
    try {
      const res = await fetch('/api/health');
      const data = await res.json();
      if (res.ok && data.status === 'healthy') {
        setHealth({ status: 'healthy', data });
      } else {
        setHealth({ status: 'unhealthy', error: data.error || 'Ollama unavailable' });
      }
    } catch (err) {
      setHealth({ 
        status: 'unhealthy', 
        error: 'Unable to connect to backend server. Make sure FastAPI server is running on port 8000.' 
      });
    }
  };

  useEffect(() => {
    checkHealth();
  }, []);

  // Handle File Upload
  const handleFileUpload = async (file) => {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      setUploadError('Only PDF files are supported.');
      return;
    }

    setIsUploading(true);
    setUploadError(null);
    setUploadedDoc(null);
    setSummaryResult(null);
    setBenchmark(null);
    setStepsLog([]);

    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await fetch('/api/upload', {
        method: 'POST',
        body: formData,
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail || 'Failed to parse PDF file.');
      }

      setUploadedDoc(data);
    } catch (err) {
      setUploadError(err.message);
    } finally {
      setIsUploading(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileUpload(e.dataTransfer.files[0]);
    }
  };

  // Trigger Summarization SSE Stream with selected model
  const handleSummarize = () => {
    if (!uploadedDoc) return;

    setIsProcessing(true);
    setSummaryResult(null);
    setBenchmark(null);
    setProgressPercent(5);
    setStepsLog([
      { text: `PDF uploaded & text extracted (${uploadedDoc.pages} pages)`, status: 'done' }
    ]);

    const eventSource = new EventSource(`/api/summarize/stream/${uploadedDoc.doc_id}?model_name=${selectedModel}`);

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        if (data.step === 'health_check') {
          setProgressMsg(data.message);
          setProgressPercent(15);
        } else if (data.step === 'health_ok') {
          setStepsLog((prev) => [...prev, { text: data.message, status: 'done' }]);
        } else if (data.step === 'chunking') {
          setProgressMsg(data.message);
          setProgressPercent(30);
        } else if (data.step === 'chunking_complete') {
          setStepsLog((prev) => [...prev, { text: data.message, status: 'done' }]);
          setProgressPercent(40);
        } else if (data.step === 'summarizing_chunk') {
          const { current_chunk, total_chunks, message } = data;
          setProgressMsg(message);
          const chunkProgress = Math.round(40 + (current_chunk / total_chunks) * 45);
          setProgressPercent(chunkProgress);
          
          setStepsLog((prev) => {
            const filtered = prev.filter(s => !s.isChunkStep);
            return [...filtered, { text: message, status: 'active', isChunkStep: true }];
          });
        } else if (data.step === 'synthesizing') {
          setProgressMsg(data.message);
          setProgressPercent(90);
          setStepsLog((prev) => {
            const filtered = prev.map(s => s.isChunkStep ? { ...s, status: 'done' } : s);
            return [...filtered, { text: data.message, status: 'active' }];
          });
        } else if (data.step === 'complete') {
          setProgressPercent(100);
          setProgressMsg(data.message);
          setSummaryResult(data.summary);
          setBenchmark(data.benchmark);
          setStepsLog((prev) => prev.map(s => ({ ...s, status: 'done' })));
          setIsProcessing(false);
          eventSource.close();
        } else if (data.step === 'error') {
          setUploadError(`Summarization Error: ${data.error}`);
          setIsProcessing(false);
          eventSource.close();
        }
      } catch (e) {
        console.error('Error parsing SSE data:', e);
      }
    };

    eventSource.onerror = (err) => {
      console.error('EventSource failed:', err);
      setUploadError('Connection to server lost during summarization.');
      setIsProcessing(false);
      eventSource.close();
    };
  };

  // Copy Summary to Clipboard
  const handleCopy = () => {
    if (!summaryResult) return;
    navigator.clipboard.writeText(summaryResult);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Download Summary File
  const handleDownload = (format) => {
    if (!uploadedDoc) return;
    window.open(`/api/download/${uploadedDoc.doc_id}?format=${format}`, '_blank');
  };

  return (
    <div className="app-container">
      {/* Header */}
      <header className="app-header">
        <div className="brand-title">
          <Scale className="text-indigo-400" size={32} />
          <div>
            <h1>Legal Judgement Summarizer</h1>
            <p className="brand-subtitle">Local LLM PDF Summarization Engine</p>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
          {/* Model Selector Dropdown */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', background: 'rgba(255,255,255,0.05)', padding: '0.4rem 0.8rem', borderRadius: '0.5rem', border: '1px solid var(--border-color)' }}>
            <Sliders size={16} color="var(--primary-accent)" />
            <select
              value={selectedModel}
              onChange={(e) => setSelectedModel(e.target.value)}
              style={{
                background: 'transparent',
                color: 'var(--text-main)',
                border: 'none',
                outline: 'none',
                fontWeight: 600,
                fontSize: '0.875rem',
                cursor: 'pointer'
              }}
            >
              <option value="gemma3:1b" style={{ background: '#121826', color: '#fff' }}>
                ⚡ Gemma 3 1B (Ultra Fast ~15-30s)
              </option>
              <option value="gemma3:4b" style={{ background: '#121826', color: '#fff' }}>
                🎯 Gemma 3 4B (High Precision ~1-2m)
              </option>
              <option value="gemma2:2b" style={{ background: '#121826', color: '#fff' }}>
                ⚖️ Gemma 2 2B (Balanced ~45s)
              </option>
            </select>
          </div>

          {/* Ollama Health Badge */}
          <div className={`health-badge ${health.status === 'healthy' ? 'healthy' : 'unhealthy'}`}>
            <div className="health-dot"></div>
            {health.status === 'checking' && <span>Checking Ollama...</span>}
            {health.status === 'healthy' && (
              <span>Ollama Ready</span>
            )}
            {health.status === 'unhealthy' && (
              <span>Ollama Offline / Model Missing</span>
            )}
            <button onClick={checkHealth} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'inherit', marginLeft: '0.25rem' }}>
              <RefreshCw size={14} />
            </button>
          </div>
        </div>
      </header>

      {/* Ollama Unhealthy Notice */}
      {health.status === 'unhealthy' && (
        <div className="error-banner" style={{ marginBottom: '1.5rem' }}>
          <AlertCircle size={24} style={{ flexShrink: 0 }} />
          <div>
            <strong>Ollama is unavailable or model is missing:</strong>
            <p>{health.error}</p>
            <div style={{ marginTop: '0.5rem', fontFamily: 'var(--font-mono)', fontSize: '0.85rem', background: 'rgba(0,0,0,0.3)', padding: '0.5rem', borderRadius: '0.375rem' }}>
              ollama pull {selectedModel}
            </div>
          </div>
        </div>
      )}

      {/* Upload Section */}
      <section className="glass-card">
        <div 
          className="dropzone"
          onDragOver={(e) => e.preventDefault()}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
        >
          <input 
            type="file" 
            ref={fileInputRef} 
            onChange={(e) => handleFileUpload(e.target.files[0])} 
            accept=".pdf" 
            style={{ display: 'none' }} 
          />
          <UploadCloud className="upload-icon" />
          <h3 style={{ fontSize: '1.2rem', fontWeight: 600 }}>Drag & drop your Legal Judgement PDF</h3>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', marginTop: '0.25rem' }}>
            Supports selectable PDF legal documents (OCR is not applied)
          </p>
          <button type="button" className="btn-upload" disabled={isUploading}>
            {isUploading ? <div className="spinner"></div> : <FileText size={18} />}
            Choose PDF
          </button>
        </div>

        {/* Upload Error / OCR Warning */}
        {uploadError && (
          <div className="error-banner">
            <AlertCircle size={22} style={{ flexShrink: 0 }} />
            <div>
              <strong>Upload Notice:</strong>
              <p>{uploadError}</p>
            </div>
          </div>
        )}

        {/* Document Stats Card */}
        {uploadedDoc && (
          <div>
            <div className="doc-meta-grid">
              <div className="meta-item">
                <div className="meta-label">Filename</div>
                <div className="meta-value" style={{ fontSize: '0.95rem' }}>{uploadedDoc.filename}</div>
              </div>
              <div className="meta-item">
                <div className="meta-label">File Size</div>
                <div className="meta-value">{uploadedDoc.file_size_formatted}</div>
              </div>
              <div className="meta-item">
                <div className="meta-label">Total Pages</div>
                <div className="meta-value">{uploadedDoc.pages}</div>
              </div>
              <div className="meta-item">
                <div className="meta-label">Extracted Text Length</div>
                <div className="meta-value">{uploadedDoc.extracted_chars.toLocaleString()} chars</div>
              </div>
            </div>

            <button 
              className="btn-primary" 
              onClick={handleSummarize} 
              disabled={isProcessing || health.status !== 'healthy'}
            >
              {isProcessing ? (
                <>
                  <div className="spinner"></div>
                  Summarizing with {selectedModel}...
                </>
              ) : (
                <>
                  <Sparkles size={20} />
                  Summarize Document ({selectedModel})
                </>
              )}
            </button>
          </div>
        )}

        {/* Live Progress Bar & Step Log */}
        {isProcessing && (
          <div className="progress-box">
            <div className="progress-header">
              <span>{progressMsg}</span>
              <span>{progressPercent}%</span>
            </div>
            <div className="progress-bar-bg">
              <div className="progress-bar-fill" style={{ width: `${progressPercent}%` }}></div>
            </div>
            <div className="step-list">
              {stepsLog.map((step, idx) => (
                <div key={idx} className={`step-item ${step.status}`}>
                  {step.status === 'done' ? (
                    <CheckCircle2 size={16} color="var(--success-color)" />
                  ) : (
                    <div className="spinner" style={{ width: 14, height: 14 }}></div>
                  )}
                  <span>{step.text}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </section>

      {/* Benchmark Statistics Card */}
      {benchmark && (
        <section className="benchmark-banner">
          <div className="benchmark-title">
            <Zap size={16} /> Benchmark & Execution Performance
          </div>
          <div className="benchmark-grid">
            <div className="bm-pill">
              <div className="bm-label">Model</div>
              <div className="bm-value">{benchmark.model_name}</div>
            </div>
            <div className="bm-pill">
              <div className="bm-label">Pages</div>
              <div className="bm-value">{benchmark.pages}</div>
            </div>
            <div className="bm-pill">
              <div className="bm-label">Extracted Chars</div>
              <div className="bm-value">{benchmark.extracted_characters.toLocaleString()}</div>
            </div>
            <div className="bm-pill">
              <div className="bm-label">Chunks</div>
              <div className="bm-value">{benchmark.chunks}</div>
            </div>
            <div className="bm-pill">
              <div className="bm-label">Processing Time</div>
              <div className="bm-value" style={{ color: '#34d399' }}>{benchmark.processing_time_formatted}</div>
            </div>
            <div className="bm-pill">
              <div className="bm-label">Input Tokens</div>
              <div className="bm-value">{benchmark.input_tokens.toLocaleString()}</div>
            </div>
            <div className="bm-pill">
              <div className="bm-label">Output Tokens</div>
              <div className="bm-value">{benchmark.output_tokens.toLocaleString()}</div>
            </div>
            <div className="bm-pill">
              <div className="bm-label">Tokens / Second</div>
              <div className="bm-value" style={{ color: '#38bdf8' }}>{benchmark.tokens_per_second} tok/s</div>
            </div>
          </div>
        </section>
      )}

      {/* Structured Legal Summary Output */}
      {summaryResult && (
        <section className="glass-card">
          <div className="summary-header">
            <h2 style={{ fontSize: '1.4rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Scale size={24} color="var(--primary-accent)" />
              Structured Legal Summary
            </h2>

            <div className="action-buttons">
              <button 
                className={`btn-secondary ${copied ? 'btn-success' : ''}`}
                onClick={handleCopy}
              >
                {copied ? <CheckCircle2 size={16} /> : <Copy size={16} />}
                {copied ? 'Copied!' : 'Copy Summary'}
              </button>

              <button className="btn-secondary" onClick={() => handleDownload('md')}>
                <Download size={16} /> Markdown (.md)
              </button>

              <button className="btn-secondary" onClick={() => handleDownload('txt')}>
                <Download size={16} /> Text (.txt)
              </button>
            </div>
          </div>

          <div className="summary-content">
            <FormattedSummaryText text={summaryResult} />
          </div>
        </section>
      )}
    </div>
  );
}

// Component to render formatted summary sections with highlighted page references
function FormattedSummaryText({ text }) {
  if (!text) return null;

  const sections = text.split(/(?=###\s+)/g);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
      {sections.map((sec, idx) => {
        const trimmed = sec.trim();
        if (!trimmed) return null;

        const firstLineEnd = trimmed.indexOf('\n');
        const titleLine = firstLineEnd !== -1 ? trimmed.substring(0, firstLineEnd) : trimmed;
        const bodyContent = firstLineEnd !== -1 ? trimmed.substring(firstLineEnd + 1) : '';

        const cleanTitle = titleLine.replace(/^###\s+/, '');

        return (
          <div key={idx} className="summary-section">
            <div className="section-title">
              {cleanTitle}
            </div>
            <div style={{ fontSize: '0.95rem', color: '#e5e7eb', whitespace: 'pre-wrap', lineHeight: 1.7 }}>
              <HighlightPageTags content={bodyContent || trimmed} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

// Highlight source page tags like [Pages 7-9] or [Page 12]
function HighlightPageTags({ content }) {
  if (!content) return null;

  const parts = content.split(/(\[(?:Pages?|Page)\s+\d+(?:[–-]\d+)?\])/gi);

  return (
    <>
      {parts.map((part, index) => {
        if (/^\[(?:Pages?|Page)\s+\d+(?:[–-]\d+)?\]$/i.test(part)) {
          return (
            <span key={index} className="page-tag">
              {part}
            </span>
          );
        }
        return part;
      })}
    </>
  );
}
