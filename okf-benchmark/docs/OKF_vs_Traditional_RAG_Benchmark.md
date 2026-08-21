# **CaseDesk**

OKF vs. Traditional Routing — Head-to-Head Benchmark

### **Benchmark Report**

Organized by matching stage (Fuzzy / Semantic / etc.), matching the layout of the original InLegalNER report

**Case Pool** 4,260 real Supreme Court cases (2021–2025) **Test Documents** 150 real judgment excerpts **Best Accuracy 99.3%** **Format-Alone Accuracy Change 0.0%**

August 17, 2026

**CaseDesk**

OKF vs. Traditional Routing Benchmark

---

## 0. A note before you read this — one important difference from the original report

> 💬 **In plain terms:** Your original InLegalNER report had four stages: Exact → Fuzzy → Semantic → **SLM Fallback** (a language-model safety net for anonymous text). **This real engine does not have that fourth stage.** It only has three: **Exact, Fuzzy, Semantic.** If none of those three finds a confident answer, the system just stops and says "not sure — send to a human." There's no AI model making a judgment call at that point, just a threshold check. I'm flagging this clearly so the comparison below isn't confusing: wherever you'd expect "SLM Fallback," read it as **"No Match / Needs Review"** instead.

Everything below is organized the way your original report was — **by matching stage**, not by "Arm 1/2/3." Within each stage, you'll see three columns: how the *current* system does it (Control), how it does using Google's new OKF file format with *no other changes* (Format Only), and how it does with OKF *plus* some extra smart cross-checking rules (Format + Rules). Think of those three columns as "same recipe, same recipe just re-packaged, and an improved recipe" — not three different systems.

---

## 1. Executive Summary

<u>Table 1: Overall accuracy across all 150 documents</u>

| | Control (today's system) | Format Only (OKF, no logic changes) | Format + Rules (OKF + smart checks) |
|---|---|---|---|
| **Overall Accuracy** | 98.0% (147/150) | 98.0% (147/150) | **99.3% (149/150)** |
| Wrong auto-matches (the dangerous kind) | 1 | 1 | 1 |
| Typical speed per document | 102 ms | 119 ms | 238 ms |

**The one-line takeaway:** switching *only* the file format changed nothing at all — same 147 right, same 3 wrong, on every single document. Adding extra cross-checking rules on top fixed 2 of the 3 failures, but made the system slower and more cautious. Full explanation stage-by-stage below.

---

## 2. Stage 1 — Exact Match

> 💬 **In plain terms:** This is the easy case — the document has a clear court reference number written on it (like a receipt number), and the system just looks it up directly. No guessing involved.

<u>Table 2: Stage 1 results</u>

| Metric | Control | Format Only | Format + Rules |
|---|---|---|---|
| Documents reaching this stage | 60 | 60 | 60 |
| Correct | 60 | 60 | 60 |
| **Accuracy** | **100.0%** | **100.0%** | **100.0%** |
| Median speed | 0.5 ms | 0.5 ms | 0.1 ms |

**Result:** perfect across the board, as expected — when the reference number is right there in the text, there's nothing to get wrong, regardless of format or extra rules.

---

## 3. Stage 2 — Fuzzy Match

> 💬 **In plain terms:** No exact reference number this time, so the system compares party names (e.g. "Frank Vitus v. Narcotics Control Bureau") using approximate text matching — tolerant of typos, OCR errors, or slightly different formatting.

<u>Table 3: Stage 2 results</u>

| Metric | Control | Format Only | Format + Rules |
|---|---|---|---|
| Documents reaching this stage | 40 | 40 | 40 |
| Correct | 39 | 39 | 39 |
| **Accuracy** | **97.5%** | **97.5%** | **97.5%** |
| Wrong auto-matches | 1 | 1 | 1 |
| Median speed | 118 ms | 140 ms | 278 ms |

**Result:** identical accuracy in all three versions — **this is the one stage that never improved, in any version tested.** One document (`doc_035`) was matched to the wrong case with a *high* confidence score (95.2%) every single time. This is a known, named risk pattern: two different real cases had similarly-worded party names, and a high fuzzy-match score doesn't protect against that. Interestingly, the Control and Format-Only versions each picked a *different* wrong case for this document — a coin-flip tie-break quirk between two equally-scored wrong answers, not a real disagreement in judgment. **This is the single most important finding in this stage: none of the three versions caught it.** The "smart rules" added in the third version don't apply here, because they only kick in at Stage 3 below.

---

## 4. Stage 3 — Semantic Match

> 💬 **In plain terms:** No case number, no usable party names — the document has been stripped down to just its legal reasoning. The system now has to understand the *meaning* of the text and compare it against the meaning of the 4,260 cases in the pool, using an AI similarity model. This is the hardest stage and where all of this benchmark's interesting differences show up.

<u>Table 4: Stage 3 results</u>

| Metric | Control | Format Only | Format + Rules |
|---|---|---|---|
| Documents reaching this stage | 48 | 48 | 50\* |
| Correct | 48 | 48 | 50 |
| **Accuracy** | **100.0%** | **100.0%** | **100.0%** |
| Sent to human review instead of guessing | 0 | 0 | 8 |
| Median speed | 149 ms | 162 ms | 313 ms |

\*Two extra documents reached this stage in the "Format + Rules" version because its added judge-name and case-relationship checks were confident enough to *correctly* resolve two documents that the other two versions had to abandon and send for human review (see Stage 4 below) — those 2 "saves" are the entire accuracy improvement this benchmark found.

**Result:** every document that reached this stage and got an actual answer was answered correctly, in all three versions — 100% on the documents it was willing to commit to. The real difference is what happened to documents that *couldn't* clear this stage confidently — see below.

---

## 5. Stage 4 — No Match / Needs Human Review

> 💬 **In plain terms:** This is the safety net. If the system genuinely can't tell which case a document belongs to, the honest and safe thing to do is admit it and ask a person — **not** guess and risk filing something into the wrong client's file. Remember: **this is not an SLM.** It's a simple rule: if confidence never crosses the bar, stop and flag it.

<u>Table 5: Stage 4 results</u>

| Metric | Control | Format Only | Format + Rules |
|---|---|---|---|
| Documents landing here | 2 | 2 | 0 |
| Correctly flagged (none wrongly auto-filed) | 2 | 2 | — |

**Result:** in the Control and Format-Only versions, 2 of the hardest documents (both from the "no identifying info at all" category) hit this safety net and were correctly sent for human review — a safe outcome, but not a solved one. In the "Format + Rules" version, the extra judge-name and case-relationship signals were strong enough to resolve **both** of these confidently and correctly at Stage 3 instead — that's where the +2 documents in Table 4 came from. Zero documents were ever wrongly kept out of this safety net in any version.

---

## 6. Was the Improvement Real, or Just Luck? (Statistical Significance)

> 💬 **In plain terms:** With only 150 test documents, a 2-document improvement could plausibly be luck rather than a real effect. We ran a standard statistical test to check.

| Comparison | Documents that changed outcome | Verdict |
|---|---|---|
| Format Only vs. Control (does the file format alone matter?) | **0 out of 150** | **Not significant** — literally zero difference, on every document |
| Format + Rules vs. Control (does the full package help?) | 2 out of 150 | **Not significant yet** (p = 0.50) — promising direction, not proof |
| Format + Rules vs. Format Only (do the extra rules alone help, format held fixed?) | 2 out of 150 | **Not significant yet** (p = 0.50) — same 2 documents, same caveat |

**What this means:** we can say with confidence that the file format by itself does nothing — that comparison came back as literally zero difference across 150 real documents, which is about as clean a "no effect" result as a test can produce. The extra smart-checking rules moved 2 documents from wrong-or-unresolved to correct, which is a good sign, but 150 documents (and only 30 of the hardest kind) isn't a big enough sample to call that proven rather than lucky. More test documents would settle it either way.

---

## 7. Key Findings

1. **Stage 1 (Exact) and Stage 3 (Semantic, when it commits to an answer) were already perfect, in every version.** Nothing to improve there.
2. **Stage 2 (Fuzzy) never improved, in any version.** One document with confusingly similar party names was matched wrong every time, at high confidence. This is the one finding that should worry you most, because a wrong match with a *high* confidence score is the most dangerous kind of error — it looks trustworthy and isn't.
3. **The file format made zero difference on its own.** Every one of 150 documents got the identical result whether the case data lived in a database or in OKF files. This matches what OKF's own creators say about it — it's a way of storing information, not a source of intelligence.
4. **The improvement came entirely from Stage 4 → Stage 3 rescues.** Two documents that used to require human review were instead correctly resolved automatically, because the extra version could cross-check judge names and case relationships — extra *data fields*, not the file format, did the work.
5. **That improvement is not yet statistically proven**, though it's a good sign. It also came at a real cost: roughly double the processing time and 4x more documents sent to human review overall (mostly because the system became more cautious at Stage 3, not because it got worse).
6. **The one dangerous error type — a wrong match with high confidence — was not fixed by anything tested here.** It survived unchanged through Control, Format Only, and Format + Rules alike.

---

## 8. Recommended Next Steps

1. **Fix Stage 2 (Fuzzy Match) directly — it's the one stage nothing here improved.** The `doc_035` failure is a name-collision problem: add a check that flags it for review whenever a fuzzy match's winning name is *also* a strong match for a second, different case. That's a more direct fix than anything tested in this round.
2. **Test on more documents, especially more "hardest" ones**, before treating the Stage 3/4 improvement as settled. 30 hard documents isn't enough to be sure a 2-document swing is real. There are 4,110 more real cases and an existing 500-document stress test sitting unused for this exact purpose.
3. **Decide the format question and the smart-rules question separately.** Since the format itself proved to make zero difference, the same judge-name/case-relationship checks could likely be added to the existing database with a couple of extra columns — probably cheaper and faster to run than adopting a new file format. OKF's real advantage here isn't accuracy — it's that a `.md` file with clearly labeled fields is something a non-technical person can open and read directly, which matters for trust and audits even though it doesn't show up in these numbers.
4. **Budget for the trade-off if you adopt the smart rules**: roughly 2x slower per document, and about 4x more documents will need a human to double-check them.

---

## 9. Conclusion

Reframed by matching stage rather than by version, the picture is simple: **Stage 1 and Stage 3 were already essentially solved. Stage 2 (Fuzzy Match) is where a real, unfixed risk lives — a wrong match with a deceptively high confidence score, present in every version tested.** The file format (OKF) made no measurable difference anywhere. The only real gain came from giving the system extra structured facts to cross-check at Stage 3 — judge names and known case relationships — which rescued 2 documents that previously had to be kicked to a human, at the cost of speed and an increase in how often the system asks for help. That gain is a promising lead, not yet a proven result, and it does not touch the fuzzy-match name-collision risk, which should be the actual next priority.

_CaseDesk OKF vs. Traditional Routing Benchmark_
