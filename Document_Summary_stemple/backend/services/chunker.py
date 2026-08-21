import re

def chunk_text(text: str, chunk_size: int = 6000, chunk_overlap: int = 500) -> list[dict]:
    """
    Chunks long text using paragraph and page boundaries while respecting overlap.

    Returns a list of dicts:
    [
      {
        "chunk_index": 1,
        "total_chunks": N,
        "text": "...chunk text...",
        "page_start": 1,
        "page_end": 5
      },
      ...
    ]
    """
    if not text:
        return []

    # If text fits within single chunk
    if len(text) <= chunk_size:
        pages_in_chunk = [int(p) for p in re.findall(r'\[Page\s+(\d+)\]', text)]
        p_start = min(pages_in_chunk) if pages_in_chunk else 1
        p_end = max(pages_in_chunk) if pages_in_chunk else 1
        return [{
            "chunk_index": 1,
            "total_chunks": 1,
            "text": text,
            "page_start": p_start,
            "page_end": p_end
        }]

    # Split text into paragraphs/sections
    paragraphs = text.split('\n\n')
    raw_chunks = []
    current_paragraphs = []
    current_length = 0

    for p in paragraphs:
        p_len = len(p) + 2
        if current_length + p_len > chunk_size and current_paragraphs:
            # Form chunk
            chunk_str = '\n\n'.join(current_paragraphs)
            raw_chunks.append(chunk_str)

            # Calculate overlap paragraphs
            overlap_length = 0
            overlap_paragraphs = []
            for prev_p in reversed(current_paragraphs):
                if overlap_length + len(prev_p) + 2 <= chunk_overlap:
                    overlap_paragraphs.insert(0, prev_p)
                    overlap_length += len(prev_p) + 2
                else:
                    break

            current_paragraphs = overlap_paragraphs
            current_length = sum(len(x) + 2 for x in current_paragraphs)

        current_paragraphs.append(p)
        current_length += p_len

    if current_paragraphs:
        raw_chunks.append('\n\n'.join(current_paragraphs))

    total = len(raw_chunks)
    result = []

    last_known_page = 1
    for idx, c_text in enumerate(raw_chunks, start=1):
        pages = [int(p) for p in re.findall(r'\[Page\s+(\d+)\]', c_text)]
        if pages:
            p_start = min(pages)
            p_end = max(pages)
            last_known_page = p_end
        else:
            p_start = last_known_page
            p_end = last_known_page

        result.append({
            "chunk_index": idx,
            "total_chunks": total,
            "text": c_text,
            "page_start": p_start,
            "page_end": p_end
        })

    return result
