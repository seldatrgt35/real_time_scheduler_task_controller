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
            "void Task(void) {}", "Task", use_rag=False,
            input_constraints="input is bounded to 0..7",
            timing_evidence="no cycle-cost table is available",
        )
        self.assertEqual("SUPPORTED", result.analysis_status)
        self.assertEqual([], retrieval.hits)
        self.assertIn("No sufficiently similar independent references", client.prompt)
        self.assertIn("strict source-only analysis", client.prompt)
        self.assertIn("input is bounded to 0..7", client.prompt)
        self.assertIn("no cycle-cost table is available", client.prompt)
        self.assertIn("dynamic_calls * cycles_per_call", client.prompt)

    def test_prompt_requires_nested_loop_callee_cost_expansion(self) -> None:
        root = Path(__file__).resolve().parents[2]
        template = (
            root
            / "gemini_rag_cycle_prototype"
            / "prompts"
            / "cycle_prediction_prompt.txt"
        ).read_text(encoding="utf-8")
        self.assertIn("Multiply nested loop", template)
        self.assertIn("helper bodies", template)
        self.assertIn("product of enclosing loop", template)
        self.assertIn("dynamic_work_ledger", template)

    def test_prompt_rejects_unsupported_source_only_hardware_assumptions(self) -> None:
        root = Path(__file__).resolve().parents[2]
        prototype = root / "gemini_rag_cycle_prototype"
        template = (prototype / "prompts" / "cycle_prediction_prompt.txt").read_text(
            encoding="utf-8"
        )
        profile = (prototype / "config" / "hardware_profile.json").read_text(
            encoding="utf-8"
        )
        self.assertIn("Internal-SRAM data does not imply", template)
        self.assertIn("do not invent a precise Flash penalty", template)
        self.assertIn("Do not cite a generic", template)
        self.assertIn("upper_basis to NOT_AVAILABLE", template)
        self.assertIn('"instruction_location": "internal PFlash', profile)
        self.assertIn('"flash_wait_states": "not supplied', profile)

    def test_helper_ledger_rejects_inconsistent_multiplication(self) -> None:
        with self.assertRaises(ValidationError):
            PredictionResponse.model_validate(prediction(
                dynamic_work_ledger={
                    "helper_invocations": [{
                        "function": "Helper",
                        "dynamic_calls": 6,
                        "nominal_cycles_per_call": 10,
                        "nominal_total_cycles": 59,
                    }]
                }
            ))

    def test_component_total_must_match_final_cycles(self) -> None:
        with self.assertRaises(ValidationError):
            PredictionResponse.model_validate(prediction(
                dynamic_work_ledger={
                    "nominal_cycle_components": [
                        {"name": "source", "cycles": 479, "basis": "estimate"}
                    ]
                }
            ))

    def test_formal_guarantee_claim_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            PredictionResponse.model_validate(prediction(formal_guarantee=True))

    def test_missing_upper_requires_not_available_basis(self) -> None:
        result = PredictionResponse.model_validate(prediction(
            analysis_status="PARTIAL",
            estimated_upper_cycles=None,
            estimated_upper_us=None,
            upper_basis="NOT_AVAILABLE",
            unresolved=["PFlash timing evidence is missing"],
        ))
        self.assertEqual("NOT_AVAILABLE", result.upper_basis)


if __name__ == "__main__":
    unittest.main()
