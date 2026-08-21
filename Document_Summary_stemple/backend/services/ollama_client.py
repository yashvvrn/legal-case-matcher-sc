import time
import httpx
from backend.config import OLLAMA_URL, MODEL_NAME

class OllamaError(Exception):
    """Custom exception for Ollama API issues."""
    pass

class OllamaClient:
    def __init__(self, url: str = OLLAMA_URL, model_name: str = MODEL_NAME):
        self.url = url.rstrip("/")
        self.default_model_name = model_name

    async def check_health(self, requested_model: str = None) -> dict:
        """
        Checks if Ollama is running and checks model availability.
        """
        target_model = requested_model or self.default_model_name
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(f"{self.url}/api/tags")
                if res.status_code != 200:
                    raise OllamaError(f"Ollama server returned HTTP {res.status_code}")
                data = res.json()
        except httpx.ConnectError:
            raise OllamaError(
                f"Ollama is not running at {self.url}. Please start Ollama using 'ollama serve'."
            )
        except Exception as e:
            raise OllamaError(f"Failed to connect to Ollama at {self.url}: {str(e)}")

        models = data.get("models", [])
        model_names = [m.get("name") for m in models if isinstance(m, dict)]
        
        match_found = any(
            target_model in name or name in target_model
            for name in model_names
        )

        if not match_found:
            available_str = ", ".join(model_names) if model_names else "none"
            raise OllamaError(
                f"Model '{target_model}' was not found in Ollama. "
                f"Available models: [{available_str}]. "
                f"Please run 'ollama pull {target_model}'."
            )

        return {
            "status": "ok",
            "url": self.url,
            "model_name": target_model,
            "available_models": model_names
        }

    async def generate(
        self, 
        prompt: str, 
        system_prompt: str = "", 
        max_tokens: int = None,
        model_name: str = None
    ) -> dict:
        """
        Calls Ollama generate endpoint and returns response text & metrics.
        """
        active_model = model_name or self.default_model_name

        options = {
            "temperature": 0.0,   # Deterministic decoding for fast legal extraction
            "top_p": 0.9,
            "num_ctx": 16384,     # Expanded context window for single-pass 20-page reading
        }
        if max_tokens:
            options["num_predict"] = max_tokens

        payload = {
            "model": active_model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": "30m",  # Keep model warm in GPU VRAM
            "options": options
        }
        if system_prompt:
            payload["system"] = system_prompt

        start_time = time.time()
        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                res = await client.post(f"{self.url}/api/generate", json=payload)
                if res.status_code != 200:
                    raise OllamaError(f"Ollama generate failed with HTTP {res.status_code}: {res.text}")
                data = res.json()
        except httpx.ConnectError:
            raise OllamaError(f"Connection lost to Ollama at {self.url}.")
        except Exception as e:
            raise OllamaError(f"Ollama generation request failed: {str(e)}")

        wall_time = time.time() - start_time
        response_text = data.get("response", "").strip()

        # Token & performance metrics from Ollama
        prompt_eval_count = data.get("prompt_eval_count", 0)  # input tokens
        eval_count = data.get("eval_count", 0)                # output tokens
        eval_duration_ns = data.get("eval_duration", 0)        # ns

        eval_duration_sec = eval_duration_ns / 1e9 if eval_duration_ns > 0 else wall_time
        tokens_per_sec = round(eval_count / eval_duration_sec, 2) if eval_duration_sec > 0 else 0.0

        return {
            "text": response_text,
            "metrics": {
                "model_name": active_model,
                "wall_time_sec": round(wall_time, 2),
                "input_tokens": prompt_eval_count,
                "output_tokens": eval_count,
                "eval_duration_sec": round(eval_duration_sec, 2),
                "tokens_per_sec": tokens_per_sec
            }
        }
