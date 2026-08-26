from __future__ import annotations

import os
from typing import Any

from gemini_rag_cycle_prototype.schemas import PredictionResponse


class MissingApiKeyError(RuntimeError):
    pass


class GeminiClient:
    def __init__(
        self, *, api_key: str | None = None, model: str | None = None,
        embedding_model: str | None = None,
        embedding_dimensions: int | None = None,
    ):
        key = api_key or os.getenv("GEMINI_API_KEY")
        if not key:
            raise MissingApiKeyError(
                "GEMINI_API_KEY is not set; place a rotated key in the environment"
            )
        try:
            from google import genai
        except ImportError as exc:
            raise RuntimeError(
                "google-genai is not installed; install requirements.txt"
            ) from exc
        self._types: Any
        from google.genai import types
        self._types = types
        self._client = genai.Client(api_key=key)
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-flash-latest")
        self.embedding_model = embedding_model or os.getenv(
            "GEMINI_EMBEDDING_MODEL", "gemini-embedding-2"
        )
        self.embedding_dimensions = embedding_dimensions or int(
            os.getenv("GEMINI_EMBEDDING_DIMENSIONS", "768")
        )

    def _embed(self, texts: list[str], task_type: str) -> list[list[float]]:
        response = self._client.models.embed_content(
            model=self.embedding_model,
            contents=texts,
            config=self._types.EmbedContentConfig(
                task_type=task_type,
                output_dimensionality=self.embedding_dimensions,
            ),
        )
        embeddings = getattr(response, "embeddings", None) or []
        return [list(item.values) for item in embeddings]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts, "RETRIEVAL_DOCUMENT")

    def embed_query(self, text: str) -> list[float]:
        values = self._embed([text], "RETRIEVAL_QUERY")
        if not values:
            raise RuntimeError("Gemini returned no query embedding")
        return values[0]

    def predict(self, prompt: str) -> tuple[PredictionResponse, str]:
        response = self._client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=self._types.GenerateContentConfig(
                temperature=0.1,
                response_mime_type="application/json",
                response_schema=PredictionResponse,
            ),
        )
        raw = response.text or ""
        parsed = getattr(response, "parsed", None)
        prediction = (
            parsed
            if isinstance(parsed, PredictionResponse)
            else PredictionResponse.model_validate(parsed)
            if parsed is not None
            else PredictionResponse.model_validate_json(raw)
        )
        return prediction, raw
