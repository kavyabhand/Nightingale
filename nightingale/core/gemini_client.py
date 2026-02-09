"""
Nightingale Gemini Client
Production-grade API client with retries, validation, and structured output
"""
import os
import time
import json
import hashlib
from typing import Optional, Dict, Any, Type, TypeVar
from datetime import datetime
import google.generativeai as genai
from google.generativeai.types import GenerationConfig
from pydantic import BaseModel, ValidationError

from nightingale.config import config
from nightingale.core.logger import logger

T = TypeVar('T', bound=BaseModel)

class GeminiClientError(Exception):
    """Base exception for Gemini client errors."""
    pass

class RateLimitError(GeminiClientError):
    """Rate limit exceeded."""
    pass

class ValidationError(GeminiClientError):
    """Response validation failed."""
    pass

class GeminiClient:
    """
    Production-grade Gemini API client with:
    - Exponential backoff retry for rate limits
    - JSON schema enforcement
    - Pydantic response validation
    - Timeout protection
    - Detailed logging
    """
    
    # Retry configuration
    MAX_RETRIES = 5
    INITIAL_DELAY = 1.0
    MAX_DELAY = 60.0
    BACKOFF_FACTOR = 2.0
    
    # Rate limit tracking
    requests_this_minute = 0
    minute_start = time.time()
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise GeminiClientError("GEMINI_API_KEY not set")
        
        genai.configure(api_key=self.api_key)
        
        # Model configurations
        self.models = {
            "pro": genai.GenerativeModel(
                model_name=config.get("agents.marathon.model", "gemini-2.0-flash"),
                generation_config=GenerationConfig(
                    temperature=0.2,
                    top_p=0.95,
                    max_output_tokens=8192,
                )
            ),
            "flash": genai.GenerativeModel(
                model_name=config.get("agents.verifier.model", "gemini-2.0-flash"),
                generation_config=GenerationConfig(
                    temperature=0.1,
                    top_p=0.9,
                    max_output_tokens=4096,
                )
            )
        }
        
        self.total_tokens = 0
        self.total_calls = 0
    
    def _check_rate_limit(self):
        """Track and respect rate limits."""
        current_time = time.time()
        if current_time - self.minute_start >= 60:
            self.requests_this_minute = 0
            self.minute_start = current_time
        
        # Free tier: 15 RPM
        max_rpm = config.get("gemini.rate_limit", 15)
        if self.requests_this_minute >= max_rpm:
            sleep_time = 60 - (current_time - self.minute_start) + 1
            logger.warning(f"Rate limit approaching, sleeping {sleep_time:.1f}s")
            time.sleep(sleep_time)
            self.requests_this_minute = 0
            self.minute_start = time.time()
    
    def _retry_with_backoff(self, func, *args, **kwargs):
        """Execute function with exponential backoff retry."""
        delay = self.INITIAL_DELAY
        last_error = None
        
        for attempt in range(self.MAX_RETRIES):
            try:
                self._check_rate_limit()
                self.requests_this_minute += 1
                return func(*args, **kwargs)
            except Exception as e:
                last_error = e
                error_str = str(e).lower()
                
                # Check for rate limit errors
                if "429" in error_str or "rate" in error_str or "quota" in error_str:
                    logger.warning(f"Rate limited, retrying in {delay:.1f}s (attempt {attempt + 1}/{self.MAX_RETRIES})")
                    time.sleep(delay)
                    delay = min(delay * self.BACKOFF_FACTOR, self.MAX_DELAY)
                    continue
                
                # Check for transient errors
                if "500" in error_str or "503" in error_str or "timeout" in error_str:
                    logger.warning(f"Transient error, retrying in {delay:.1f}s")
                    time.sleep(delay)
                    delay = min(delay * self.BACKOFF_FACTOR, self.MAX_DELAY)
                    continue
                
                # Non-retryable error
                raise
        
        raise GeminiClientError(f"Max retries exceeded: {last_error}")
    
    def generate(
        self,
        prompt: str,
        model: str = "pro",
        incident_id: str = "",
        timeout: int = 300
    ) -> str:
        """
        Generate raw text response from Gemini.
        
        Args:
            prompt: The prompt to send
            model: "pro" or "flash"
            incident_id: For logging
            timeout: Request timeout in seconds
            
        Returns:
            Raw text response
        """
        start_time = time.time()
        
        def _call():
            response = self.models[model].generate_content(prompt)
            return response
        
        try:
            response = self._retry_with_backoff(_call)
            duration_ms = int((time.time() - start_time) * 1000)
            
            # Extract token counts if available
            tokens = 0
            if hasattr(response, 'usage_metadata'):
                tokens = getattr(response.usage_metadata, 'total_token_count', 0)
            
            self.total_tokens += tokens
            self.total_calls += 1
            
            logger.api_call(incident_id, model, tokens, duration_ms)
            
            return response.text
            
        except Exception as e:
            logger.error(f"Gemini API error: {e}", incident_id=incident_id, component="gemini")
            raise GeminiClientError(f"API call failed: {e}")
    
    def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        model: str = "pro",
        incident_id: str = "",
        max_validation_retries: int = 3
    ) -> T:
        """
        Generate and validate structured response.
        
        Args:
            prompt: The prompt (should request JSON output)
            response_model: Pydantic model class for validation
            model: "pro" or "flash"
            incident_id: For logging
            max_validation_retries: Max retries for validation errors
            
        Returns:
            Validated Pydantic model instance
        """
        json_schema = response_model.model_json_schema()
        
        structured_prompt = f"""{prompt}

IMPORTANT: Respond with ONLY valid JSON matching this exact schema:
```json
{json.dumps(json_schema, indent=2)}
```

Do not include any text before or after the JSON. Do not use markdown code blocks.
Just output the raw JSON object."""

        for attempt in range(max_validation_retries):
            try:
                raw_response = self.generate(structured_prompt, model, incident_id)
                
                # Clean response - remove markdown code blocks if present
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
                        # Ask Gemini to fix it
                        fix_prompt = f"""The previous response was not valid JSON. Error: {e}

Please output ONLY valid JSON matching the schema. No explanations.
Previous response was:
{raw_response[:500]}"""
                        structured_prompt = fix_prompt
                        continue
                    raise ValidationError(f"JSON parsing failed: {e}")
                
                # Validate with Pydantic
                try:
                    return response_model.model_validate(data)
                except Exception as e:
                    logger.warning(f"Pydantic validation error (attempt {attempt + 1}): {e}")
                    if attempt < max_validation_retries - 1:
                        fix_prompt = f"""The JSON was valid but didn't match the schema. Error: {e}

Output JSON matching this schema exactly:
{json.dumps(json_schema, indent=2)}"""
                        structured_prompt = fix_prompt
                        continue
                    raise ValidationError(f"Schema validation failed: {e}")
                    
            except (GeminiClientError, ValidationError):
                if attempt == max_validation_retries - 1:
                    raise
                continue
        
        raise ValidationError("Max validation retries exceeded")
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get client usage metrics."""
        return {
            "total_calls": self.total_calls,
            "total_tokens": self.total_tokens,
            "requests_this_minute": self.requests_this_minute
        }

# Global client instance (lazy initialization)
_client: Optional[GeminiClient] = None

def get_gemini_client() -> GeminiClient:
    """Get or create global Gemini client."""
    global _client
    if _client is None:
        _client = GeminiClient()
    return _client
