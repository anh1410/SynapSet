"""Gemini-backed judge model for DeepEval, so evals reuse the app's GOOGLE_API_KEY.

The judge defaults to a stronger model than the generator (gemini-flash-lite-latest), because a model
grading its own output is a known source of lenient, noisy scores. Override with EVAL_JUDGE_MODEL
(model availability depends on your API key).
"""

import os

os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")
# DeepEval caps one whole test case (all metrics, all judge calls) at 180s by default.
os.environ.setdefault("DEEPEVAL_PER_ATTEMPT_TIMEOUT_SECONDS_OVERRIDE", "600")

import httpx
from deepeval.models import DeepEvalBaseLLM
from google.genai import errors, types
from pydantic import BaseModel
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from app.core.llm import get_genai_client

DEFAULT_JUDGE_MODEL = "gemini-3.5-flash"
CALL_TIMEOUT_MS = 60_000


def _is_retryable(exc: BaseException) -> bool:
    """Retry transient failures, but not a daily quota 429: it will not clear for hours, so waiting is pointless."""
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, errors.APIError):
        return not (exc.code == 429 and "PerDay" in str(exc))
    return False


class GeminiJudge(DeepEvalBaseLLM):
    def __init__(self, model_name: str | None = None):
        self.model_name = model_name or os.environ.get("EVAL_JUDGE_MODEL", DEFAULT_JUDGE_MODEL)
        super().__init__(self.model_name)

    def load_model(self):
        return get_genai_client()

    @retry(
        retry=retry_if_exception(_is_retryable),
        stop=stop_after_attempt(6),
        wait=wait_exponential(multiplier=2, min=2, max=60),
        reraise=True,
    )
    def _call(self, prompt: str, json_mode: bool) -> str:
        config = types.GenerateContentConfig(
            temperature=0.0,
            response_mime_type="application/json" if json_mode else None,
            http_options=types.HttpOptions(timeout=CALL_TIMEOUT_MS),
        )
        response = self.model.models.generate_content(model=self.model_name, contents=prompt, config=config)
        return response.text or ""

    def generate(self, prompt: str, schema: type[BaseModel] | None = None):
        if schema is None:
            return self._call(prompt, json_mode=False)
        text = self._call(prompt, json_mode=True)
        try:
            return schema.model_validate_json(text)
        except ValueError:
            return text  # DeepEval's own JSON extraction handles stray fences/prose

    async def a_generate(self, prompt: str, schema: type[BaseModel] | None = None):
        return self.generate(prompt, schema)

    def get_model_name(self) -> str:
        return self.model_name

    def preflight(self) -> None:
        """Fail fast, with one clear error, if the judge model cannot be reached at all."""
        self._call("Reply with the single word: ok", json_mode=False)
