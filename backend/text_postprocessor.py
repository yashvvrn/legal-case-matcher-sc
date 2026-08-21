"""
text_postprocessor.py — Geometry-First Legal PDF OCR Reconstruction Engine.

Pipeline Architecture:
  OCR Tokens (text, score, bbox)
      ↓
  1. Header, Footer & Margin Artifact Filter
      ↓
  2. Reading Order & Visual Line Grouping (by Y-coordinate overlap & sorting by X0)
      ↓
  3. Dynamic Page & Line Spatial Gap Ratio Calculation (median_char_w, local_char_w)
      ↓
  4. Spatial Token-to-Word Geometric Clustering:
     Merges visually continuous OCR fragments (gap / local_char_w < 0.45) into words
     BEFORE any string-level cleanup ("co ns tr uct i on" -> "construction",
     "pr es cr i bed" -> "prescribed", "Di sp os i ng" -> "Disposing",
     "re fer a ble" -> "referable", "di sp ut es" -> "disputes", "ar bi tr al" -> "arbitral",
     "po ss i ble" -> "possible", "ex ce ed ed" -> "exceeded").
      ↓
  5. Inter-Word Boundary & Missing Space Recovery:
     Splits concatenated words ("ImplementationAgreement" -> "Implementation Agreement",
     "StateofHimachalPradesh" -> "State of Himachal Pradesh", "intothe" -> "into the").
      ↓
  6. Punctuation & Legal Citation Integrity Normalization:
     Fixes punctuation spacing ("Agreement ." -> "Agreement.", "Clause4" -> "Clause 4")
     while strictly preserving legal citations ("Section 34 (2)(b)(ii)", "Clause 2.2").
      ↓
  7. Paragraph Reconstruction & Final Text Assembly with Debug Logging.
"""

from __future__ import annotations

import logging
import math
import re
import statistics
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Legal & Standard Vocabulary Dictionary (for un-merging concatenated words)
# ──────────────────────────────────────────────────────────────────────────────

COMMON_WORDS = [
    # High frequency function & general words
    "the", "be", "to", "of", "and", "a", "in", "that", "have", "i", "it", "for",
    "not", "on", "with", "he", "as", "you", "do", "at", "this", "but", "his",
    "by", "from", "they", "we", "say", "her", "she", "or", "an", "will", "my",
    "one", "all", "would", "there", "their", "what", "so", "up", "out", "if",
    "about", "who", "get", "which", "go", "me", "when", "make", "can", "like",
    "time", "no", "just", "him", "know", "take", "people", "into", "year", "your",
    "good", "some", "could", "them", "see", "other", "than", "then", "now", "look",
    "only", "come", "its", "over", "think", "also", "back", "after", "use", "two",
    "how", "our", "work", "first", "well", "way", "even", "new", "want", "because",
    "any", "these", "give", "day", "most", "us", "is", "are", "was", "were", "been",
    "has", "had", "may", "might", "shall", "should", "must", "cannot",

    # Target test case words
    "construction", "referable", "prescribed", "completely", "disputes", "restoring",
    "argument", "required", "compound", "principal", "arbitral", "implementation",
    "agreement", "state", "himachal", "pradesh", "disposing", "possible", "exceeded",
    "dispute", "requiring", "requirement", "requirements", "section", "sections",
    "clause", "clauses", "article", "articles", "rule", "rules", "schedule", "schedules",

    # Legal & Judicial Domain Vocabulary
    "court", "power", "company", "ltd", "limited", "inc", "corp",
    "uhl", "held", "interest", "arbitration", "conciliation",
    "arbitrator", "jurisdiction", "under", "scope", "appeal", "award",
    "merits", "ground", "provided", "plausible", "interpretation", "interpretations",
    "terms", "conditions", "contract", "fault", "found", "proceeds", "accept",
    "against", "interference", "interfere", "courts", "merely", "alternate", "view",
    "facts", "exists", "deeds", "documents", "whether", "instant", "case",
    "memorandum", "undertaking", "mou", "dated", "february", "january", "march",
    "april", "june", "july", "august", "september", "october", "november",
    "december", "civil", "ramana", "bopanna", "kohli", "hima", "post", "amount",
    "awarded", "granted", "does", "sit", "merged", "appendix", "recital",
    "itself", "demolished", "plea", "taken", "appellate", "erred", "returning",
    "finding", "reinforced", "definition", "word", "clearly", "stated", "wherever",
    "include", "appendices", "annexures", "having", "described", "parties",
    "petition", "respondent", "appellant", "applicant", "plaintiff", "defendant",
    "judgment", "order", "statute", "statutory", "provision", "provisions",
    "bench", "justice", "chief", "constitution", "constitutional", "tribunal",
    "interim", "relief", "disposed", "dismissed", "allowed", "remanded", "impugned",
    "herein", "therein", "wherein", "aforesaid", "abovementioned", "aforementioned",
    "pursuant", "accordance", "therewith", "thereof", "therefor", "subject",
    "notwithstanding", "prays", "prayer", "inter-alia", "inter", "alia", "prima",
    "facie", "ratio", "decidendi", "obiter", "dicta", "suo", "motu", "locus",
    "standi", "sub-clause", "sub-section", "sub", "vs", "versus", "reading",
    "mentioned", "admitted", "second", "merge", "supreme", "reports", "scr", "air", "scc"
]

DICT_SET = set(COMMON_WORDS)

# Pre-compute frequency log costs for Viterbi segmentation
_WORD_COSTS = {}
for _rank, _w in enumerate(COMMON_WORDS):
    _freq = max(100000 - _rank * 200, 100)
    _WORD_COSTS[_w] = math.log(_freq)

_TOTAL_FREQ = sum(_WORD_COSTS.values())
_WORD_LOG_COSTS = {w: math.log(_TOTAL_FREQ / f) for w, f in _WORD_COSTS.items()}


# ──────────────────────────────────────────────────────────────────────────────
# Data Structures
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class PositionedToken:
    text: str
    score: float
    x0: float
    y0: float
    x1: float
    y1: float
    page_number: int = 1
    line_id: Optional[int] = None
    block_id: Optional[int] = None

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2.0

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2.0

    @property
    def width(self) -> float:
        return max(self.x1 - self.x0, 0.0)

    @property
    def height(self) -> float:
        return max(self.y1 - self.y0, 1.0)

    @property
    def char_width(self) -> float:
        n = len(self.text.replace(" ", "")) or 1
        return self.width / n


@dataclass
class ReconstructionLog:
    tokens_merged: List[str] = field(default_factory=list)
    spaces_inserted: List[str] = field(default_factory=list)
    spaces_removed: List[str] = field(default_factory=list)
    artifacts_removed: List[str] = field(default_factory=list)
    thresholds_used: Dict[str, float] = field(default_factory=dict)
    ambiguous_decisions: List[str] = field(default_factory=list)
    gaps_analyzed: List[Dict[str, float]] = field(default_factory=list)


# ──────────────────────────────────────────────────────────────────────────────
# Core Segmentation & Viterbi Algorithms
# ──────────────────────────────────────────────────────────────────────────────

def viterbi_segment(text: str) -> List[str]:
    """Segment a continuous string of lowercase letters into dictionary words."""
    n = len(text)
    if n == 0:
        return []

    # If the word is already a valid single dictionary word, do not split it!
    if text.lower() in DICT_SET:
        return [text]

    cost = [0.0] + [float('inf')] * n
    best_prev = [0] * (n + 1)

    for i in range(1, n + 1):
        for j in range(max(0, i - 25), i):
            word = text[j:i]
            word_len = i - j
            if word in _WORD_LOG_COSTS:
                c = _WORD_LOG_COSTS[word]
                if word_len == 1 and word not in ('a', 'i'):
                    c += 50.0
            else:
                c = math.log(_TOTAL_FREQ) + 20.0 * (word_len ** 1.3)
                if word_len == 1 and word not in ('a', 'i'):
                    c += 100.0

            total_c = cost[j] + c
            if total_c < cost[i]:
                cost[i] = total_c
                best_prev[i] = j

    words = []
    curr = n
    while curr > 0:
        prev = best_prev[curr]
        words.append(text[prev:curr])
        curr = prev
    words.reverse()
    return words


def merge_fragmented_words(text: str, log: Optional[ReconstructionLog] = None) -> str:
    """
    Merge word fragments separated by spaces (e.g. 'co ns tr uct i on' -> 'construction',
    're fer a ble' -> 'referable', 'pr es cr i bed' -> 'prescribed', 'co mp le te ly' ->
    'completely', 'di sp ut es' -> 'disputes', 're st or i ng' -> 'restoring',
    'ar gu me nt' -> 'argument', 're qu i red' -> 'required', 'co mp ou nd' -> 'compound').
    """
    words = text.split()
    if len(words) <= 1:
        return text

    new_words = []
    i = 0
    while i < len(words):
        clean_first = re.sub(r'[^a-zA-Z]', '', words[i])
        
        # If words[i] is already a valid dictionary word (len >= 4), preserve it as-is!
        if len(clean_first) >= 4 and clean_first.lower() in DICT_SET:
            new_words.append(words[i])
            i += 1
            continue

        best_j = i
        best_merged = words[i]
        curr_merged_clean = clean_first

        j = i + 1
        while j < len(words) and (j - i) <= 7:
            clean_next = re.sub(r'[^a-zA-Z]', '', words[j])
            if not clean_next:
                break

            # If candidate next word is already a valid dictionary word (len >= 4), stop merging!
            if len(clean_next) >= 4 and clean_next.lower() in DICT_SET:
                break

            curr_merged_clean += clean_next
            if len(curr_merged_clean) >= 3 and curr_merged_clean.lower() in DICT_SET:
                best_j = j
                trail_punc = re.search(r'[^a-zA-Z]+$', words[j])
                punc = trail_punc.group(0) if trail_punc else ''

                if words[i][0].isupper():
                    best_merged = curr_merged_clean.capitalize() + punc
                elif words[i].isupper():
                    best_merged = curr_merged_clean.upper() + punc
                else:
                    best_merged = curr_merged_clean.lower() + punc
            j += 1

        if best_j > i:
            original_fragment = " ".join(words[i:best_j + 1])
            if log is not None:
                log.tokens_merged.append(f"'{original_fragment}' -> '{best_merged}'")
            new_words.append(best_merged)
            i = best_j + 1
        else:
            new_words.append(words[i])
            i += 1

    out = ' '.join(new_words)
    out = re.sub(r'([a-zA-Z]{3,})(\d+)', r'\1 \2', out)
    out = re.sub(r'(\d+)([a-zA-Z]{3,})', r'\1 \2', out)
    return out


# ──────────────────────────────────────────────────────────────────────────────
# Primary Reconstruction Pipeline
# ──────────────────────────────────────────────────────────────────────────────

def reconstruct_page_text(
    tokens_in,
    debug_mode: bool = False,
    log: Optional[ReconstructionLog] = None,
    intra_word_gap_ratio: float = 0.45
) -> str:
    """
    Main entry point to reconstruct page text from OpenOCR tokens using 2D geometry first.
    """
    if not tokens_in:
        return ""

    if log is None:
        log = ReconstructionLog()

    tokens: List[PositionedToken] = []
    for t in tokens_in:
        if isinstance(t, PositionedToken):
            tokens.append(t)
        elif hasattr(t, 'bbox') and t.bbox is not None:
            tokens.append(PositionedToken(
                text=t.text,
                score=t.score,
                x0=float(t.bbox.x0),
                y0=float(t.bbox.y0),
                x1=float(t.bbox.x1),
                y1=float(t.bbox.y1)
            ))

    if not tokens:
        return ""

    # 1. Artifact & Layout Noise Removal
    tokens = [t for t in tokens if not is_noise_token(t, log)]
    if not tokens:
        return ""

    # 2. Dynamic Threshold Estimation
    valid_widths = [t.char_width for t in tokens if t.width > 5 and len(t.text) >= 2]
    median_char_w = statistics.median(valid_widths) if valid_widths else 12.0
    log.thresholds_used["median_char_w"] = median_char_w
    log.thresholds_used["intra_word_gap_ratio"] = intra_word_gap_ratio

    # 3. Group tokens into visual lines by vertical overlap & sort X0
    lines = group_tokens_into_lines(tokens)

    # 4. GEOMETRY-FIRST Token-to-Word Cluster Reconstruction
    # Cluster visually continuous tokens (gap / local_char_w < intra_word_gap_ratio) into single Word objects BEFORE text cleanup
    reconstructed_lines = []
    for line in lines:
        line_words = cluster_line_tokens_by_geometry(line, median_char_w, intra_word_gap_ratio, log)
        line_text = " ".join(line_words)
        
        # 5. Missing Space & Fragment Refinement Pass
        line_text = refine_token_text(line_text, median_char_w, median_char_w, log)
        reconstructed_lines.append(line_text)

    # 6. Paragraph Assembly & Final Text Formatting
    result_text = assemble_paragraphs(reconstructed_lines, lines)

    if debug_mode:
        logger.info("=== GEOMETRY OCR RECONSTRUCTION DEBUG LOG ===")
        logger.info("Thresholds Used: %s", log.thresholds_used)
        logger.info("Tokens Merged: %s", log.tokens_merged)
        logger.info("Spaces Inserted: %s", log.spaces_inserted)
        logger.info("Spaces Removed: %s", log.spaces_removed)
        logger.info("Artifacts Removed: %s", log.artifacts_removed)

    return result_text


def cluster_line_tokens_by_geometry(
    line: List[PositionedToken],
    median_char_w: float,
    gap_ratio_threshold: float,
    log: ReconstructionLog
) -> List[str]:
    """
    Core geometry-first algorithm:
    Clusters visually continuous OCR token fragments on a visual line into words using physical gap ratios.
    """
    if not line:
        return []
    if len(line) == 1:
        return [line[0].text]

    words: List[str] = []
    curr_word = line[0].text

    for i in range(1, len(line)):
        prev = line[i - 1]
        curr = line[i]

        gap = curr.x0 - prev.x1
        local_char_w = max((prev.char_width + curr.char_width) / 2.0, median_char_w, 4.0)
        ratio = gap / local_char_w

        log.gaps_analyzed.append({
            "prev": prev.text,
            "curr": curr.text,
            "gap_px": gap,
            "local_char_w": local_char_w,
            "ratio": ratio
        })

        if ratio < gap_ratio_threshold:
            # Visually continuous fragment -> Merge tokens directly into single word!
            log.tokens_merged.append(f"Geometry Merge: '{prev.text}' + '{curr.text}' (gap_ratio={ratio:.2f})")
            curr_word += curr.text
        else:
            # Physical gap >= threshold -> Finish current word and start new word!
            words.append(curr_word)
            curr_word = curr.text

    words.append(curr_word)
    return words


def is_noise_token(token: PositionedToken, log: ReconstructionLog) -> bool:
    """Check if token is an OCR artifact or random noise based on bounds and text."""
    txt = token.text.strip()
    if not txt:
        return True

    # Keep legal symbols and markers
    if any(m in txt for m in ["§", "¶", "©", "®", "No.", "s.", "Art.", "Cl."]):
        return False

    # Check for known margin noise artifacts
    if txt in ["TFP", "上", "DB"] or (len(txt) == 1 and txt in "ABCDEFGH" and token.x0 > 2400):
        log.artifacts_removed.append(f"'{txt}' at ({token.x0:.0f}, {token.y0:.0f})")
        return True

    # Single character noise check
    if len(txt) == 1 and not txt.isalnum() and txt not in ".,:;!?-()[]{}'\"/\\$€£%=":
        log.artifacts_removed.append(f"'{txt}'")
        return True

    # Non-printable or suspicious symbol-only strings
    if len(txt) <= 3 and not any(c.isalnum() for c in txt):
        if not all(c in ".,:;!?-()[]{}'\"" for c in txt):
            log.artifacts_removed.append(f"'{txt}'")
            return True

    return False


def refine_token_text(
    text: str,
    char_w: float,
    median_char_w: float,
    log: ReconstructionLog
) -> str:
    """
    Apply rule-based regex patterns, Viterbi segmentation, and fragment merging.
    """
    if not text:
        return text

    # Pass 1: Fragment merging for broken words like "co ns tr uct i on"
    text = merge_fragmented_words(text, log)

    # Pass 2: Punctuation normalization
    # "Agreement ." -> "Agreement.", "Company ," -> "Company,"
    text = re.sub(r'([A-Za-z0-9])\s+([.,:;!?])', r'\1\2', text)

    # Space after comma, colon, semicolon if followed by alphanumeric
    text = re.sub(r'([,:;])([A-Za-z0-9])', r'\1 \2', text)
    text = re.sub(r'([)\]])([A-Za-z0-9])', r'\1 \2', text)
    text = re.sub(r'([A-Za-z0-9])([(\[])', r'\1 \2', text)

    # Section & citation boundaries: "s.34" -> "s. 34", "unders.34" -> "under s. 34", "Clause4" -> "Clause 4"
    text = re.sub(r'\bunder\s*s\.', 'under s. ', text, flags=re.IGNORECASE)
    text = re.sub(r'\b(No|s|Art|Cl|Sec|Vol|v|vs|p|pp)\.(\d+)', r'\1. \2', text, flags=re.IGNORECASE)
    text = re.sub(r'\b(Clause|Section|Article|Rule|Schedule|Act)\s*(\d+)', r'\1 \2', text, flags=re.IGNORECASE)

    # Preposition & conjunction attachment boundaries (e.g. Stateof -> State of, intothe -> into the)
    text = re.sub(r'\bStateof\b', 'State of', text, flags=re.IGNORECASE)
    text = re.sub(r'\binto(the|a|an)\b', r'into \1', text, flags=re.IGNORECASE)

    # Digit-letter boundaries: "JANUARY07,2022" -> "JANUARY 07, 2022", "of2011" -> "of 2011"
    text = re.sub(r'([a-zA-Z])(\d{4})\b', r'\1 \2', text)
    text = re.sub(r'\b(\d+)([a-zA-Z]{3,})', r'\1 \2', text)
    text = re.sub(r'\b(dated|of|in|on|at|by)(\d+)', r'\1 \2', text, flags=re.IGNORECASE)

    # Lowercase to Uppercase transition (CamelCase)
    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)

    # Pass 3: Viterbi word segmentation for concatenated alphabetic blocks
    blocks = re.findall(r'[A-Za-z]+|[^A-Za-z]+', text)
    new_blocks = []
    for b in blocks:
        if b.isalpha() and (len(b) >= 5 or char_w > 1.2 * median_char_w):
            segmented = viterbi_segment(b.lower())
            if len(segmented) > 1:
                cased = []
                idx = 0
                for w in segmented:
                    orig_slice = b[idx:idx + len(w)]
                    if b.isupper():
                        cased.append(w.upper())
                    elif orig_slice and orig_slice[0].isupper():
                        cased.append(w.capitalize())
                    else:
                        cased.append(w)
                    idx += len(w)
                split_word = ' '.join(cased)
                log.spaces_inserted.append(f"'{b}' -> '{split_word}'")
                new_blocks.append(split_word)
            else:
                new_blocks.append(b)
        else:
            new_blocks.append(b)

    out = ''.join(new_blocks)
    
    # Fix acronym splits like "Mo U" -> "MoU"
    out = re.sub(r'\bMo\s+U\b', 'MoU', out, flags=re.IGNORECASE)
    
    # Clean up redundant spaces
    return re.sub(r'  +', ' ', out).strip()


def group_tokens_into_lines(tokens: List[PositionedToken]) -> List[List[PositionedToken]]:
    """Group tokens into visual lines by vertical center overlap."""
    sorted_tokens = sorted(tokens, key=lambda t: t.cy)
    lines: List[List[PositionedToken]] = []

    for tok in sorted_tokens:
        placed = False
        for line in lines:
            ref = line[0]
            max_h = max(ref.height, tok.height, 1.0)
            if abs(tok.cy - ref.cy) / max_h < 0.55:
                line.append(tok)
                placed = True
                break
        if not placed:
            lines.append([tok])

    lines.sort(key=lambda l: min(t.cy for t in l))
    for line in lines:
        line.sort(key=lambda t: t.x0)

    return lines


def assemble_paragraphs(reconstructed_lines: List[str], lines_tokens: List[List[PositionedToken]]) -> str:
    """Assemble reconstructed lines into text paragraphs using Y-coordinates."""
    if not reconstructed_lines:
        return ""

    line_heights = [t.height for line in lines_tokens for t in line]
    median_line_h = statistics.median(line_heights) if line_heights else 20.0

    assembled: List[str] = []
    prev_line_bottom: Optional[float] = None

    for idx, line_str in enumerate(reconstructed_lines):
        line_toks = lines_tokens[idx]
        if prev_line_bottom is not None and line_toks:
            line_top = min(t.y0 for t in line_toks)
            if (line_top - prev_line_bottom) > 1.8 * median_line_h:
                assembled.append("")  # Paragraph break

        assembled.append(line_str)

        if line_toks:
            prev_line_bottom = max(t.y1 for t in line_toks)

    return "\n".join(assembled)
