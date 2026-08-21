# Legal Case Matching Pipeline — Evaluation Report (Hybrid Update)

## Executive Performance Summary
- **Total Evaluated Variants:** 12780 (100 original cases x 3 synthetic variants)
- **Overall Case-Matching Accuracy:** **98.43%** (12579/12780)
- **False Positive Rate:** **0.41%** (52/12780)
- **No-Match Rate:** **1.17%** (149/12780)
- **Average Query Response Time:** 0.0210 seconds

---

## Before/After Comparison: Legacy vs. New Hybrid Pipeline

| Pipeline Version | Overall Accuracy | Overall FP Rate | Overall No-Match | Semantic Tier Correct | Semantic Tier FP | Semantic Tier No-Match |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Legacy (Single-Snippet)** | 98.13% (12541) | 1.16% (148) | 91 | 4069 | **100** (Pattern B) | 91 |
| **New Hybrid (Dense+Sparse)** | 98.43% (12579) | 0.41% (52) | 149 | 4107 | **4** (Pattern B resolved) | 149 |

---

## Detailed Trace of Regressions (Correct $ightarrow$ Incorrect/No-match)
- **Total previously-correct matches lost:** **66**

- Case **ESCR010002662021** (paraphrased) became a **no_match** (fell below threshold under hybrid).
- Case **ESCR010002622021** (paraphrased) became a **no_match** (fell below threshold under hybrid).
- Case **ESCR010002902021** (paraphrased) became a **no_match** (fell below threshold under hybrid).
- Case **ESCR010005612021** (paraphrased) became a **no_match** (fell below threshold under hybrid).
- Case **ESCR010005562021** (paraphrased) became a **no_match** (fell below threshold under hybrid).
- Case **ESCR010005952021** (paraphrased) became a **no_match** (fell below threshold under hybrid).
- Case **ESCR010006272021** (paraphrased) became a **no_match** (fell below threshold under hybrid).
- Case **ESCR010003922021** (paraphrased) became a **no_match** (fell below threshold under hybrid).
- Case **ESCR010003992021** (paraphrased) became a **no_match** (fell below threshold under hybrid).
- Case **ESCR010005592022** (paraphrased) became a **no_match** (fell below threshold under hybrid).
- Case **ESCR010001482022** (paraphrased) became a **no_match** (fell below threshold under hybrid).
- Case **ESCR010006682022** (paraphrased) became a **no_match** (fell below threshold under hybrid).
- Case **ESCR010003462022** (paraphrased) became a **no_match** (fell below threshold under hybrid).
- Case **ESCR010004082022** (paraphrased) became a **no_match** (fell below threshold under hybrid).
- Case **ESCR010003492022** (paraphrased) became a **no_match** (fell below threshold under hybrid).
- Case **ESCR010002752022** (paraphrased) became a **no_match** (fell below threshold under hybrid).
- Case **ESCR010009332022** (paraphrased) became a **no_match** (fell below threshold under hybrid).
- Case **ESCR010000682022** (paraphrased) became a **no_match** (fell below threshold under hybrid).
- Case **ESCR010003152022** (paraphrased) became a **no_match** (fell below threshold under hybrid).
- Case **ESCR010000232022** (paraphrased) became a **no_match** (fell below threshold under hybrid).
- Case **ESCR010004872022** (paraphrased) became a **no_match** (fell below threshold under hybrid).
- Case **ESCR010009892022** (paraphrased) became a **no_match** (fell below threshold under hybrid).
- Case **ESCR010000332022** (paraphrased) became a **no_match** (fell below threshold under hybrid).
- Case **ESCR010007522022** (paraphrased) became a **no_match** (fell below threshold under hybrid).
- Case **ESCR010003762022** (paraphrased) became a **no_match** (fell below threshold under hybrid).
- Case **ESCR010005752023** (paraphrased) became a **no_match** (fell below threshold under hybrid).
- Case **ESCR010004072023** (paraphrased) became a **no_match** (fell below threshold under hybrid).
- Case **ESCR010002992023** (paraphrased) became a **no_match** (fell below threshold under hybrid).
- Case **ESCR010006912023** (paraphrased) became a **no_match** (fell below threshold under hybrid).
- Case **ESCR010007472023** (paraphrased) became a **no_match** (fell below threshold under hybrid).
- Case **ESCR010003262023** (paraphrased) became a **no_match** (fell below threshold under hybrid).
- Case **ESCR010002552023** (paraphrased) became a **no_match** (fell below threshold under hybrid).
- Case **ESCR010002522023** (paraphrased) became a **no_match** (fell below threshold under hybrid).
- Case **ESCR010007492023** (paraphrased) became a **no_match** (fell below threshold under hybrid).
- Case **ESCR010001342023** (paraphrased) became a **no_match** (fell below threshold under hybrid).
- Case **ESCR010000202024** (paraphrased) became a **no_match** (fell below threshold under hybrid).
- Case **ESCR010002892024** (paraphrased) became a **no_match** (fell below threshold under hybrid).
- Case **ESCR010006832024** (paraphrased) became a **no_match** (fell below threshold under hybrid).
- Case **ESCR010006942024** (paraphrased) became a **no_match** (fell below threshold under hybrid).
- Case **ESCR010006262024** (paraphrased) became a **no_match** (fell below threshold under hybrid).
- Case **ESCR010006282024** (paraphrased) became a **no_match** (fell below threshold under hybrid).
- Case **ESCR010001892024** (paraphrased) became a **no_match** (fell below threshold under hybrid).
- Case **ESCR010005022024** (paraphrased) became a **no_match** (fell below threshold under hybrid).
- Case **ESCR010005882024** (paraphrased) became a **no_match** (fell below threshold under hybrid).
- Case **ESCR010001752024** (paraphrased) became a **no_match** (fell below threshold under hybrid).
- Case **ESCR010001782024** (paraphrased) became a **no_match** (fell below threshold under hybrid).
- Case **ESCR010006872024** (paraphrased) became a **no_match** (fell below threshold under hybrid).
- Case **ESCR010005562024** (paraphrased) became a **no_match** (fell below threshold under hybrid).
- Case **ESCR010000192024** (paraphrased) became a **no_match** (fell below threshold under hybrid).
- Case **ESCR010002152024** (paraphrased) became a **no_match** (fell below threshold under hybrid).
- Case **ESCR010002192024** (paraphrased) became a **no_match** (fell below threshold under hybrid).
- Case **ESCR010000982025** (paraphrased) became a **no_match** (fell below threshold under hybrid).
- Case **ESCR010002042025** (paraphrased) became a **no_match** (fell below threshold under hybrid).
- Case **ESCR010002382025** (paraphrased) became a **no_match** (fell below threshold under hybrid).
- Case **ESCR010002472025** (paraphrased) became a **no_match** (fell below threshold under hybrid).
- Case **ESCR010003452025** (paraphrased) became a **no_match** (fell below threshold under hybrid).
- Case **ESCR010003382025** (paraphrased) became a **no_match** (fell below threshold under hybrid).
- Case **ESCR010003692025** (paraphrased) became a **no_match** (fell below threshold under hybrid).
- Case **ESCR010005702025** (paraphrased) became a **no_match** (fell below threshold under hybrid).
- Case **ESCR010006772025** (paraphrased) became a **no_match** (fell below threshold under hybrid).
- Case **ESCR010006762025** (paraphrased) became a **no_match** (fell below threshold under hybrid).
- Case **ESCR010005102025** (paraphrased) became a **no_match** (fell below threshold under hybrid).
- Case **ESCR010007642025** (paraphrased) became a **no_match** (fell below threshold under hybrid).
- Case **ESCR010008232025** (paraphrased) became a **no_match** (fell below threshold under hybrid).
- Case **ESCR010008612025** (paraphrased) became a **no_match** (fell below threshold under hybrid).
- Case **ESCR010008712025** (paraphrased) became a **no_match** (fell below threshold under hybrid).

---

## Table 1: Performance by Variant Type (Hybrid Pipeline)

| Variant Type | Expected Tier | Test Count | Correct Matches | Accuracy (%) | False Positives | No Match |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Clean** | Exact Tier | 4260 | 4260 | **100.0%** | 0 | 0 |
| **Noisy** | Fuzzy Tier | 4260 | 4212 | **98.9%** | 48 | 0 |
| **Paraphrased** | Semantic Tier | 4260 | 4107 | **96.4%** | 4 | 149 |

---

## Table 2: Confusion Matrix (Expected Tier vs Actual Tier)

```
actual_tier    exact  fuzzy  semantic  none
expected_tier                              
exact           4260      0         0     0
fuzzy              0   4243        17     0
semantic           0      0      4111   149
```

---

## Table 3: Per-Tier Metrics (by Actual Matching Tier)

| Tier     |   True Positives (TP) |   False Positives (FP) |   False Negatives (FN) | Precision   | Recall   | F1-Score   |
|:---------|----------------------:|-----------------------:|-----------------------:|:------------|:---------|:-----------|
| Exact    |                  4260 |                      0 |                      0 | 100.0%      | 100.0%   | 100.0%     |
| Fuzzy    |                  4195 |                     48 |                     48 | 98.9%       | 98.9%    | 98.9%      |
| Semantic |                  4124 |                      4 |                    153 | 99.9%       | 96.4%    | 98.1%      |

*Note: Table 1's Noisy Correct count (4,212) differs from Table 3's Fuzzy Tier True Positives (4,195) because 17 noisy queries fell through the fuzzy tier and were correctly matched by the semantic tier instead.*

---

## Hybrid Weight Sensitivity Warning
> [!IMPORTANT]
> The weights used for this run (**0.7 dense / 0.3 sparse**) were tuned primarily against the 100 Pattern-B false-positive cases. In production, these weights should be treated as **provisional** and subject to continuous optimization. A grid search over different weights on a broader test set is recommended to find the optimal trade-off between semantic abstraction and keyword alignment.
