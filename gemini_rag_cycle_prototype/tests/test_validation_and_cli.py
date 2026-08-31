import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pydantic import ValidationError

from gemini_rag_cycle_prototype.cli import load_current_index, read_required
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
        "estimation_basis": "SOURCE_ONLY",
        "reference_anchor_task_id": None,
        "reference_anchor_measured_us": None,
        "reference_adjustments": [],
        "cycle_components": [
            {"name": "source_visible_work", "cycles": 300, "evidence": "ledger"},
            {"name": "resolved_helper_work", "cycles": 180, "evidence": "helper expansion"},
        ],
        "estimated_source_execution_cycles": 480,
        "estimated_source_execution_us": 10.0,
        "formal_guarantee": False,
        "confidence_percent": 50,
        "estimation_reasoning_summary": "references and source structure",
        "assumptions": [],
        "unresolved": [],
        "warnings": [],
    }
    base.update(overrides)
    return base


class ValidationAndCliTest(unittest.TestCase):
    def test_response_schema_is_compatible_with_gemini_developer_api(self) -> None:
        schema = PredictionResponse.model_json_schema()

        def contains_additional_properties(value) -> bool:
            if isinstance(value, dict):
                return (
                    "additionalProperties" in value
                    or any(contains_additional_properties(child) for child in value.values())
                )
            if isinstance(value, list):
                return any(contains_additional_properties(child) for child in value)
            return False

        self.assertFalse(contains_additional_properties(schema))
        properties = schema["properties"]
        self.assertIn("estimated_source_execution_cycles", properties)
        self.assertIn("estimated_source_execution_us", properties)
        self.assertIn("cycle_components", properties)
        self.assertIn("estimation_basis", properties)
        self.assertNotIn("estimated_execution_cycles", properties)
        self.assertNotIn("estimated_nominal_cycles", properties)
        self.assertNotIn("estimated_upper_cycles", properties)

    def test_execution_cycles_must_be_positive(self) -> None:
        with self.assertRaises(ValidationError):
            PredictionResponse.model_validate(
                prediction(estimated_source_execution_cycles=0)
            )

    def test_confidence_must_be_in_range(self) -> None:
        with self.assertRaises(ValidationError):
            PredictionResponse.model_validate(prediction(confidence_percent=101))

    def test_reference_anchor_requires_measurement_and_adjustments(self) -> None:
        with self.assertRaisesRegex(ValidationError, "requires anchor task ID"):
            PredictionResponse.model_validate(
                prediction(estimation_basis="REFERENCE_ANCHORED")
            )
        parsed = PredictionResponse.model_validate(prediction(
            estimation_basis="REFERENCE_ANCHORED",
            reference_anchor_task_id="board.csv:2:ReferenceTask",
            reference_anchor_measured_us=10.0,
            reference_adjustments=["same loop count; extra branch added"],
        ))
        self.assertEqual("REFERENCE_ANCHORED", parsed.estimation_basis)

    def test_supported_requires_all_predictions(self) -> None:
        with self.assertRaises(ValidationError):
            PredictionResponse.model_validate(
                prediction(estimated_source_execution_us=None)
            )

    def test_component_sum_must_equal_source_estimate(self) -> None:
        with self.assertRaisesRegex(ValidationError, "sum of priced cycle components"):
            PredictionResponse.model_validate(
                prediction(estimated_source_execution_cycles=481)
            )

    def test_unpriced_component_requires_partial_and_visible_unknowns(self) -> None:
        components = [
            {"name": "source_visible_work", "cycles": 480, "evidence": "ledger"},
            {"name": "pflash_fetch_overhead", "cycles": None, "evidence": "unknown"},
        ]
        with self.assertRaisesRegex(ValidationError, "require PARTIAL"):
            PredictionResponse.model_validate(prediction(cycle_components=components))
        parsed = PredictionResponse.model_validate(prediction(
            analysis_status="PARTIAL",
            cycle_components=components,
            unresolved=["PFlash timing is not supplied"],
            warnings=["Estimate excludes unpriced PFlash contribution"],
        ))
        self.assertEqual(480, parsed.estimated_source_execution_cycles)

    def test_unresolved_requires_explanation(self) -> None:
        with self.assertRaises(ValidationError):
            PredictionResponse.model_validate(
                prediction(
                    analysis_status="UNRESOLVED",
                    estimated_source_execution_cycles=None,
                    estimated_source_execution_us=None,
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

    def test_stale_rag_index_is_rejected_before_prediction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "index.json"
            path.write_text(RagIndex(
                embedding_model="fake",
                embedding_dimensions=2,
                document_format_version=1,
                records=[],
            ).model_dump_json(), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "--rebuild-index"):
                load_current_index(path)

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
        self.assertIn("dynamic call count", client.prompt)
        self.assertIn("UNPRICED HARDWARE RULE", client.prompt)
        self.assertIn("Do not add it to `estimated_source_execution_cycles`", client.prompt)

    def test_prompt_requires_nested_loop_callee_cost_expansion(self) -> None:
        root = Path(__file__).resolve().parents[2]
        template = (
            root
            / "gemini_rag_cycle_prototype"
            / "prompts"
            / "cycle_prediction_prompt.txt"
        ).read_text(encoding="utf-8")
        self.assertIn("once in a 6 by 6 loop executes 36 times", template)
        self.assertIn("Expand each supplied helper body", template)
        self.assertIn("Multiply nested-loop bounds", template)
        self.assertIn("arithmetic matching the component sum", template)

    def test_prompt_rejects_unsupported_source_only_hardware_assumptions(self) -> None:
        root = Path(__file__).resolve().parents[2]
        prototype = root / "gemini_rag_cycle_prototype"
        template = (prototype / "prompts" / "cycle_prediction_prompt.txt").read_text(
            encoding="utf-8"
        )
        profile = (prototype / "config" / "hardware_profile.json").read_text(
            encoding="utf-8"
        )
        self.assertIn("Null components contribute zero", template)
        self.assertIn("Assuming one or another number of Flash wait states", template)
        self.assertIn("Multiplying by 1.3, 1.6", template)
        self.assertIn("Do not target a desired error percentage", template)
        self.assertIn("Combined retrieval score >= 0.85", template)
        self.assertIn("Do not discard a strong measured anchor", template)
        self.assertIn('"instruction_location": "internal PFlash', profile)
        self.assertIn('"flash_wait_states": "not supplied', profile)


if __name__ == "__main__":
    unittest.main()
