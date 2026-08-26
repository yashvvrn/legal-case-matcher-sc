# 📊 Multi-Year 150-Document Evaluation Benchmark Report

## 🎯 Executive Summary
- **Master Dataset Scope**: 12,688 Supreme Court Judgments (2010 – 2025)
- **Total Test Queries**: 144
- **Overall Accuracy**: **97.22%** (140/144)
- **Average Query Latency**: **24.46 ms**

---

## 📈 Match Tier Distribution Breakdown
| Tier | Count | Percentage | Primary Signal |
| :--- | :--- | :--- | :--- |
| **EXACT** | 22 | 15.3% | Direct CNR & Neutral Citation |
| **FUZZY** | 12 | 8.3% | Party names & Case No tokens |
| **SEMANTIC** | 107 | 74.3% | Hybrid dense + sparse vectors |
| **NONE** | 3 | 2.1% | Below threshold cut-off |

---

## 📋 Per-Test Category Performance
- **semantic_headnote**: 110/110 (100.0% accuracy)
- **fuzzy_parties**: 8/12 (66.7% accuracy)
- **exact_cnr**: 11/11 (100.0% accuracy)
- **ocr_noised_cnr**: 11/11 (100.0% accuracy)
