# 14 — OKF Matter-Pool Routing Benchmark: 3-Arm Test Guide

**Status:** Draft v1.0 · Prepared 16 Aug 2026
**Scope:** Re-run the InLegalNER Stage B/C/D routing benchmark with the matter pool represented as an Open Knowledge Format (OKF) bundle, across three arms.
**Prerequisite reading:** `InLegalNER_CaseDesk_Benchmark.pdf` (baseline), `10-Document-Intelligence-Local-Vault-Spec.md` (pipeline), `05-Security-Compliance.md` §2 (residency).
**Audience:** You (non-coder), driving a coding agent. Every code step is a copy-exact prompt.

---

## 0. What OKF actually is, in one paragraph

OKF v0.2 is a **file format specification**, published by Google Cloud's Data Cloud team in June 2026. A "bundle" is a directory of markdown files. Each file is a "concept." The file path is the concept's ID. Every file has a YAML frontmatter block at the top and a markdown body below it. The **only** required frontmatter field is `type`. Everything else — `title`, `description`, `resource`, `tags`, plus the optional provenance/trust/lifecycle families (`sources`, `generated`, `verified`, `status`, `stale_after`) — is optional. Concepts link to each other with ordinary markdown links, which turns the folder into a graph.

There is no runtime, no SDK, no database, no matcher, no scorer. It cannot make your router more accurate by itself. What it can do is give the router a **richer, structured, graph-linked representation of the 60-case matter pool** than the flat SQLite rows it reads today — which is the substrate the §9 recommendations in your benchmark report need anyway.

**Version note:** the blog post you sent describes v0.1. The spec in the repo has already moved to **v0.2**, which supersedes it. Build against v0.2. Two v0.1 fields are retired: `timestamp` is replaced by `generated: { by, at }`, and the body `# Citations` list is replaced by the `sources` frontmatter field.

---

## 1. The experiment design

### 1.1 Three arms

| Arm | Matter pool representation | Matching features | What it isolates |
|---|---|---|---|
| **A1 — Control** | Existing SQLite mirror (`matters`, `clients`, `matter_parties`) | Existing: deterministic → fuzzy → embedding → SLM | Reproduces the 85.6% baseline. Proves the harness is intact. |
| **A2 — Format only** | OKF bundle, 60 concept docs | **Identical to A1.** No new signals used. | The effect of the format alone. |
| **A3 — OKF + §9** | Same OKF bundle as A2 | Multi-signal scoring over frontmatter, candidate re-ranking, contradiction gate | The effect of the §9 recommendations, now that structured fields exist to power them. |

### 1.2 The single most important methodological rule

> **A2 must embed exactly the same text A1 embeds.**

If the OKF concept body contains a nicely written facts summary while the SQLite row contains a raw title string, A2 is not measuring the format — it is measuring content curation, and the result is worthless. The producer (Step 3) must build the OKF body from the *same fields* A1 already reads, in the same order, nothing added.

**Expected outcome for A2: no meaningful change from A1.** That is the correct result, not a failed experiment. It establishes that the format is signal-neutral, which is exactly what lets you attribute A3's delta to the §9 features rather than to a representation artefact. If A2 moves more than a couple of documents in either direction, you have a leak — stop and find it before running A3.

### 1.3 Test contamination — read before building anything

Your matter pool and your test documents both derive from InLegalNER. Three specific ways this experiment can silently cheat:

1. **Body leakage.** If you generate a matter's OKF concept body from the *test document's* full text, semantic matching becomes near-exact retrieval and Stage C will jump to ~95%. Meaningless. The bundle must be built **only from matter-pool metadata** — the fields a real firm would have entered when opening the matter — never from the test documents.
2. **Cross-link leakage.** The `# Related Matters` links are the most valuable part of the graph and the easiest place to cheat. If you author the links by looking at which test documents confused which matters (LNER0002↔LNER0028, LNER0018↔LNER0013, LNER0020↔LNER0013), you have encoded the answer key. Links must come from a rule you can state in advance — same parties, same court + same statute + overlapping dates, explicit citation in the judgment — applied blind.
3. **Threshold tuning on the test set.** Do not tune the A3 contradiction thresholds against the 90 benchmark documents. Hold out a tuning split, or fix thresholds a priori from the report's observed 0.75–0.82 confidence band and do not touch them.

### 1.4 Statistical power — the uncomfortable part

Stage C is 30 documents. 17/30 = 56.7%. Moving to 70% means 21/30 — a four-document swing. On a paired sample of 30 with McNemar's test, a four-document swing is **not** statistically distinguishable from noise. You could ship an architecture decision on a coin flip.

Two options, both acceptable:

- **Cheap:** treat this run as directional only. State in the report that it is exploratory and that no arm is declared a winner. Requires an honest "not significant" line in every conclusion.
- **Correct:** expand Stage C to **at least 100 documents** before running the three arms. InLegalNER's dev split has the material. This is roughly a day of harness work and it is what turns the output from an anecdote into evidence.

Recommendation: expand. You are going to be showing this benchmark to people who evaluate evidence for a living.

### 1.5 Metrics — fixing a flaw in the current report

Your existing Stage C pass condition is `actual_matter_id == expected_matter_id`, and it explicitly accepts both `filed` and `needs_review` outcomes. That conflates two outcomes with wildly different real-world cost:

- **Wrong suggestion, sent to review** — a mild annoyance. The advocate corrects it in one tap.
- **Wrong matter, auto-filed** — a document sitting in the wrong client's file. In a litigation practice this is a privilege and conflict problem, not a UX problem.

Of your 13 Stage C failures, 11 were `needs_review` and only 2 were `filed` (semantic_015 at 0.821 confidence, and semantic_010 at fuzzy confidence 1.000). Those two are the ones that matter. Report them separately.

**Capture per arm, per stage:**

| Metric | Definition | Why |
|---|---|---|
| `matter_accuracy` | correct matter ID, any status | Comparable to the existing report |
| `autofile_precision` | correct ∧ filed / all filed | **The safety-critical number.** Should be ≥ 0.99 |
| `autofile_recall` | correct ∧ filed / all documents | The productivity number |
| `review_rate` | needs_review / all | The cost of being conservative |
| `harmful_error_count` | filed ∧ wrong | Should trend to 0. This is the headline. |
| `invariant_violations` | Stage D docs not in needs_review | Hard gate. Must be 0. |
| `p50_route_ms`, `p90_route_ms` | Per-document, excluding bundle load | Latency |
| `bundle_load_ms` | One-time, startup | **New in A2/A3.** Do not fold into route latency. |
| `contradiction_trigger_rate` | A3 only | How often the gate fires |
| `calibration_table` | accuracy bucketed by confidence in 0.05 bands | Powers §9.2 threshold work |

`bundle_load_ms` deserves emphasis: reading and YAML-parsing 60 markdown files is slower than a SQLite query, but it happens once at app start, not per document. If you fold it into route latency you will produce a fake regression and possibly kill a good architecture over it.

---

## 2. Setup

### 2.1 What you need on the machine

Assume your existing Windows dev environment plus:

| Item | Why | How |
|---|---|---|
| Python 3.11+ | The harness | Already present if the current benchmark runs |
| `pyyaml`, `python-frontmatter`, `rapidfuzz` | Parse OKF, fuzzy match | `pip install pyyaml python-frontmatter rapidfuzz` |
| Node.js 20+ | Only for the OKF validator/graph viewer | nodejs.org, LTS installer |
| The OKF spec | Ground truth | `github.com/GoogleCloudPlatform/knowledge-catalog` → `okf/SPEC.md` |
| A conformance validator | Checks your bundle is legal OKF | See §2.3 |

You do **not** need: a Google Cloud account, BigQuery, Gemini API access, or the reference enrichment agent. Explicitly skip all of it — see §2.2.

### 2.2 What you must NOT install — the compliance trap

Google's reference producer is an enrichment agent that walks a BigQuery dataset and runs LLM passes over it in the cloud. Do not use it, and do not let a coding agent quietly reach for it.

- **For this benchmark**, the data is public InLegalNER judgments. No DPDP exposure. You *could* technically use cloud tooling here without breaking any law.
- **In production**, the same producer would be walking real matters — party names, CNRs, client identities. Sending that to BigQuery or a cloud LLM breaks `10-Document-Intelligence-Local-Vault-Spec.md`'s guarantee that no document content or metadata leaves the device for classification, and breaks the residency posture in `05-Security-Compliance.md` §2.

If you build the benchmark producer as a cloud pipeline, you build something you can never ship. **Write the producer as a local Python script from day one**, so the benchmark artefact is the production artefact. This is the single most consequential setup decision in this guide.

### 2.3 Folder layout

Create this on your Windows machine:

```
Z:\Software\Stemple\okf-benchmark\
├── spec\
│   └── SPEC.md                  # downloaded copy of OKF v0.2, for the agent to read
├── producer\
│   └── build_bundle.py          # Step 3 output
├── bundle\
│   └── matters\                 # Step 3 output: 60 .md files + index.md + log.md
├── router\
│   ├── arm1_sqlite.py
│   ├── arm2_okf_parity.py
│   └── arm3_okf_multisignal.py
├── harness\
│   ├── run_benchmark.py
│   └── testset\                 # the 90 (or 190) test documents
├── results\
│   └── *.json
└── report\
    └── okf_benchmark_report.html
```

### 2.4 Conformance checking

There is a free open-source OKF conformance suite and validator maintained by WitsCode, tracking spec v0.2 and verified against Google's own reference bundles; it also ships a graph tool that renders any bundle as a self-contained interactive HTML file. Use it as an independent check — but treat the spec itself as authority. Third-party validators can lag or over-enforce; if the validator and `SPEC.md` §11 disagree, the spec wins.

Conformance under v0.2 §11 is deliberately minimal — your bundle passes if:
1. Every non-reserved `.md` file has a parseable YAML frontmatter block.
2. Every frontmatter block has a non-empty `type`.
3. `index.md` and `log.md` follow §8 and §9 when present.

Note what is *not* required: no optional fields, no known type values, no unbroken cross-links, no index files. Consumers must not reject a bundle for any of those.

---

## 3. Build the matter bundle

### 3.1 The concept schema

Each of the 60 matters becomes one file at `bundle/matters/LNER0002.md`. `type` is the only required field; everything below it is producer-defined, which the spec explicitly permits.

```markdown
---
type: Legal Matter
title: Parmar Samantsinh Umedsinh v. State of Gujarat
description: Criminal appeal against conviction, Gujarat High Court.
resource: casedesk://matter/LNER0002
tags: [criminal, gujarat-hc, appeal]
status: stable
generated: { by: casedesk_okf_producer/0.1, at: 2026-08-16T10:00:00Z }

# --- routing signals (producer-defined, CaseDesk-specific) ---
court: Gujarat High Court
bench_coram: ["Hon'ble Mr. Justice A B Sharma"]
case_number: R/CR.A/1234/2019
cnr_number: GJHC240012342019
matter_type: criminal
filing_date: 2019-03-14
last_order_date: 2021-08-11
statutes: ["IPC s.302", "IPC s.34", "CrPC s.374"]
parties:
  petitioners: ["Parmar Samantsinh Umedsinh"]
  respondents: ["State of Gujarat"]
party_aliases: ["Samantsinh Parmar", "S. Umedsinh Parmar"]
---

# Summary

One-paragraph matter description, built ONLY from matter-pool metadata.

# Parties

| Role | Name | Notes |
|---|---|---|
| Petitioner | Parmar Samantsinh Umedsinh | Appellant/accused no. 2 |
| Respondent | State of Gujarat | Through Public Prosecutor |

# Related Matters

Co-accused appeal heard alongside [LNER0028](/matters/LNER0028.md).
```

Three design notes:

- **`party_aliases` is doing real work.** Your `semantic_010` failure was a fuzzy match at confidence 1.000 that still picked the wrong matter — a name collision. An explicit alias list plus a distinct-name check is the cheapest fix available and it needs somewhere structured to live.
- **`statutes` and `court` are the contradiction-gate inputs.** A document citing a Bombay HC arbitration provision should never file into a Gujarat HC criminal appeal regardless of embedding score.
- **`generated.by` uses the actor convention** — `<producer>/<version>` for tools, `human:<id>` for people. If you hand-correct a concept, add `verified: { by: human:ravindra, at: ... }`. That is what makes a concept human-reviewed rather than machine-confirmed, and later it becomes the audit story for a firm asking who curated their matter graph.

### 3.2 Prompt 1 — the producer

> Copy this into your coding agent, verbatim. Attach `spec/SPEC.md` and the InLegalNER matter-pool source file.

```
Read the attached OKF v0.2 SPEC.md in full before writing any code.

Write a single local Python script at producer/build_bundle.py. Constraints:
1. No network calls of any kind. No cloud SDKs, no BigQuery, no LLM APIs. Pure
   local file I/O and stdlib plus pyyaml.
2. Input: the InLegalNER matter-pool metadata file (attached), containing the 60
   matters LNER0001..LNER0060.
3. Output: an OKF v0.2 conformant bundle at bundle/matters/, one .md file per
   matter, named <MATTER_ID>.md.
4. Frontmatter must follow exactly the schema in section 3.1 of the attached
   guide. type must be "Legal Matter". Omit any field for which the source data
   has no value — do NOT emit empty strings or nulls.
5. Body sections: "# Summary", "# Parties", "# Related Matters". The Summary
   must be assembled from matter-pool metadata fields ONLY. Under no
   circumstances read, ingest, or reference the test-document corpus.
6. "# Related Matters" links must be generated by a deterministic, stated rule,
   which you will print to stdout at the top of the run. Use exactly this rule:
   link two matters if they share a party name at rapidfuzz token_set_ratio
   >= 0.92, OR if they share the same court AND at least one identical statute
   AND their filing dates fall within 180 days of each other. No other links.
   Use bundle-relative link form: /matters/LNER0028.md
7. Also emit bundle/matters/index.md per SPEC.md section 8 (no frontmatter
   except okf_version: "0.2" at the bundle root index) and bundle/matters/log.md
   per section 9.
8. Print a summary table: matters written, average frontmatter fields populated,
   total cross-links, matters with zero cross-links.

Do not write the router. Do not write the harness. Only the producer.
```

### 3.3 Verify before proceeding

Run the validator. Then open the generated graph HTML and look at it with your own eyes. You are checking for:

- Any matter with a suspiciously specific summary → body leakage from test documents.
- A cross-link graph that is either fully connected (rule too loose, everything links to everything, graph carries no information) or fully disconnected (rule too tight, A3 has nothing to work with). Neither is usable. Aim for a mean degree of roughly 1–4.
- Fields populated at wildly different rates across matters — sparse frontmatter is realistic but if only 12 of 60 have `statutes`, A3's contradiction gate will almost never fire and the arm will look falsely neutral.

**That last point is the production-transfer risk, and it is the biggest hole in this entire experiment.** InLegalNER judgments are rich; you can extract court, statutes, bench, and dates from them. A real solo advocate opening a matter in CaseDesk types a title, maybe a case number, and moves on. If A3 wins here on the strength of `statutes` and `bench_coram`, and real matters have neither field populated, the improvement will not transfer to production at all. Before you invest in A3, decide how those fields get populated in the real product — and if the answer is "the advocate fills them in," be honest that the answer is really "they won't."

---

## 4. Build the three routers

### 4.1 Prompt 2 — Arm 1 (control)

```
Take the existing CaseDesk routing engine used to produce the
InLegalNER_CaseDesk_Benchmark report and wrap it, unmodified, behind this
interface at router/arm1_sqlite.py:

    def load_pool() -> Pool          # returns pool object, timed separately
    def route(doc_text: str, pool: Pool) -> RouteResult

RouteResult must be a dataclass with fields:
    matter_id: str | None
    status: Literal["filed", "needs_review"]
    method: Literal["deterministic", "fuzzy", "semantic", "slm", None]
    confidence: float | None
    contradiction_reasons: list[str]   # always empty for arm 1
    route_ms: float

Change NO matching logic, NO thresholds, NO model. This arm must reproduce
85.6% overall / 100.0% Stage B / 56.7% Stage C / 0 invariant violations. If it
does not reproduce those numbers within one document per stage, stop and report
the discrepancy rather than adjusting anything.
```

### 4.2 Prompt 3 — Arm 2 (format parity)

```
Write router/arm2_okf_parity.py implementing the same interface as
router/arm1_sqlite.py.

The ONLY difference from arm 1: load_pool() reads the OKF bundle at
bundle/matters/ instead of the SQLite mirror.

Critical parity requirements — violating any of these invalidates the experiment:
1. The text passed to the embedding model for each matter must be byte-identical
   to the text arm 1 embeds. Reconstruct it from the same frontmatter fields arm 1
   read from SQLite columns, concatenated in the same order. Do NOT embed the
   markdown body, the "# Related Matters" section, or any frontmatter field arm 1
   did not have access to.
2. The strings passed to the fuzzy matcher must be identical to arm 1's. Do NOT
   use party_aliases.
3. Identical thresholds, identical model, identical SLM fallback, identical
   stage ordering.
4. contradiction_reasons stays empty.
5. Time bundle load separately and expose it as pool.load_ms. Do not include it
   in route_ms.

Then write a parity self-check script that asserts, for all 60 matters, that
arm2's embedding input string == arm1's embedding input string. Run it and
report any mismatch. Do not proceed if any mismatch exists.
```

### 4.3 Prompt 4 — Arm 3 (OKF + §9)

```
Write router/arm3_okf_multisignal.py implementing the same interface.

It starts from arm 2 and adds four things, in this order:

1. MULTI-SIGNAL EXTRACTION. From the incoming document, extract with regex /
   deterministic rules only (no LLM): court name (match against a static known-
   courts list), case number patterns, CNR pattern, statute citations
   (e.g. "Section 302 IPC", "s. 34 IPC", "Article 226"), dates, and bench names.

2. CANDIDATE RETRIEVAL. Use the existing embedding similarity to retrieve the
   top 5 candidate matters, not the top 1.

3. RE-RANKING. Score each candidate as:
       final = 0.55 * semantic_similarity
             + 0.20 * statute_overlap        (Jaccard over statutes)
             + 0.15 * court_match            (1.0 exact, 0.0 otherwise)
             + 0.10 * date_proximity         (1.0 if any doc date within the
                                              matter's filing..last_order window)
   Additionally, boost by +0.05 for each candidate that is cross-linked in the
   OKF graph to another top-5 candidate that also scores above 0.70 (graph
   coherence). Cap final at 1.0.

4. CONTRADICTION GATE, applied last, before any filing decision. Force
   status="needs_review" and append a reason string if ANY of:
   - document court is confidently extracted AND != matter court
   - document case_number confidently extracted AND != matter case_number
   - document cites a statute in a matter_type category incompatible with the
     matter's matter_type (criminal doc vs arbitration matter, etc.)
   - the fuzzy party match is >= 0.95 but the matched name appears in
     party_aliases of two or more distinct matters (collision guard)

Thresholds are FIXED at the values above. Do not tune them against the test set.
Do not add any signal not listed here.

Populate contradiction_reasons on every RouteResult so the report can show why
the gate fired.
```

The graph-coherence boost in step 3 is the one component that genuinely requires OKF rather than a wider SQL schema. Everything else in A3 could be done with extra columns. Worth watching in the results: if you strip the graph boost and A3 performs identically, then the honest conclusion is that OKF bought you nothing and the win came from multi-signal scoring — which you should say plainly in the report rather than let the format take credit.

---

## 5. Run the benchmark

### 5.1 Prompt 5 — the harness

```
Write harness/run_benchmark.py.

It must:
1. Accept --arm {1,2,3} and --stages B,C,D.
2. Load the same test corpus for every arm, in the same order, with a fixed
   random seed. The identical document must be routed by all three arms — this
   is a PAIRED design.
3. For each document record: doc_id, stage, expected_matter, actual_matter,
   status, method, confidence, contradiction_reasons, route_ms.
4. Compute per stage and overall: matter_accuracy, autofile_precision,
   autofile_recall, review_rate, harmful_error_count (filed AND wrong),
   invariant_violations (Stage D docs not needs_review), p50_route_ms,
   p90_route_ms. Record bundle_load_ms once per arm, separately.
5. Compute a calibration table: accuracy bucketed by confidence in 0.05-wide
   bands from 0.60 to 1.00, with counts per band.
6. Write results/arm<N>_<timestamp>.json.
7. Run each arm 3 times and report the median plus min/max for all latency
   metrics. Accuracy metrics are deterministic and need one run — assert that
   they are identical across the three runs and fail loudly if not.

Then write harness/compare.py which loads all three result files and computes,
for each pair of arms (1v2, 1v3, 2v3) and each stage:
   - the 2x2 paired contingency table (both correct / only A / only B / neither)
   - McNemar's exact test p-value
   - the count of documents that changed outcome in each direction
Print a table. Do not report a difference as meaningful if p >= 0.05; label it
"not significant" explicitly.
```

### 5.2 Order of operations

1. Run Arm 1. **Confirm it reproduces 85.6% / 100.0% / 56.7% / 0 violations.** If it does not, the harness has drifted and every downstream number is untrustworthy. Fix before continuing.
2. Run the parity self-check from Prompt 3. Fix any mismatch.
3. Run Arm 2. Expect no significant change. Investigate any change over ~2 documents per stage.
4. Run Arm 3.
5. Run `compare.py`.

---

## 6. Generate the report

### 6.1 Prompt 6

```
Write report/build_report.py. It reads the three result JSON files plus the
compare.py output and emits a single self-contained HTML file at
report/okf_benchmark_report.html, styled to match the existing
InLegalNER_CaseDesk_Benchmark PDF (same section structure, same table style,
same page furniture).

Required sections:
1. Executive summary — headline table: three arms x (overall accuracy,
   harmful_error_count, invariant_violations, p50 latency).
2. Method — the three arms, the parity constraint, the contamination controls,
   and an explicit statement of the sample size and its power limitation.
3. Per-stage results — one table per stage, three columns (A1/A2/A3).
4. Paired significance — the McNemar tables and p-values. Every non-significant
   result must be labelled "not significant (n=NN, p=0.NN)" in the prose, not
   just the table.
5. Safety — autofile_precision and harmful_error_count per arm, with each
   harmful error listed individually (doc_id, expected, actual, confidence,
   method). Stage D invariant compliance stated separately as a pass/fail gate.
6. Calibration — accuracy-by-confidence-band chart per arm, with the 0.75-0.82
   band highlighted (the band that produced the baseline's failures).
7. Contradiction gate analysis (A3) — trigger rate, reason breakdown, and how
   many triggers were correct saves vs. false alarms that cost a good auto-file.
8. Latency — route latency per stage per arm, with bundle_load_ms reported
   separately and explicitly excluded from route latency.
9. Limitations — must include: sample size, field-density difference between
   InLegalNER judgments and real CaseDesk matter records, and the fact that
   cross-links were rule-generated rather than expert-curated.
10. Conclusion.

Use inline SVG for charts. No external CDN, no network fetch at render time.
```

### 6.2 How to read the output — decision rules, set now

Commit to these before you see the numbers.

| Observation | Conclusion |
|---|---|
| A2 ≈ A1 (within noise) | Format is signal-neutral. Correct. Proceed. |
| A2 differs materially from A1 | Parity bug. The experiment is invalid. Do not report A3. |
| A3 > A1 on Stage C, p < 0.05, `harmful_error_count` ≤ A1 | §9 features work. Adopt them. Separately decide whether OKF or extra SQL columns is the better carrier. |
| A3 > A1 but `harmful_error_count` increased | **Reject.** More wrong auto-files is not a win at any accuracy. |
| A3 > A1 but p ≥ 0.05 | Directional only. Expand the test set before deciding. |
| A3 ≈ A1 | The §9 recommendations did not pay off at this pool size. More likely a sparsity problem than a wrong idea — check field population rates first. |
| Any arm has `invariant_violations` > 0 | Hard fail. That invariant is a production gate per report §9.5. |

---

## 7. Risks and honest loopholes

**The format is probably not the active ingredient.** Almost everything A3 does — statute overlap, court matching, date windows, alias collision guards — could be implemented against a slightly wider SQLite schema with no OKF at all, and it would be faster and simpler. Only the graph-coherence boost genuinely needs the linked-document structure. Go in expecting the answer "the §9 features helped, the format was incidental," and build the experiment so you can actually detect that rather than hide it.

**The field-density gap is the real threat to validity.** Covered in §3.3. Restating because it is the thing most likely to make this entire benchmark not transfer: rich public judgments are not sparse user-entered matter records.

**Adopting OKF has a real production cost.** Your local vault already stores matters in SQLite for PowerSync. Adding a markdown bundle means either a second representation to keep in sync — a class of bug you do not want on an offline-first product with conflict resolution — or replacing SQLite reads for routing, which means the router no longer shares a data path with the rest of the app. Neither is free. This benchmark should be a precondition for that decision, not an assumption behind it.

**There is a strategic upside the accuracy numbers will not show.** A per-matter markdown concept with `generated`/`verified` actors and a `sources` trail is an audit artefact a legally sophisticated buyer can read. "Here is exactly what the system knew about your matter, who curated it, and when it was last confirmed" is a differentiator for an audience that thinks in terms of records. That value is real and is entirely independent of whether Stage C moves from 56.7%. Do not let it contaminate the accuracy read — but do not discard it either.

**Sequencing.** Do not run this against a production CaseDesk build. Everything here is offline, against public data, in a scratch directory. Nothing in this experiment should touch the Local Vault or the PowerSync schema until the results are in.

---

## 8. Sequence checklist

- [ ] Download OKF v0.2 `SPEC.md` into `spec/`
- [ ] Install Python deps and Node
- [ ] Decide: expand Stage C to 100+ docs, or accept directional-only findings (§1.4)
- [ ] Prompt 1 → producer → 60-file bundle
- [ ] Validate conformance; inspect the graph visually (§3.3)
- [ ] Audit field population rates across the 60 matters
- [ ] Prompt 2 → Arm 1 → **reproduce the 85.6% baseline**
- [ ] Prompt 3 → Arm 2 → **pass the parity self-check**
- [ ] Run Arm 2, confirm no significant delta
- [ ] Prompt 4 → Arm 3
- [ ] Prompt 5 → harness → run all three arms, 3x each
- [ ] Run `compare.py`, get McNemar p-values
- [ ] Prompt 6 → report
- [ ] Apply the §6.2 decision table before interpreting anything
