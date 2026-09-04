from __future__ import annotations

from typing import Protocol, Type

from pydantic import BaseModel

from gemini_rag_cycle_prototype.schemas import PredictionResponse


class LlmClient(Protocol):
    provider: str
    model: str
    embedding_model: str
    embedding_dimensions: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...

    def predict(
        self,
        prompt: str,
        response_schema: Type[BaseModel] = PredictionResponse,
    ) -> tuple[BaseModel, str]: ...
