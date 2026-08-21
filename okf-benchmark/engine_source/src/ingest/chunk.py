"""
Chunked text extraction utilities for Indian Supreme Court judgments.

Extracts three structural chunks from each full judgment text:
  chunk_opening : first ~800 chars  (cause title, parties, procedural framing)
  chunk_body    : 25%–60% character range (~1500–2000 chars) — facts, arguments
  chunk_holding : last ~800 chars   (order / holding / disposition)

If the document is too short to produce three non-overlapping chunks,
the entire text is used as a single chunk and is_fallback=True is returned.

Minimum chars required for three-chunk split (configurable):
  chunk_opening_len + chunk_body_len + chunk_holding_len = 800+1800+800 = 3400 chars
"""

from typing import Tuple, Dict

# Default chunk sizes (can be overridden from config.yaml via caller)
OPENING_CHARS  = 800
BODY_CHARS     = 1800   # taken from ~25%-60% of full text
HOLDING_CHARS  = 800
MIN_THREE_CHUNK_LEN = OPENING_CHARS + BODY_CHARS + HOLDING_CHARS  # 3400


def extract_three_chunks(
    full_text: str,
    opening_chars: int = OPENING_CHARS,
    body_chars:    int = BODY_CHARS,
    holding_chars: int = HOLDING_CHARS,
) -> Dict[str, object]:
    """
    Split full_text into three structural chunks.

    Returns a dict:
      {
        "chunk_opening": str,
        "chunk_body":    str,
        "chunk_holding": str,
        "is_fallback":   bool,   # True if text too short for three distinct chunks
        "full_text_len": int,
      }

    Chunk positions:
      opening  = text[0 : opening_chars]
      body     = text[body_start : body_start + body_chars]
               where body_start = int(0.25 * len(text))
      holding  = text[-holding_chars :]

    Non-overlap guarantee: if body_start < opening_chars or
    body_start + body_chars > len(text) - holding_chars,
    we fall back to a single-chunk representation.
    """
    text = full_text.strip()
    n = len(text)
    min_len = opening_chars + body_chars + holding_chars

    if n < min_len:
        # Short document — use whole text for all three slots and flag it
        return {
            "chunk_opening": text,
            "chunk_body":    text,
            "chunk_holding": text,
            "is_fallback":   True,
            "full_text_len": n,
        }

    # Opening: strict head
    chunk_opening = text[:opening_chars]

    # Holding: strict tail
    chunk_holding = text[-holding_chars:]

    # Body: from the 25% mark, but must not overlap with opening or holding
    body_start = max(opening_chars, int(0.25 * n))
    body_end   = min(body_start + body_chars, n - holding_chars)

    if body_end <= body_start:
        # Degenerate: fall back
        return {
            "chunk_opening": text,
            "chunk_body":    text,
            "chunk_holding": text,
            "is_fallback":   True,
            "full_text_len": n,
        }

    chunk_body = text[body_start:body_end]

    return {
        "chunk_opening": chunk_opening,
        "chunk_body":    chunk_body,
        "chunk_holding": chunk_holding,
        "is_fallback":   False,
        "full_text_len": n,
    }
