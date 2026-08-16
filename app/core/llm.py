from functools import lru_cache

import httpx
from google import genai
from google.genai import errors
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import get_settings


@lru_cache
def get_genai_client() -> genai.Client:
    settings = get_settings()
    return genai.Client(api_key=settings.google_api_key)


@retry(
    retry=retry_if_exception_type((errors.ServerError, errors.APIError, httpx.TransportError)),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    reraise=True,
)
def embed_text(text: str) -> list[float]:
    settings = get_settings()
    client = get_genai_client()
    result = client.models.embed_content(model=settings.embedding_model, contents=text)
    return result.embeddings[0].values
