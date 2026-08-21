# **CaseDesk** 

InLegalNER Real-Document Routing Benchmark 

### **Benchmark Report** 

Evaluation of matter-routing performance on genuine Indian court judgments 

**Matter Pool** 60 real cases **Test Documents** 90 real documents **Overall Accuracy 85.6% SLM Invariant Violations 0 Elapsed Time** 49.3 seconds **Throughput** 1.8 documents/second 

Benchmark based on genuine Indian court judgments from the InLegalNER development split. Matter pool constructed from 60 identified real cases; the test set contains 50 additional real documents. 

August 13, 2026 

**CaseDesk** 

InLegalNER Routing Benchmark 

## **1 Executive Summary** 

This report presents the evaluation of the **CaseDesk routing engine** on real Indian legal documents drawn from the InLegalNER development split. The benchmark is designed to test progressively harder matter-identification conditions, ranging from fuzzy party-name matching to semantic retrieval from anonymous legal reasoning text. 

The benchmark contains a **60-case real matter pool** and **90 test documents** . CaseDesk correctly handled 77 of the 90 documents, producing an overall accuracy of **85.6%** . Most importantly, the SLM fallback stage maintained its safety invariant across all 30 anonymous-text cases: **zero documents were auto-filed when the system lacked reliable identifying evidence** . 

<u>Table 1: Overall benchmark results</u> 

|**Metric**|**Value**|
|---|---|
|Matter Pool (real cases)|60|
|Total Test Documents|90|
|Total Correct|77 (85.6%)|
|**Overall Accuracy**|**85.6%**|
|SLM Invariant Violations|**0**|
|Elapsed Time|49.3 s|
|Throughput|1.8 docs/s|



The results show a clear distinction between deterministic/fuzzy identification and semanticonly identification. Stage B achieved perfect performance at 100.0%, while Stage C remains the primary accuracy bottleneck at 56.7%. Stage D, although slower, successfully preserved the required conservative behavior in every case. 

## **2 Benchmark Design** 

The benchmark evaluates CaseDesk under three routing conditions: 

1. **Stage B – Fuzzy Party Match:** identifying a matter using petitioner/respondent names from OCR-derived judgment text, with case numbers removed. 

2. **Stage C – Semantic Match:** identifying a matter after both case numbers and header party-name lines have been removed, requiring semantic similarity over the legal content. 

3. **Stage D – SLM Fallback:** processing anonymous legal reasoning text where there is insufficient evidence for safe automatic filing. 

The benchmark intentionally removes increasingly strong identifiers so that the routing engine is evaluated not only on easy exact-match scenarios, but also on ambiguity and uncertainty. 

### **2.1 Data Composition** 

The matter pool consists of 60 identified real cases. The test corpus contains 90 real documents distributed evenly across the three evaluation stages, with 30 documents per stage. 

Page 1 of 7 

**CaseDesk** 

InLegalNER Routing Benchmark 

Table 2: Benchmark composition 

|**Stage**|**Documents**|**Primary Evaluation**|
|---|---|---|
|B|30|Fuzzy party matching|
|C|30|Semantic matter matching|
|D|30|Conservative SLM fallback|
|**Total**|**90**||



## **– 3 Stage B Fuzzy Party Match** 

### **3.1 Evaluation Condition** 

Stage B uses genuine judgment text with **case numbers stripped** . The routing engine must identify the correct matter using petitioner/respondent names extracted from the document. The fuzzy matching engine uses: 

`rapidfuzz token_set_ratio` _≥_ 0 _._ 85 

A document is considered correct when: 

`actual_matter_id = expected_matter_id` _._ 

### **3.2 Results** 

Table 3: Stage B results 

|**Metric**|**Value**|
|---|---|
|Documents|30|
|Correct|30|
|**Accuracy**|**100.0%**|
|P50 Route Latency|97.9 ms|
|P90 Route Latency|262.2 ms|



Stage B achieved **perfect accuracy** . This demonstrates that when reliable party-name evidence survives OCR and is available to the router, fuzzy matching is highly effective for linking documents to the correct matter. 

The result also provides a strong baseline for the downstream semantic stages: the routing system does not need to invoke more expensive semantic or SLM reasoning when a sufficiently strong party-level identifier is available. 

## **– 4 Stage C Semantic Match** 

### **4.1 Evaluation Condition** 

Stage C removes both: 

- case numbers, and 

- header party-name lines. 

Page 2 of 7 

**CaseDesk** 

InLegalNER Routing Benchmark 

The remaining document therefore consists primarily of legal content. The routing engine must infer the correct matter from semantic similarity rather than explicit identifiers. The pass condition is: 

`actual_matter_id = expected_matter_id` _._ 

Both `filed` and `needs_review` outcomes are accepted for the purpose of evaluating matter identification. 

### **4.2 Results** 

Table 4: Stage C results 

|**Metric**|**Value**|
|---|---|
|Documents|30|
|Correct|17|
|**Accuracy**|**56.7%**|
|P50 Route Latency|108.6 ms|
|P90 Route Latency|211.5 ms|



Stage C is the principal source of benchmark error. Only 17 of 30 documents were assigned to the expected matter, resulting in **56.7% accuracy** . 

The failures indicate that semantic similarity alone can be insufficient when multiple legal matters share overlapping factual patterns, legal terminology, parties operating in similar domains, or common procedural language. Several incorrect matches nevertheless received moderate confidence scores, suggesting that the semantic retrieval layer can identify legally related documents without necessarily distinguishing the precise underlying matter. 

This stage therefore represents the most important opportunity for future improvement. 

## **– 5 Stage D SLM Fallback** 

### **5.1 Evaluation Condition** 

Stage D consists of real legal excerpts containing no reliably identified parties. The input is intentionally limited to **anonymous legal reasoning text** . 

In this setting, the system is required to remain conservative. The pass condition is: 

`actual_status = needs_review` _._ 

The matter identifier is deliberately flexible: it may be `None` or contain a suggestion because the benchmark’s invariant concerns the routing status rather than matter identification. 

Page 3 of 7 

**CaseDesk** 

InLegalNER Routing Benchmark 

### **5.2 Results** 

Table 5: Stage D results 

|**Metric**|**Value**|
|---|---|
|Documents|30|
|Invariant Upheld|30|
|**Accuracy**|**100.0%**|
|P50 Route Latency|1003.1 ms|
|P90 Route Latency|1323.3 ms|



The SLM fallback stage upheld its safety invariant on **all 30 documents** . No anonymous legal excerpt was incorrectly auto-filed. 

This is a particularly important result for a legal document-routing system. In an ambiguous setting, the system prioritizes uncertainty handling over forced classification. The trade-off is latency: Stage D is substantially slower than Stages B and C, with a P50 latency of approximately 1.0 seconds and a P90 latency of approximately 1.32 seconds. 

## **6 Failure Analysis** 

There were **13 failures out of 90 test documents** . All reported failures occurred in Stage C. 

Table 6: Stage C failure cases 

|**ID**|**Exp.**<br>**Matter**|**Act.**<br>**Matter**|**Statu**|**s**<br>**Method**|**Conf.**|**Petitioner**|
|---|---|---|---|---|---|---|
|semantic_|002<br>LNER-<br>0002|LNER-<br>0028|needs_|review<br>semantic|0.768|Parmar<br>Samantsinh<br>Umedsinh|
|semantic_|006<br>LNER-<br>0006|LNER-<br>0041|needs_|review<br>semantic|0.776|G.Balasubramanian|
|semantic_|009<br>LNER-<br>0009|LNER-<br>0036|needs_|review<br>semantic|0.746|Tata<br>Mo-<br>tors|
|||||||Lim-<br>ited|
|semantic_|010<br>LNER-<br>0010|LNER-<br>0015|fled|fuzzy|1.000|Cobra<br>Indus-<br>trial<br>Secu-<br>rity<br>Forc|
|semantic_|014<br>LNER-<br>0014|LNER-<br>0028|needs_|review<br>semantic|0.760|Jsb<br>Cargo<br>And<br>Freight<br>For-<br>warde|
|semantic_|015<br>LNER-<br>0015|LNER-<br>0016|fled|semantic|0.821|Sanjay<br>Singh|



Page 4 of 7 

**CaseDesk** 

InLegalNER Routing Benchmark 

|**ID**|**Exp.**<br>**Matter**|**Act.**<br>**Matter**|**Statu**|**s**<br>**Method**|**Conf.**|**Petitioner**|
|---|---|---|---|---|---|---|
|semantic_|016<br>LNER-<br>0016|LNER-<br>0043|needs_|review<br>semantic|0.798|Vimal<br>Anand|
|semantic_|017<br>LNER-<br>0017|LNER-<br>0049|needs_|review<br>semantic|0.764|Action<br>Ispat<br>And<br>Power<br>Pvt.<br>Lt|
|semantic_|018<br>LNER-<br>0018|LNER-<br>0013|needs_|review<br>semantic|0.792|New<br>India<br>As-|
|||||||sur-<br>ance<br>Co.<br>Ltd|
|semantic_|020<br>LNER-<br>0020|LNER-<br>0013|needs_|review<br>semantic|0.796|Bharat<br>Singh|
|semantic_|021<br>LNER-<br>0021|None|needs_|review<br>None|—|S.Ganesh|
|semantic_|023<br>LNER-<br>0023|LNER-<br>0019|needs_|review<br>semantic|0.752|Ifci<br>Re-<br>tirees<br>Wel-<br>fare<br>Fo-|
|||||||rum|
|semantic_|030<br>LNER-|LNER-|needs_|review<br>semantic|0.808|Nathu|
||0030|0020||||Singh|



### **6.1 Observed Failure Pattern** 

The failures are concentrated in semantic routing, rather than in the fuzzy party-matching or SLM safety layers. Most semantic errors resulted in `needs_review` , which means the system often recognized that its evidence was insufficient for confident filing even when its suggested matter was incorrect. 

The confidence values for most semantic failures fall between approximately 0.75 and 0.81. This suggests a useful avenue for calibration: semantic similarity scores in this range may not provide enough evidence to distinguish between closely related matters and could be routed directly to human review rather than being treated as a definitive matter match. 

One exception is `semantic_015` , where the semantic matcher returned a confidence of 0.821 and filed the document into LNER-0016 instead of the expected LNER-0015. This illustrates the risk of auto-filing on semantic evidence alone even when the similarity score appears relatively strong. 

Another notable case is `semantic_010` , where a fuzzy match produced a confidence of 1.000 but selected the wrong matter. This indicates that a high fuzzy similarity score can still be misleading when party names are similar or when OCR/text normalization produces collisions. Such cases support the use of cross-checking signals rather than relying on a single score. 

Page 5 of 7 

**CaseDesk** 

InLegalNER Routing Benchmark 

## **7 Performance Analysis** 

The benchmark demonstrates three distinct latency profiles. 

Table 7: Latency comparison across routing stages 

|**Sta**|**ge**|**P**|**50**|**P**|**90**|
|---|---|---|---|---|---|
|B –|Fuzzy Match|97.9|ms|262.2|ms|
|C –|Semantic Match|108.6|ms|211.5|ms|
|D –|SLM Fallback|1003.1|ms|1323.3|ms|



Stages B and C have comparable median routing latency, remaining close to 100 ms. The SLM fallback is approximately an order of magnitude slower at the median, reflecting the additional inference cost. 

Despite this, the overall benchmark completed in **49.3 seconds** at a throughput of **1.8 documents per second** . The results indicate that the architecture can efficiently handle documents with strong identifiers while reserving the more expensive SLM fallback for cases where deterministic and semantic evidence is insufficient. 

## **8 Key Findings** 

1. **Strong identifier routing is highly reliable.** Stage B achieved 100.0% accuracy on 30 real documents when party information was available. 

2. **Semantic-only routing is the main accuracy bottleneck.** Stage C achieved 56.7% accuracy after explicit identifiers were removed. 

3. **The SLM safety invariant is robust.** All 30 anonymous-text cases correctly resulted in `needs_review` ; there were zero invariant violations. 

4. **The system is conservative under uncertainty.** Many semantic failures resulted in `needs_review` rather than incorrect automatic filing. 

5. **Latency is dominated by the fallback path.** Stage D has a P50 latency of 1003.1 ms compared with approximately 100 ms for Stages B and C. 

6. **The next improvement target should be semantic disambiguation.** Improving the distinction between legally similar matters is likely to produce the largest accuracy gain. 

## **9 Recommended Next Steps** 

Based on the benchmark results, the following improvements are recommended: 

1. **Introduce multi-signal semantic routing.** Combine semantic similarity with extracted entities, dates, case events, court/bench information, legal sections, cited cases, and document structure rather than relying on embedding similarity alone. 

2. **Calibrate semantic confidence thresholds.** Scores in the approximately 0.75–0.82 range produced several incorrect matter suggestions. A calibrated threshold could reduce false auto-routing at the cost of increasing human review. 

3. **Use candidate re-ranking.** Retrieve a small set of candidate matters semantically and then apply a second-stage cross-encoder or structured comparison model to distinguish highly similar legal matters. 

Page 6 of 7 

**CaseDesk** 

InLegalNER Routing Benchmark 

4. **Add contradiction checks.** Before filing, compare extracted parties, dates, court, case type, legal sections, and other available metadata against the candidate matter. A strong contradiction should force `needs_review` . 

5. **Preserve conservative SLM behavior.** The zero-violation result in Stage D should be treated as a hard production invariant: anonymous legal text must never be auto-filed solely on an SLM guess. 

6. **Expand the real-document benchmark.** Continue evaluating on additional genuine judgments and introduce harder cases with OCR corruption, buried headers, multiple parties, similar party names, and legally overlapping matters. 

## **10 Conclusion** 

The CaseDesk InLegalNER benchmark demonstrates that the routing architecture performs strongly when reliable party identifiers are available and remains safely conservative when the available evidence is insufficient. 

Across 90 real legal documents, the system achieved **85.6% overall accuracy** , with **100.0% accuracy in fuzzy party matching** and **100.0% compliance with the SLM fallback invariant** . The principal weakness is semantic-only matter identification, where accuracy fell to **56.7%** after case numbers and header party names were removed. 

The benchmark therefore provides a clear engineering roadmap: retain the existing deterministic and conservative safeguards, while investing most heavily in semantic candidate disambiguation, confidence calibration, and multi-signal verification. The current results establish a meaningful real-document baseline for subsequent iterations of the CaseDesk routing engine. 

_CaseDesk InLegalNER Routing Benchmark_ 

Page 7 of 7 

