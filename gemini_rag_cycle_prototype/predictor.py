from __future__ import annotations

import json
from pathlib import Path

from gemini_rag_cycle_prototype.gemini_client import GeminiClient
from gemini_rag_cycle_prototype.rag.index_builder import RagIndex
from gemini_rag_cycle_prototype.rag.measurement_loader import HARDWARE_PROFILE_ID
from gemini_rag_cycle_prototype.rag.retriever import RetrievalResult, Retriever
from gemini_rag_cycle_prototype.schemas import PredictionResponse


class LeakageError(RuntimeError):
    pass


class Predictor:
    def __init__(
        self, repository_root: Path, index: RagIndex, client: GeminiClient
    ):
        self.root = repository_root.resolve()
        self.index = index
        self.client = client
        prototype = self.root / "gemini_rag_cycle_prototype"
        self.profile = json.loads(
            (prototype / "config" / "hardware_profile.json").read_text(
                encoding="utf-8"
            )
        )
        self.template = (
            prototype / "prompts" / "cycle_prediction_prompt.txt"
        ).read_text(encoding="utf-8")

    def _references(self, retrieval: RetrievalResult) -> str:
        output = []
        for number, hit in enumerate(retrieval.hits, start=1):
            record = hit.record
            output.append(
                "\n".join((
                    f"Reference example ID: {record.task_id}",
                    f"Task name: {record.task_name}",
                    f"Similarity score: {hit.similarity:.6f}",
                    f"Structural summary: {record.structural_summary.model_dump_json()}",
                    f"Hardware profile: {record.hardware_profile_id}",
                    f"Sample count: {record.measurement.sample_count}",
                    f"Measured mean execution time: {record.measurement.mean_us} us",
                    f"Measured maximum execution time: {record.measurement.maximum_us} us",
                    "Relevant C source:",
                    "```c",
                    record.source_code,
                    "```",
                ))
            )
        return "\n\n".join(output) if output else "No sufficiently similar independent references."

    def predict(
        self, source_code: str, function_name: str, *,
        context_code: str = "", top_k: int = 5,
        minimum_similarity: float = 0.45,
        exclude_task_id: str | None = None,
        exclude_function: str | None = None,
        exclude_source_path: str | None = None,
    ) -> tuple[PredictionResponse, str, RetrievalResult]:
        retrieval = Retriever(self.index, self.client).retrieve(
            source_code,
            function_name,
            HARDWARE_PROFILE_ID,
            top_k=top_k,
            minimum_similarity=minimum_similarity,
            exclude_task_id=exclude_task_id,
            exclude_function=exclude_function,
            exclude_source_path=exclude_source_path,
        )
        prompt = self.template.format(
            hardware_profile=json.dumps(self.profile, indent=2),
            function_name=function_name,
            source_code=source_code,
            context_code=context_code or "No additional context files supplied.",
            references=self._references(retrieval),
        )
        prediction, raw = self.client.predict(prompt)
        allowed_ids = {hit.record.task_id for hit in retrieval.hits}
        returned_ids = {
            example.task_id for example in prediction.retrieved_examples_used
        }
        if not returned_ids.issubset(allowed_ids):
            raise LeakageError(
                "Gemini cited a reference that was not in the leakage-filtered retrieval set"
            )
        if prediction.hardware_profile_id != HARDWARE_PROFILE_ID:
            raise ValueError("prediction used the wrong hardware profile")
        if (
            prediction.estimated_nominal_cycles is not None
            and prediction.estimated_nominal_us is not None
        ):
            expected = prediction.estimated_nominal_cycles / 48.0
            if abs(expected - prediction.estimated_nominal_us) > max(0.05, expected * 0.01):
                prediction.warnings.append(
                    "Nominal cycle/us values are inconsistent at 48 MHz; values were recorded unchanged."
                )
        if (
            prediction.estimated_upper_cycles is not None
            and prediction.estimated_upper_us is not None
        ):
            expected = prediction.estimated_upper_cycles / 48.0
            if abs(expected - prediction.estimated_upper_us) > max(0.05, expected * 0.01):
                prediction.warnings.append(
                    "Upper cycle/us values are inconsistent at 48 MHz; values were recorded unchanged."
                )
        prediction.warnings.extend(retrieval.warnings)
        return prediction, raw, retrieval
