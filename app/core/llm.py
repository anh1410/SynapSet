from functools import lru_cache

from google import genai

from app.core.config import get_settings


@lru_cache
def get_genai_client() -> genai.Client:
    settings = get_settings()
    return genai.Client(api_key=settings.google_api_key)


def embed_text(text: str) -> list[float]:
    settings = get_settings()
    client = get_genai_client()
    result = client.models.embed_content(model=settings.embedding_model, contents=text)
    return result.embeddings[0].values
