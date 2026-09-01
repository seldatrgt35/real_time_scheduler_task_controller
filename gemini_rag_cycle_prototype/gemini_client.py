from __future__ import annotations

import os
from pathlib import Path
import time
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

    def _embed_one(self, text: str, task_type: str) -> list[float]:
        response = self._client.models.embed_content(
            model=self.embedding_model,
            contents=text,
            config=self._types.EmbedContentConfig(
                task_type=task_type,
                output_dimensionality=self.embedding_dimensions,
            ),
        )
        embeddings = getattr(response, "embeddings", None) or []
        if len(embeddings) != 1:
            raise ValueError(
                "Embedding count mismatch for one input: "
                f"expected 1, received {len(embeddings)}"
            )
        values = list(embeddings[0].values)
        if len(values) != self.embedding_dimensions:
            raise ValueError(
                "Embedding dimension mismatch: "
                f"expected {self.embedding_dimensions}, received {len(values)}"
            )
        return values

    def _embed(self, texts: list[str], task_type: str) -> list[list[float]]:
        # The SDK/model may aggregate contents=[text1, text2, ...] into one
        # embedding. Keep one API request per input so N documents always map
        # to N independently generated vectors, in the original input order.
        embeddings: list[list[float]] = []
        chunk_size = max(1, int(os.getenv("GEMINI_EMBEDDING_REQUEST_CHUNK", "16")))
        for start in range(0, len(texts), chunk_size):
            for text in texts[start:start + chunk_size]:
                embeddings.append(self._embed_one(text, task_type))
        if len(embeddings) != len(texts):
            raise ValueError(
                "Embedding count mismatch: "
                f"expected {len(texts)}, received {len(embeddings)}"
            )
        return embeddings

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts, "RETRIEVAL_DOCUMENT")

    def embed_query(self, text: str) -> list[float]:
        values = self._embed([text], "RETRIEVAL_QUERY")
        if not values:
            raise RuntimeError("Gemini returned no query embedding")
        return values[0]

    def _generate_content_with_retry(self, prompt: str, config: Any) -> Any:
        attempts = max(1, int(os.getenv("GEMINI_GENERATION_ATTEMPTS", "3")))
        for attempt in range(attempts):
            try:
                return self._client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=config,
                )
            except Exception as exc:
                # Retry only temporary service/rate conditions. Authentication,
                # schema and other client errors must fail immediately.
                code = getattr(exc, "code", None)
                if code not in {429, 500, 502, 503, 504} or attempt + 1 >= attempts:
                    raise
                time.sleep(5 * (2 ** attempt))

    def predict(self, prompt: str) -> tuple[PredictionResponse, str]:
        # Structured assembly responses can be much larger than the earlier
        # summary-only JSON. Without an explicit budget Gemini may stop at its
        # default output limit and return syntactically incomplete JSON.
        max_output_tokens = max(
            8192, int(os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "65536"))
        )
        response = self._generate_content_with_retry(
            prompt,
            self._types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=max_output_tokens,
                response_mime_type="application/json",
                response_schema=PredictionResponse,
                automatic_function_calling=(
                    self._types.AutomaticFunctionCallingConfig(disable=True)
                ),
            ),
        )
        raw = response.text or ""
        parsed = getattr(response, "parsed", None)
        try:
            prediction = (
                parsed
                if isinstance(parsed, PredictionResponse)
                else PredictionResponse.model_validate(parsed)
                if parsed is not None
                else PredictionResponse.model_validate_json(raw)
            )
        except Exception as exc:
            diagnostic_path = Path(os.getenv(
                "GEMINI_INVALID_RESPONSE_PATH",
                "gemini_rag_cycle_prototype/results/last_invalid_gemini_response.json",
            ))
            diagnostic_path.parent.mkdir(parents=True, exist_ok=True)
            diagnostic_path.write_text(raw, encoding="utf-8")
            finish_reason = None
            candidates = getattr(response, "candidates", None) or []
            if candidates:
                finish_reason = getattr(candidates[0], "finish_reason", None)
            if not raw.rstrip().endswith(("}", "]")):
                raise ValueError(
                    "Gemini returned truncated JSON before validation; "
                    f"received {len(raw)} characters, finish_reason="
                    f"{finish_reason!s}, max_output_tokens={max_output_tokens}. "
                    "The incomplete response was saved to "
                    f"{diagnostic_path}."
                ) from exc
            raise
        return prediction, raw
