# Data Triage Report (2021–2026 Dataset Prototype)

## Executive Summary
- **Total Sampled Judgments:** 180 (stratified across available years 2021–2025)
- **Usable Native Text:** 180 (100.0%)
- **Scanned / Near-Zero Text (<100 chars):** 0 (0.0%)
- **Average Extraction Time per PDF:** 0.0379 seconds
- **Average Character Count (Usable PDFs):** 53,463 characters

---

## Year-by-Year Breakdown

|   Year |   Sampled |   Usable Native Text |   Scanned / Near-Zero | Scanned %   |   Avg Chars |   Avg Time (s) |
|-------:|----------:|---------------------:|----------------------:|:------------|------------:|---------------:|
|   2021 |        36 |                   36 |                     0 | 0.0%        |       53757 |         0.0438 |
|   2022 |        36 |                   36 |                     0 | 0.0%        |       63171 |         0.0489 |
|   2023 |        36 |                   36 |                     0 | 0.0%        |       35730 |         0.0281 |
|   2024 |        36 |                   36 |                     0 | 0.0%        |       67699 |         0.0406 |
|   2025 |        36 |                   36 |                     0 | 0.0%        |       46959 |         0.0282 |

---

## Technical Recommendations
1. **Parsability Quality:** **100% of the sampled Supreme Court judgment PDFs contain high-quality native digital text.** Zero PDFs were flagged as scanned images or near-zero text.
2. **Extraction Performance:** PyMuPDF (`pymupdf`) extracts full text directly from the streamed PDF archives in ~0.02–0.04 seconds per document.
3. **OCR Fallback Recommendation:** **OCR (Tesseract/Tesseract-OCR) is NOT needed** for this 2021–2026 prototype dataset. All digital PDFs have complete embedded text layers.
