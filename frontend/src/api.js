/**
 * api.js — Thin wrapper around fetch for all backend endpoints.
 * All calls go through the Vite proxy (/api → localhost:8000/api).
 */

const BASE = '/api'

async function _request(method, path, body) {
  const opts = { method, headers: {} }
  if (body instanceof FormData) {
    opts.body = body
  } else if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json'
    opts.body = JSON.stringify(body)
  }
  const res = await fetch(BASE + path, opts)
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const j = await res.json()
      detail = j.detail || detail
    } catch (_) {}
    throw new Error(detail)
  }
  return res
}

export async function uploadPDF(file, engine = 'openocr') {
  const fd = new FormData()
  fd.append('file', file)
  const res = await _request('POST', `/process?engine=${encodeURIComponent(engine)}`, fd)
  return res.json()
}

export async function getJob(jobId) {
  const res = await _request('GET', `/jobs/${jobId}`)
  return res.json()
}

export async function getPageDetail(jobId, pageNumber) {
  const res = await _request('GET', `/jobs/${jobId}/pages/${pageNumber}`)
  return res.json()
}

export async function markReviewed(jobId, pageNumber) {
  const res = await _request('POST', `/jobs/${jobId}/pages/${pageNumber}/review`, {
    action: 'mark_reviewed'
  })
  return res.json()
}

export async function updatePageText(jobId, pageNumber, text) {
  const res = await _request('POST', `/jobs/${jobId}/pages/${pageNumber}/review`, {
    action: 'update_text',
    text
  })
  return res.json()
}

export function exportTxtUrl(jobId) {
  return `${BASE}/jobs/${jobId}/export/txt`
}

export function exportJsonUrl(jobId) {
  return `${BASE}/jobs/${jobId}/export/json`
}

/**
 * Rasterize a PDF at the given DPI and return a Blob URL for download.
 * The caller is responsible for calling URL.revokeObjectURL() when done.
 *
 * @param {File}   file  — original PDF File object
 * @param {number} dpi   — render resolution (72–400)
 * @returns {Promise<{blobUrl: string, filename: string}>}
 */
export async function rasterizePDF(file, dpi = 200) {
  const fd = new FormData()
  fd.append('file', file)
  const res = await fetch(`${BASE}/rasterize?dpi=${dpi}`, { method: 'POST', body: fd })
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try { const j = await res.json(); detail = j.detail || detail } catch (_) {}
    throw new Error(detail)
  }
  const blob = await res.blob()
  const blobUrl = URL.createObjectURL(blob)
  // Extract filename from Content-Disposition header if present
  const cd = res.headers.get('Content-Disposition') || ''
  const match = cd.match(/filename="?([^"]+)"?/)
  const filename = match ? match[1] : `rasterized_${dpi}dpi.pdf`
  return { blobUrl, filename }
}
