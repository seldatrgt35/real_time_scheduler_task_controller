import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pydantic import ValidationError

from gemini_rag_cycle_prototype.cli import read_required
from gemini_rag_cycle_prototype.gemini_client import GeminiClient, MissingApiKeyError
from gemini_rag_cycle_prototype.predictor import Predictor
from gemini_rag_cycle_prototype.rag.index_builder import RagIndex
from gemini_rag_cycle_prototype.schemas import PredictionResponse, SourceAnalysis


def prediction(**overrides) -> dict:
    base = {
        "analysis_status": "SUPPORTED",
        "function_name": "Task",
        "hardware_profile_id": "S32K148_GCC11_4_O0_48MHz_source_only",
        "source_analysis": SourceAnalysis().model_dump(),
        "retrieved_examples_used": [],
        "estimated_nominal_cycles": 480,
        "estimated_upper_cycles": 576,
        "estimated_nominal_us": 10.0,
        "estimated_upper_us": 12.0,
        "confidence_percent": 70,
        "estimation_reasoning_summary": "references and source structure",
        "assumptions": [],
        "unresolved": [],
        "warnings": [],
    }
    base.update(overrides)
    return base


class ValidationAndCliTest(unittest.TestCase):
    def test_upper_cycle_cannot_be_smaller_than_nominal(self) -> None:
        with self.assertRaises(ValidationError):
            PredictionResponse.model_validate(
                prediction(estimated_upper_cycles=479)
            )

    def test_confidence_must_be_in_range(self) -> None:
        with self.assertRaises(ValidationError):
            PredictionResponse.model_validate(prediction(confidence_percent=101))

    def test_supported_requires_all_predictions(self) -> None:
        with self.assertRaises(ValidationError):
            PredictionResponse.model_validate(prediction(estimated_upper_us=None))

    def test_unresolved_requires_explanation(self) -> None:
        with self.assertRaises(ValidationError):
            PredictionResponse.model_validate(
                prediction(
                    analysis_status="UNRESOLVED",
                    estimated_nominal_cycles=None,
                    estimated_upper_cycles=None,
                    estimated_nominal_us=None,
                    estimated_upper_us=None,
                )
            )

    def test_missing_api_key_is_reported_without_secret_value(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(MissingApiKeyError) as raised:
                GeminiClient()
        self.assertNotIn("AQ.", str(raised.exception))

    def test_missing_source_file_is_reported(self) -> None:
        with self.assertRaises(FileNotFoundError):
            read_required(Path("does-not-exist.c"), "C source")

    def test_no_rag_prediction_does_not_request_embedding(self) -> None:
        class SourceOnlyClient:
            def embed_query(self, text):
                raise AssertionError("query embedding must not be requested")

            def predict(self, prompt):
                self.prompt = prompt
                return PredictionResponse.model_validate(prediction()), "{}"

        root = Path(__file__).resolve().parents[2]
        client = SourceOnlyClient()
        result, _, retrieval = Predictor(
            root,
            RagIndex(
                embedding_model="unused", embedding_dimensions=768, records=[]
            ),
            client,
        ).predict(
            "void Task(void) {}", "Task", use_rag=False
        )
        self.assertEqual("SUPPORTED", result.analysis_status)
        self.assertEqual([], retrieval.hits)
        self.assertIn("No sufficiently similar independent references", client.prompt)
        self.assertIn("dynamic helper invocations", client.prompt)
        self.assertIn("mandatory bottom-up cross-check", client.prompt)
        self.assertIn("merely listing counts without pricing them is insufficient", client.prompt)

    def test_prompt_requires_nested_loop_callee_cost_expansion(self) -> None:
        root = Path(__file__).resolve().parents[2]
        template = (
            root
            / "gemini_rag_cycle_prototype"
            / "prompts"
            / "cycle_prediction_prompt.txt"
        ).read_text(encoding="utf-8")
        self.assertIn("helper called once in a 6 by 6 loop executes 36 times", template)
        self.assertIn("callee-body work", template)
        self.assertIn("product of enclosing loop bounds", template)
        self.assertIn("compact arithmetic decomposition", template)


if __name__ == "__main__":
    unittest.main()
