"""
Nightingale Gemini Client
Single-key API client using official google-genai SDK
With caching, structured output, and graceful rate limit handling

SDK: google-genai
Model: models/gemini-3-flash-preview
"""
import os
import time
import json
import hashlib
from typing import Optional, Dict, Any, Type, TypeVar
from datetime import datetime
from pathlib import Path
from pydantic import BaseModel
from google import genai
from google.genai import types

from nightingale.config import config
from nightingale.core.logger import logger

T = TypeVar('T', bound=BaseModel)

# ── SDK info ────────────────────────────────────────────────────────

SDK_PACKAGE = "google-genai"
SDK_VERSION = getattr(genai, "__version__", "unknown")


class GeminiClientError(Exception):
    """Base exception for Gemini client errors."""
    pass


class QuotaExhaustedError(GeminiClientError):
    """All retries exhausted due to rate limits."""
    pass


class SchemaValidationError(GeminiClientError):
    """Response validation failed."""
    pass


class ResponseCache:
    """
    Persistent cache for Gemini API responses.
    Keyed by SHA-256 prompt hash.
    Only stores real API responses — never synthetic data.
    """

    def __init__(self, cache_dir: str = ".nightingale_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.enabled = True

    def _key(self, prompt: str) -> str:
        return hashlib.sha256(prompt.encode()).hexdigest()

    def get(self, prompt: str) -> Optional[str]:
        if not self.enabled:
            return None
        path = self.cache_dir / f"{self._key(prompt)}.json"
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            logger.info("[CACHE HIT] Using cached Gemini response", component="gemini")
            return data["response"]
        return None

    def put(self, prompt: str, response_text: str):
        if not self.enabled:
            return
        path = self.cache_dir / f"{self._key(prompt)}.json"
        path.write_text(json.dumps({
            "prompt_hash": self._key(prompt),
            "response": response_text,
            "cached_at": datetime.now().isoformat()
        }, indent=2), encoding="utf-8")


class GeminiClient:
    """
    Production Gemini API client using official google-genai SDK.

    - Single API key: GEMINI_API_KEY
    - Model: models/gemini-3-flash-preview
    - Response caching (real responses only)
    - Record mode (replay cached responses, no API calls)
    - Exponential backoff on rate limits
    - Graceful escalation when quota is exhausted
    - JSON schema enforcement via prompt + Pydantic validation
    """

    MAX_RETRIES = 3
    INITIAL_DELAY = 2.0
    MAX_DELAY = 30.0
    BACKOFF_FACTOR = 2.0

    def __init__(self, record_mode: bool = False):
        self.record_mode = record_mode
        self.cache = ResponseCache()

        # Single API key
        self.api_key = os.getenv("GEMINI_API_KEY", "")

        if not self.api_key and not self.record_mode:
            raise GeminiClientError(
                "ERROR: GEMINI_API_KEY not set.\n"
                "Set it using:\n"
                "  PowerShell:   $env:GEMINI_API_KEY = 'your_key_here'\n"
                "  Linux/macOS:  export GEMINI_API_KEY='your_key_here'"
            )

        self.client = None
        self.model_name = config.get("agents.marathon.model", "models/gemini-3-flash-preview")

        if self.api_key:
            self._configure()

        # Rate limit tracking
        self.requests_this_minute = 0
        self.minute_start = time.time()

        # Metrics
        self.total_tokens = 0
        self.total_calls = 0

    def _configure(self):
        """Create genai.Client with the API key."""
        self.client = genai.Client(api_key=self.api_key)
        masked = self.api_key[:8] + "..." + self.api_key[-4:]
        logger.info(f"Gemini client initialized", component="gemini")
        logger.info(f"  SDK:   {SDK_PACKAGE} v{SDK_VERSION}", component="gemini")
        logger.info(f"  Model: {self.model_name}", component="gemini")
        logger.info(f"  Key:   {masked}", component="gemini")

    # ── Rate limiting ───────────────────────────────────────────────

    def _check_rate_limit(self):
        current_time = time.time()
        if current_time - self.minute_start >= 60:
            self.requests_this_minute = 0
            self.minute_start = current_time

        max_rpm = config.get("gemini.rate_limit", 15)
        if self.requests_this_minute >= max_rpm:
            sleep_time = 60 - (current_time - self.minute_start) + 1
            logger.warning(
                f"Rate limit approaching ({self.requests_this_minute}/{max_rpm} RPM), "
                f"sleeping {sleep_time:.1f}s"
            )
            time.sleep(sleep_time)
            self.requests_this_minute = 0
            self.minute_start = time.time()

    # ── Retry with backoff ──────────────────────────────────────────

    def _retry_with_backoff(self, func, *args, **kwargs):
        """Execute function with exponential backoff. Raises QuotaExhaustedError if all retries fail."""
        delay = self.INITIAL_DELAY
        last_error = None

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                self._check_rate_limit()
                self.requests_this_minute += 1
                return func(*args, **kwargs)
            except Exception as e:
                last_error = e
                error_str = str(e).lower()

                is_quota = any(k in error_str for k in [
                    "429", "rate", "quota", "resource_exhausted"
                ])
                is_transient = any(k in error_str for k in [
                    "500", "503", "timeout", "unavailable"
                ])

                if is_quota or is_transient:
                    if attempt < self.MAX_RETRIES:
                        logger.warning(
                            f"{'Rate limited' if is_quota else 'Transient error'}, "
                            f"retrying in {delay:.0f}s (attempt {attempt}/{self.MAX_RETRIES})"
                        )
                        time.sleep(delay)
                        delay = min(delay * self.BACKOFF_FACTOR, self.MAX_DELAY)
                        continue
                    else:
                        raise QuotaExhaustedError(
                            f"API quota exhausted after {self.MAX_RETRIES} retries. "
                            f"Last error: {e}"
                        )

                # Non-retryable error — raise immediately
                raise

        raise QuotaExhaustedError(f"Max retries exceeded: {last_error}")

    # ── Core generation ─────────────────────────────────────────────

    def generate(
        self,
        prompt: str,
        model: str = "",
        incident_id: str = "",
    ) -> str:
        """Generate raw text from Gemini, with cache support."""

        # Cache check
        cached = self.cache.get(prompt)
        if cached is not None:
            self.total_calls += 1
            return cached

        if self.record_mode:
            raise GeminiClientError(
                "Record mode ON but no cached response for this prompt. "
                "Run once without --record-mode to populate the cache."
            )

        use_model = model if model else self.model_name
        start_time = time.time()

        def _call():
            return self.client.models.generate_content(
                model=use_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.2,
                    top_p=0.95,
                    max_output_tokens=8192,
                ),
            )

        response = self._retry_with_backoff(_call)
        duration_ms = int((time.time() - start_time) * 1000)

        tokens = 0
        if hasattr(response, 'usage_metadata') and response.usage_metadata:
            tokens = getattr(response.usage_metadata, 'total_token_count', 0) or 0

        self.total_tokens += tokens
        self.total_calls += 1

        logger.api_call(incident_id, use_model, tokens, duration_ms)

        text = response.text
        self.cache.put(prompt, text)
        return text

    def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        model: str = "",
        incident_id: str = "",
        max_validation_retries: int = 3
    ) -> T:
        """Generate and validate structured JSON response against a Pydantic model."""

        json_schema = response_model.model_json_schema()

        # Build a concrete example to guide the model
        schema_instruction = f"""
CRITICAL: Respond with ONLY valid JSON. No markdown, no code fences, no explanation.

Required JSON schema:
{json.dumps(json_schema, indent=2)}

IMPORTANT for files_to_change: Each entry MUST use these EXACT field names:
- "file_path": string (path to the file)
- "change_type": string (one of: "modify", "add", "delete")
- "content": string (the new file content or patch)

Example format:
{{
  "root_cause": "...",
  "rationale": "...",
  "files_to_change": [
    {{"file_path": "path/to/file.py", "change_type": "modify", "content": "full corrected file content"}}
  ],
  "verification_commands": ["python -m pytest -v"],
  "confidence": 0.8,
  "risk_assessment": "low"
}}"""

        structured_prompt = f"{prompt}\n\n{schema_instruction}"
        original_prompt = structured_prompt

        for attempt in range(max_validation_retries):
            raw_response = self.generate(structured_prompt, model, incident_id)

            # Clean response
            cleaned = raw_response.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

            # Parse JSON
            try:
                data = json.loads(cleaned)
            except json.JSONDecodeError as e:
                logger.warning(f"JSON parse error (attempt {attempt + 1}): {e}")
                if attempt < max_validation_retries - 1:
                    self.cache.enabled = False
                    structured_prompt = (
                        f"Your previous response was not valid JSON. Error: {e}\n\n"
                        f"You MUST output ONLY raw valid JSON matching this schema.\n"
                        f"{schema_instruction}"
                    )
                    self.cache.enabled = True
                    continue
                raise SchemaValidationError(
                    f"JSON parsing failed after {max_validation_retries} attempts: {e}"
                )

            # Validate with Pydantic
            try:
                return response_model.model_validate(data)
            except Exception as e:
                logger.warning(f"Pydantic validation error (attempt {attempt + 1}): {e}")
                if attempt < max_validation_retries - 1:
                    self.cache.enabled = False
                    structured_prompt = (
                        f"Your JSON was valid but fields were wrong. Error: {e}\n\n"
                        f"Fix the fields and output ONLY valid JSON.\n"
                        f"{schema_instruction}"
                    )
                    self.cache.enabled = True
                    continue
                raise SchemaValidationError(
                    f"Schema validation failed after {max_validation_retries} attempts: {e}"
                )

        raise SchemaValidationError("Max validation retries exceeded")

    def get_metrics(self) -> Dict[str, Any]:
        return {
            "total_calls": self.total_calls,
            "total_tokens": self.total_tokens,
            "requests_this_minute": self.requests_this_minute,
        }


# ── Global client ───────────────────────────────────────────────────

_client: Optional[GeminiClient] = None


def get_gemini_client(record_mode: bool = False) -> GeminiClient:
    """Get or create global Gemini client."""
    global _client
    if _client is None:
        _client = GeminiClient(record_mode=record_mode)
    return _client


def reset_gemini_client():
    """Reset global client (for testing or re-init)."""
    global _client
    _client = None


def verify_api_key() -> Dict[str, Any]:
    """
    Minimal API key verification.
    Makes ONE tiny request: "Respond with the word OK."
    Returns dict with reachable, model, latency_ms, tokens.
    """
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        return {
            "reachable": False,
            "error": "GEMINI_API_KEY not set",
        }

    model_name = config.get("agents.marathon.model", "models/gemini-3-flash-preview")
    client = genai.Client(api_key=api_key)

    start = time.time()
    try:
        response = client.models.generate_content(
            model=model_name,
            contents="Respond with the word OK.",
        )
        latency_ms = int((time.time() - start) * 1000)

        tokens = 0
        if hasattr(response, 'usage_metadata') and response.usage_metadata:
            tokens = getattr(response.usage_metadata, 'total_token_count', 0) or 0

        return {
            "reachable": True,
            "model": model_name,
            "sdk": f"{SDK_PACKAGE} v{SDK_VERSION}",
            "latency_ms": latency_ms,
            "tokens": tokens,
            "response": response.text.strip(),
        }
    except Exception as e:
        latency_ms = int((time.time() - start) * 1000)
        error_str = str(e).lower()
        is_quota = any(k in error_str for k in ["429", "quota", "rate", "resource_exhausted"])

        return {
            "reachable": False,
            "quota_exhausted": is_quota,
            "error": str(e),
            "latency_ms": latency_ms,
            "model": model_name,
            "sdk": f"{SDK_PACKAGE} v{SDK_VERSION}",
        }
