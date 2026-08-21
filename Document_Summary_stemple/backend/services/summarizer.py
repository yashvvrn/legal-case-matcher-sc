import time
import asyncio
import logging
from typing import AsyncGenerator
from backend.services.ollama_client import OllamaClient
from backend.services.chunker import chunk_text
from backend.config import CHUNK_SIZE, CHUNK_OVERLAP, MODEL_NAME

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a strict, highly accurate legal assistant specialized in legal judgement summarization.
Your sole source of truth is the supplied legal judgement text.
CRITICAL INSTRUCTIONS:
1. ONLY use information explicitly stated in the supplied document.
2. DO NOT invent, assume, or infer facts, citations, court names, judges, arguments, legal provisions, precedent cases, or holdings unsupported by the text.
3. If specific information for any requested section is not mentioned in the document, write: "Not stated in the document."
4. Include source page references in brackets where practical (e.g., [Pages 3–5] or [Page 12]).
5. Maintain objective, formal, and precise legal terminology."""

CHUNK_SUMMARY_PROMPT_TEMPLATE = """Summarize Section (Chunk {chunk_index} of {total_chunks}) covering [Pages {page_start}–{page_end}].

Document Text Section:
---
{chunk_text}
---

Provide a CONCISE summary (max 300 words) listing only key facts, procedural background, legal issues, petitioner/respondent arguments, court reasoning, rulings, and precedents cited in this section. Maintain page tags [Page X]."""

FINAL_STRUCTURED_SUMMARY_PROMPT_TEMPLATE = """You are provided with key extracted notes from a complete legal judgement document.
Generate a comprehensive, structured legal summary adhering EXACTLY to the following format and headings.

Document Notes:
---
{extracted_notes}
---

REQUIRED STRUCTURED SUMMARY FORMAT:

### Case Information
- **Case Name:** [State exact case name, or "Not stated in the document."]
- **Court:** [State exact court, or "Not stated in the document."]
- **Date:** [State decision date, or "Not stated in the document."]
- **Case Number / Citation:** [State citation/case number, or "Not stated in the document."]
- **Judges / Bench:** [State judges/bench members, or "Not stated in the document."]

### 1. Facts
[Summarize relevant factual background with page references e.g. [Pages 2–4]. If absent, write "Not stated in the document."]

### 2. Procedural History
[Explain procedural history if available, with page references. If absent, write "Not stated in the document."]

### 3. Issues
[List exact legal questions/issues before the court.]

### 4. Arguments
**Petitioner/Appellant:**
[Summarize petitioner's arguments.]

**Respondent:**
[Summarize respondent's arguments.]

### 5. Court's Reasoning
[Explain the court's rationale and legal reasoning leading to its conclusion.]

### 6. Decision / Holding
[State the exact ruling or holding of the court.]

### 7. Final Outcome
[State the actual outcome of the case (e.g. appeal allowed/dismissed, judgment set aside, petition granted).]

### 8. Legal Principles
[List key legal principles, doctrines, tests, or rules applied or established.]

### 9. Important Precedents
[List important cases relied upon by the court, if identifiable from the document.]

### 10. Key Takeaways
[Provide 5–10 concise bullet points highlighting the main takeaways of this judgement.]
"""

class LegalSummarizer:
    def __init__(self, ollama_client: OllamaClient = None):
        self.client = ollama_client or OllamaClient()

    async def summarize_stream(
        self,
        full_text: str,
        page_count: int,
        char_count: int,
        chunk_size: int = CHUNK_SIZE,
        chunk_overlap: int = CHUNK_OVERLAP,
        model_name: str = None
    ) -> AsyncGenerator[dict, None]:
        """
        Processes document with optimized single-pass or parallel chunking.
        """
        start_time = time.time()
        active_model = model_name or MODEL_NAME

        # 1. Health check Ollama & selected model
        yield {"step": "health_check", "message": f"Checking Ollama for model '{active_model}'..."}
        await self.client.check_health(requested_model=active_model)
        yield {"step": "health_ok", "message": f"✓ Ollama & {active_model} verified"}

        # 2. Chunking with large chunk size (default 35,000 chars)
        yield {"step": "chunking", "message": "Preparing document..."}
        chunks = chunk_text(full_text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        total_chunks = len(chunks)
        yield {"step": "chunking_complete", "message": f"✓ Document prepared into {total_chunks} chunk(s)"}

        accumulated_input_tokens = 0
        accumulated_output_tokens = 0

        if total_chunks == 1:
            # Single pass summarization - Ultra Fast!
            chunk = chunks[0]
            yield {
                "step": "summarizing_chunk",
                "current_chunk": 1,
                "total_chunks": 1,
                "message": f"Summarizing document in ultra-fast single pass using {active_model}..."
            }
            
            prompt = FINAL_STRUCTURED_SUMMARY_PROMPT_TEMPLATE.format(extracted_notes=chunk["text"])
            res = await self.client.generate(
                prompt=prompt, 
                system_prompt=SYSTEM_PROMPT, 
                max_tokens=1500,
                model_name=active_model
            )
            
            final_summary_text = res["text"]
            accumulated_input_tokens += res["metrics"]["input_tokens"]
            accumulated_output_tokens += res["metrics"]["output_tokens"]

        else:
            # Multi-pass parallel chunk processing
            yield {
                "step": "summarizing_chunk",
                "current_chunk": 1,
                "total_chunks": total_chunks,
                "message": f"Processing {total_chunks} chunks concurrently with {active_model}..."
            }

            async def process_single_chunk(chunk):
                prompt = CHUNK_SUMMARY_PROMPT_TEMPLATE.format(
                    chunk_index=chunk["chunk_index"],
                    total_chunks=total_chunks,
                    page_start=chunk["page_start"],
                    page_end=chunk["page_end"],
                    chunk_text=chunk["text"]
                )
                return await self.client.generate(
                    prompt=prompt, 
                    system_prompt=SYSTEM_PROMPT,
                    max_tokens=400,
                    model_name=active_model
                )

            chunk_results = await asyncio.gather(*[process_single_chunk(c) for c in chunks])

            intermediate_summaries = []
            for idx, res in enumerate(chunk_results, start=1):
                chunk_info = chunks[idx - 1]
                intermediate_summaries.append(
                    f"--- Chunk {idx} (Pages {chunk_info['page_start']}-{chunk_info['page_end']}) ---\n{res['text']}"
                )
                accumulated_input_tokens += res["metrics"]["input_tokens"]
                accumulated_output_tokens += res["metrics"]["output_tokens"]

            # Final synthesis pass
            yield {"step": "synthesizing", "message": f"Synthesizing final structured summary with {active_model}..."}
            combined_notes = "\n\n".join(intermediate_summaries)
            final_prompt = FINAL_STRUCTURED_SUMMARY_PROMPT_TEMPLATE.format(extracted_notes=combined_notes)
            
            res_final = await self.client.generate(
                prompt=final_prompt, 
                system_prompt=SYSTEM_PROMPT,
                max_tokens=1500,
                model_name=active_model
            )
            final_summary_text = res_final["text"]
            
            accumulated_input_tokens += res_final["metrics"]["input_tokens"]
            accumulated_output_tokens += res_final["metrics"]["output_tokens"]

        total_processing_time = round(time.time() - start_time, 2)
        
        overall_tokens_per_sec = (
            round(accumulated_output_tokens / total_processing_time, 2)
            if total_processing_time > 0 else 0.0
        )

        minutes = int(total_processing_time // 60)
        seconds = int(total_processing_time % 60)
        time_str = f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s"

        benchmark_stats = {
            "model_name": active_model,
            "pages": page_count,
            "extracted_characters": char_count,
            "chunks": total_chunks,
            "processing_time_sec": total_processing_time,
            "processing_time_formatted": time_str,
            "input_tokens": accumulated_input_tokens,
            "output_tokens": accumulated_output_tokens,
            "tokens_per_second": overall_tokens_per_sec
        }

        yield {
            "step": "complete",
            "message": "✓ Summarization completed successfully!",
            "summary": final_summary_text,
            "benchmark": benchmark_stats
        }
