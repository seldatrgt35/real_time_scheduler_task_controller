from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Type
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import BaseModel

from gemini_rag_cycle_prototype.schemas import PredictionResponse


class OllamaClient:
    """Local Ollama generation and embedding client.

    Uses Ollama's native HTTP API so no additional Python dependency is needed.
    """

    provider = "ollama"

    def __init__(
        self, *, model: str | None = None, embedding_model: str | None = None,
        embedding_dimensions: int | None = None, base_url: str | None = None,
    ):
        self.model = model or os.getenv("OLLAMA_MODEL", "qwen2.5-coder:14b")
        self.embedding_model = embedding_model or os.getenv(
            "OLLAMA_EMBEDDING_MODEL", "nomic-embed-text"
        )
        self.embedding_dimensions = embedding_dimensions or int(
            os.getenv("OLLAMA_EMBEDDING_DIMENSIONS", "768")
        )
        self.base_url = (base_url or os.getenv(
            "OLLAMA_BASE_URL", "http://127.0.0.1:11434"
        )).rstrip("/")
        self.request_timeout_seconds = max(
            1, int(os.getenv("OLLAMA_REQUEST_TIMEOUT_SECONDS", "3600"))
        )
        self.temperature = float(os.getenv("OLLAMA_TEMPERATURE", "0"))
        self.seed = int(os.getenv("OLLAMA_SEED", "42"))

    def _post(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = Request(
            self.base_url + endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.request_timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Ollama HTTP {exc.code} for {endpoint}: {detail}"
            ) from exc
        except URLError as exc:
            raise RuntimeError(
                "Cannot connect to Ollama at " + self.base_url
                + ". Start it with 'ollama serve' and pull the configured model."
            ) from exc

    def _generate_streaming(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Read generation chunks continuously so long CPU runs stay alive."""
        payload = dict(payload)
        payload["stream"] = True
        request = Request(
            self.base_url + "/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        fragments: list[str] = []
        final: dict[str, Any] = {}
        chunk_count = 0
        try:
            with urlopen(request, timeout=self.request_timeout_seconds) as response:
                for encoded_line in response:
                    if not encoded_line.strip():
                        continue
                    chunk = json.loads(encoded_line.decode("utf-8"))
                    if chunk.get("error"):
                        raise RuntimeError("Ollama generation error: " + chunk["error"])
                    fragments.append(chunk.get("response") or "")
                    chunk_count += 1
                    if chunk_count % 100 == 0:
                        print(
                            f"[Ollama] received {chunk_count} output tokens...",
                            file=sys.stderr, flush=True,
                        )
                    if chunk.get("done"):
                        final = chunk
        except (HTTPError, URLError, TimeoutError, ConnectionError, OSError) as exc:
            raise RuntimeError(
                "Ollama generation connection failed at " + self.base_url
                + ". The model may be CPU-bound or the server may have stopped."
            ) from exc
        final["response"] = "".join(fragments)
        return final

    def _validate_embedding(self, values: Any) -> list[float]:
        vector = [float(value) for value in values]
        if len(vector) != self.embedding_dimensions:
            raise ValueError(
                "Embedding dimension mismatch: expected "
                f"{self.embedding_dimensions}, received {len(vector)}"
            )
        return vector

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        response = self._post("/api/embed", {
            "model": self.embedding_model,
            "input": texts,
            "truncate": False,
        })
        embeddings = response.get("embeddings") or []
        if len(embeddings) != len(texts):
            raise ValueError(
                f"Embedding count mismatch: expected {len(texts)}, "
                f"received {len(embeddings)}"
            )
        return [self._validate_embedding(values) for values in embeddings]

    def embed_query(self, text: str) -> list[float]:
        embeddings = self.embed_documents([text])
        if len(embeddings) != 1:
            raise ValueError(
                f"Embedding count mismatch: expected 1, received {len(embeddings)}"
            )
        return embeddings[0]

    def predict(
        self,
        prompt: str,
        response_schema: Type[BaseModel] = PredictionResponse,
    ) -> tuple[BaseModel, str]:
        attempts = max(1, int(os.getenv("OLLAMA_VALIDATION_ATTEMPTS", "3")))
        current_prompt = prompt
        last_error: Exception | None = None
        schema = response_schema.model_json_schema()
        for attempt in range(attempts):
            print(
                f"[Ollama] model={self.model}, structured validation attempt "
                f"{attempt + 1}/{attempts}", file=sys.stderr, flush=True,
            )
            started = time.monotonic()
            response = self._generate_streaming({
                "model": self.model,
                "prompt": current_prompt,
                "format": schema,
                "keep_alive": os.getenv("OLLAMA_KEEP_ALIVE", "10m"),
                "options": {
                    "temperature": self.temperature,
                    "seed": self.seed,
                    "num_ctx": int(os.getenv("OLLAMA_NUM_CTX", "16384")),
                    "num_predict": int(os.getenv("OLLAMA_NUM_PREDICT", "6144")),
                },
            })
            raw = response.get("response") or ""
            print(
                f"[Ollama] completed in {time.monotonic() - started:.1f}s",
                file=sys.stderr, flush=True,
            )
            try:
                return response_schema.model_validate_json(raw), raw
            except Exception as exc:
                last_error = exc
                print(
                    "[Ollama] response rejected by validator:\n" + str(exc),
                    file=sys.stderr, flush=True,
                )
                self._save_invalid_response(raw, attempt + 1, exc)
                if attempt + 1 < attempts:
                    current_prompt = self._repair_prompt(prompt, exc, response_schema)
                    continue
                raise
        assert last_error is not None
        raise last_error

    @staticmethod
    def _repair_prompt(
        original_prompt: str,
        error: Exception,
        response_schema: Type[BaseModel] | None = None,
    ) -> str:
        schema_fields = getattr(response_schema, "model_fields", {}) if response_schema else {}
        if "estimated_source_execution_cycles" in schema_fields:
            specific_guidance = (
                "For every instruction ledger entry, total_cycles must equal dynamic_count * cycles_each. "
                "Use only instruction classes and exact cycles_each values present in the supplied timing profile. "
                "estimated_source_execution_cycles must equal the sum of all ledger total_cycles values, and "
                "estimated_source_execution_us must equal that sum divided by 48.0 exactly. "
                "PARTIAL requires a non-empty ledger and both estimates. confidence_percent must not exceed 50.\n"
            )
        elif "selected_path" in schema_fields and "blocks" in schema_fields:
            specific_guidance = (
                "Ensure every block referenced in selected_path, edge source_block/target_block, and successors "
                "is explicitly and fully defined in the 'blocks' list. Keep the basic blocks consolidated and "
                "do not emit unlisted or incomplete blocks.\n"
            )
        else:
            specific_guidance = ""

        return (
            original_prompt
            + "\n\nVALIDATION REPAIR REQUIRED\n"
            + "Regenerate the complete JSON response from scratch. Return JSON "
              "only and strictly satisfy the supplied response schema. Do not return a "
              "patch, commentary, or markdown markers.\n"
            + specific_guidance
            + "Validator diagnostics:\n"
            + str(error)
        )

    @staticmethod
    def _save_invalid_response(
        raw: str, attempt: int, error: Exception | None = None
    ) -> None:
        base_path = Path(os.getenv(
            "OLLAMA_INVALID_RESPONSE_PATH",
            "gemini_rag_cycle_prototype/results/last_invalid_ollama_response.json",
        ))
        base_path.parent.mkdir(parents=True, exist_ok=True)
        base_path.write_text(raw, encoding="utf-8")
        attempt_path = base_path.with_name(
            f"{base_path.stem}.attempt-{attempt}{base_path.suffix}"
        )
        attempt_path.write_text(raw, encoding="utf-8")
        if error is not None:
            attempt_path.with_suffix(".error.txt").write_text(
                str(error), encoding="utf-8"
            )
