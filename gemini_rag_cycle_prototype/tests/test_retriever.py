from __future__ import annotations

import unittest

from gemini_rag_cycle_prototype.rag.index_builder import IndexedRecord, RagIndex
from gemini_rag_cycle_prototype.rag.measurement_loader import (
    HARDWARE_PROFILE_ID,
    normalize_source,
    source_fingerprint,
)
from gemini_rag_cycle_prototype.rag.retriever import Retriever, cosine_similarity
from gemini_rag_cycle_prototype.predictor import (
    LeakageError,
    canonicalize_reference_ids,
)
from gemini_rag_cycle_prototype.schemas import Measurement, RagRecord, StructuralSummary


class FakeEmbedder:
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        return [1.0, 0.0]


class FailingEmbedder(FakeEmbedder):
    def embed_query(self, text: str) -> list[float]:
        raise AssertionError("no-RAG mode must not request a query embedding")


def record(
    task_id: str, name: str, source: str,
    hardware: str = HARDWARE_PROFILE_ID, source_path: str = "task.c",
    dataset_split: str = "calibration",
) -> RagRecord:
    return RagRecord(
        task_id=task_id,
        task_name=name,
        source_path=source_path,
        source_code=source,
        source_fingerprint=source_fingerprint(source),
        normalized_source=normalize_source(source),
        hardware_profile_id=hardware,
        structural_summary=StructuralSummary(),
        measurement=Measurement(mean_us=10.0, maximum_us=12.0, source_path="m.csv"),
        dataset_split=dataset_split,
    )


class RetrieverTest(unittest.TestCase):
    def test_cosine_similarity_and_ranking(self) -> None:
        self.assertAlmostEqual(1.0, cosine_similarity([1, 0], [2, 0]))
        index = RagIndex(
            embedding_model="fake", embedding_dimensions=2,
            records=[
                IndexedRecord(record=record("a", "A", "void A(void){x++;}"), embedding=[0.5, 0.5]),
                IndexedRecord(record=record("b", "B", "void B(void){y++;}"), embedding=[1.0, 0.0]),
            ],
        )
        result = Retriever(index, FakeEmbedder()).retrieve(
            "void Q(void){z++;}", "Q", HARDWARE_PROFILE_ID,
            minimum_similarity=0.0,
        )
        self.assertEqual("b", result.hits[0].record.task_id)

    def test_same_id_name_fingerprint_near_copy_and_hardware_are_excluded(self) -> None:
        query = "void Query(void) { value += 1U; }"
        almost = "void Renamed(void) { value += 1U; }"
        entries = [
            record("same-id", "Different", "void A(void){a++;}"),
            record("name", "Query", "void B(void){b++;}"),
            record("fingerprint", "Other", query),
            record("near", "Renamed", almost),
            record("hardware", "OtherHw", "void C(void){c++;}", "OTHER"),
            record("path", "SamePath", "void P(void){p++;}", source_path="query.c"),
            record("valid", "Valid", "void Valid(void){for(i=0;i<8;i++){x^=i;}}"),
        ]
        index = RagIndex(
            embedding_model="fake", embedding_dimensions=2,
            records=[IndexedRecord(record=item, embedding=[1.0, 0.0]) for item in entries],
        )
        result = Retriever(index, FakeEmbedder()).retrieve(
            query, "Query", HARDWARE_PROFILE_ID,
            exclude_task_id="same-id", minimum_similarity=0.0,
            exclude_source_path="query.c",
            near_duplicate_threshold=0.75,
        )
        self.assertEqual(["valid"], [hit.record.task_id for hit in result.hits])
        reasons = {item["reason"] for item in result.excluded}
        self.assertTrue({
            "same_task_id", "same_function_name", "same_source_fingerprint",
            "near_duplicate_source", "hardware_profile_mismatch",
            "same_source_path",
        }.issubset(reasons))

    def test_unique_retrieved_task_name_is_canonicalized_safely(self) -> None:
        item = record("dataset.csv:2:TaskA", "TaskA", "void TaskA(void){x++;}")
        from gemini_rag_cycle_prototype.rag.retriever import RetrievalHit, RetrievalResult
        retrieval = RetrievalResult(hits=[RetrievalHit(item, 0.9)])
        self.assertEqual(
            {"dataset.csv:2:TaskA"},
            canonicalize_reference_ids({"TaskA"}, retrieval),
        )

    def test_unretrieved_reference_is_still_rejected(self) -> None:
        item = record("dataset.csv:2:TaskA", "TaskA", "void TaskA(void){x++;}")
        from gemini_rag_cycle_prototype.rag.retriever import RetrievalHit, RetrievalResult
        retrieval = RetrievalResult(hits=[RetrievalHit(item, 0.9)])
        with self.assertRaises(LeakageError):
            canonicalize_reference_ids({"NotRetrieved"}, retrieval)


if __name__ == "__main__":
    unittest.main()
