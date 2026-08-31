from __future__ import annotations

from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from gemini_rag_cycle_prototype.gemini_client import GeminiClient
from gemini_rag_cycle_prototype.rag.index_builder import (
    EMBEDDING_DOCUMENT_FORMAT_VERSION,
    IndexedRecord,
    RagIndex,
    build_index,
)
from gemini_rag_cycle_prototype.schemas import Measurement, RagRecord, StructuralSummary


class FakeEmbedContentConfig:
    def __init__(self, **values):
        self.values = values


class FakeModels:
    def __init__(self, outputs: dict[str, list[list[float]]]):
        self.outputs = outputs
        self.calls: list[str] = []

    def embed_content(self, *, model, contents, config):
        self.calls.append(contents)
        return SimpleNamespace(
            embeddings=[SimpleNamespace(values=value) for value in self.outputs[contents]]
        )


def client(outputs: dict[str, list[list[float]]], dimensions: int = 3) -> GeminiClient:
    instance = GeminiClient.__new__(GeminiClient)
    instance._client = SimpleNamespace(models=FakeModels(outputs))
    instance._types = SimpleNamespace(EmbedContentConfig=FakeEmbedContentConfig)
    instance.embedding_model = "fake"
    instance.embedding_dimensions = dimensions
    return instance


def record(task_id: str) -> RagRecord:
    source = f"void Task_{task_id}(void) {{ value += {task_id}U; }}"
    return RagRecord(
        task_id=task_id,
        task_name=f"Task_{task_id}",
        source_path=f"{task_id}.c",
        source_code=source,
        callee_source="void Helper(void) { hidden++; }",
        source_context="#define HIDDEN_COUNT (99U)",
        source_fingerprint=task_id,
        normalized_source=source,
        hardware_profile_id="hardware",
        structural_summary=StructuralSummary(),
        measurement=Measurement(source_path="measurements.csv"),
        dataset_split="calibration",
    )


class GeminiEmbeddingTest(unittest.TestCase):
    def test_index_rebuild_reuses_unchanged_embeddings(self) -> None:
        existing_record = record("1")
        new_record = record("2")
        calls = []

        def embed_documents(texts):
            calls.append(texts)
            return [[0.0, 1.0, 0.0]]

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "index.json"
            path.write_text(
                RagIndex(
                    embedding_model="fake",
                    embedding_dimensions=3,
                    document_format_version=EMBEDDING_DOCUMENT_FORMAT_VERSION,
                    records=[IndexedRecord(
                        record=existing_record,
                        embedding=[1.0, 0.0, 0.0],
                    )],
                ).model_dump_json(),
                encoding="utf-8",
            )
            rebuilt = build_index(
                [existing_record, new_record],
                SimpleNamespace(embed_documents=embed_documents),
                path,
                "fake",
                3,
            )

        self.assertEqual(1, len(calls))
        self.assertEqual(1, len(calls[0]))
        self.assertIn("Task_2", calls[0][0])
        self.assertNotIn("Helper", calls[0][0])
        self.assertNotIn("HIDDEN_COUNT", calls[0][0])
        self.assertEqual(
            EMBEDDING_DOCUMENT_FORMAT_VERSION,
            rebuilt.document_format_version,
        )
        self.assertEqual(
            [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
            [item.embedding for item in rebuilt.records],
        )

    def test_three_documents_produce_three_ordered_embeddings(self) -> None:
        gemini = client({
            "first": [[1.0, 0.0, 0.0]],
            "second": [[0.0, 1.0, 0.0]],
            "third": [[0.0, 0.0, 1.0]],
        })
        result = gemini.embed_documents(["first", "second", "third"])
        self.assertEqual(
            [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
            result,
        )
        self.assertEqual(["first", "second", "third"], gemini._client.models.calls)

    def test_single_query_produces_one_embedding(self) -> None:
        gemini = client({"query": [[0.1, 0.2, 0.3]]})
        self.assertEqual([0.1, 0.2, 0.3], gemini.embed_query("query"))
        self.assertEqual(["query"], gemini._client.models.calls)

    def test_aggregated_response_is_not_accepted_for_one_input(self) -> None:
        gemini = client({"first": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]})
        with self.assertRaisesRegex(
            ValueError, "expected 1, received 2"
        ):
            gemini.embed_documents(["first"])

    def test_wrong_embedding_dimension_is_rejected_by_client(self) -> None:
        gemini = client({"first": [[1.0, 0.0]]})
        with self.assertRaisesRegex(
            ValueError, "expected 3, received 2"
        ):
            gemini.embed_documents(["first"])

    def test_wrong_embedding_count_is_rejected_by_index(self) -> None:
        embedder = SimpleNamespace(
            embed_documents=lambda texts: [[1.0, 0.0, 0.0]],
        )
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(
                ValueError, "expected 3, received 1"
            ):
                build_index(
                    [record("1"), record("2"), record("3")],
                    embedder,
                    Path(directory) / "index.json",
                    "fake",
                    3,
                )

    def test_wrong_embedding_dimension_is_rejected_by_index(self) -> None:
        embedder = SimpleNamespace(embed_documents=lambda texts: [[1.0, 0.0]])
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(
                ValueError, "record 0: expected 3, received 2"
            ):
                build_index(
                    [record("1")], embedder, Path(directory) / "index.json",
                    "fake", 3,
                )

    def test_generation_retries_temporary_503_and_preserves_request(self) -> None:
        class TemporaryError(Exception):
            code = 503

        calls = []

        def generate_content(**kwargs):
            calls.append(kwargs)
            if len(calls) < 3:
                raise TemporaryError("high demand")
            return "response"

        gemini = GeminiClient.__new__(GeminiClient)
        gemini._client = SimpleNamespace(
            models=SimpleNamespace(generate_content=generate_content)
        )
        gemini.model = "test-model"
        with patch("gemini_rag_cycle_prototype.gemini_client.time.sleep") as sleep:
            result = gemini._generate_content_with_retry("prompt", "config")
        self.assertEqual("response", result)
        self.assertEqual(3, len(calls))
        self.assertTrue(all(call["contents"] == "prompt" for call in calls))
        self.assertEqual([5, 10], [call.args[0] for call in sleep.call_args_list])

    def test_generation_does_not_retry_non_transient_error(self) -> None:
        class InvalidRequest(Exception):
            code = 400

        gemini = GeminiClient.__new__(GeminiClient)
        gemini._client = SimpleNamespace(
            models=SimpleNamespace(
                generate_content=lambda **kwargs: (_ for _ in ()).throw(
                    InvalidRequest("invalid")
                )
            )
        )
        gemini.model = "test-model"
        with patch("gemini_rag_cycle_prototype.gemini_client.time.sleep") as sleep:
            with self.assertRaises(InvalidRequest):
                gemini._generate_content_with_retry("prompt", "config")
        sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
