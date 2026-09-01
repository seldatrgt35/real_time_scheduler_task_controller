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
from gemini_rag_cycle_prototype.schemas import (
    PredictionResponse, PredictedInstruction, SourceAnalysis,
)


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


def structured_prediction() -> dict:
    payload = prediction(
        analysis_status="PARTIAL",
        cycle_components=[{
            "name": "predicted_thumb2_cycle_sum", "cycles": 5,
            "evidence": "structured instruction",
        }],
        estimated_source_execution_cycles=5,
        estimated_source_execution_us=5 / 48,
        unresolved=["exact PFlash timing"],
        warnings=["source-only assembly prediction"],
    )
    payload["instruction_cycle_ledger"] = [{
        "instruction_class": "alu_move_compare_shift",
        "dynamic_count": 1, "cycles_each": 1, "total_cycles": 1,
        "evidence": "entry block",
    }, {
        "instruction_class": "function_return_with_refill",
        "dynamic_count": 1, "cycles_each": 4, "total_cycles": 4,
        "evidence": "BX LR",
    }]
    payload["predicted_functions"] = [{
        "function_name": "Task", "execution_count": 1,
        "entry_block_id": "entry", "stack_allocation_bytes": 0,
        "stack_deallocation_bytes": 0, "lr_saved": False,
        "valid_return_via": "BX_LR", "loop_bounds_proven": True,
        "blocks": [{
            "block_id": "entry", "execution_count": 1, "successors": [],
            "instructions": [{
                "opcode": "adds", "operands": "r0, #1",
                "instruction_class": "alu_move_compare_shift",
                "count_per_block": 1,
                "timing_profile_record": "alu_move_compare_shift",
            }, {
                "opcode": "bx", "operands": "lr",
                "instruction_class": "function_return",
                "count_per_block": 1,
                "timing_profile_record": "function_return_with_refill",
            }],
        }],
    }]
    return payload


class ValidationAndCliTest(unittest.TestCase):
    def test_derivable_branch_and_register_transfer_fields_are_normalized(self) -> None:
        branch = PredictedInstruction.model_validate({
            "opcode": "bhi.n", "operands": "target",
            "instruction_class": "conditional_branch_taken",
            "count_per_block": 1,
            "timing_profile_record": "conditional_branch_taken",
            "not_taken_timing_profile_record": "conditional_branch_taken",
            "taken_count": 2, "not_taken_count": 1,
        })
        self.assertEqual("conditional_branch", branch.instruction_class)
        self.assertEqual(
            "conditional_branch_not_taken", branch.not_taken_timing_profile_record
        )
        pop = PredictedInstruction.model_validate({
            "opcode": "pop", "operands": "{r4, r7, pc}",
            "instruction_class": "function_return",
            "count_per_block": 1,
            "timing_profile_record": "function_return_with_refill",
        })
        self.assertEqual(3, pop.register_transfer_count)
        self.assertEqual(
            "push_or_pop_register_transfer", pop.timing_profile_record
        )
        combined = PredictedInstruction.model_validate({
            "opcode": "mov sp, r7", "operands": "",
            "instruction_class": "alu_move_compare_shift",
            "timing_profile_record": "alu_move_compare_shift",
        })
        self.assertEqual("mov", combined.opcode)
        self.assertEqual("sp, r7", combined.operands)

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
        self.assertIn("PREDICT GCC -O0 THUMB-2 BASIC BLOCKS", client.prompt)
        self.assertIn("predicted_thumb2_cycle_sum", client.prompt)
        self.assertIn("INSTRUCTION TIMING EVIDENCE", client.prompt)
        self.assertIn("RETRIEVED GCC 11.4 -O0 TRANSFORMATION EVIDENCE", client.prompt)
        self.assertNotIn("RETRIEVED MEASURED BOARD REFERENCES", client.prompt)

    def test_rag_and_no_rag_use_distinct_prompt_templates(self) -> None:
        root = Path(__file__).resolve().parents[2]
        prototype = root / "gemini_rag_cycle_prototype" / "prompts"
        rag = (prototype / "cycle_prediction_prompt.txt").read_text(
            encoding="utf-8"
        )
        source_only = (prototype / "source_only_prediction_prompt.txt").read_text(
            encoding="utf-8"
        )
        self.assertIn("REFERENCE_ANCHORED", rag)
        self.assertIn("RETRIEVED MEASURED BOARD REFERENCES", rag)
        self.assertIn("predicted_thumb2_cycle_sum", source_only)
        self.assertIn("instruction_cycle_ledger", source_only)
        self.assertIn("PREDICT GCC -O0 THUMB-2 BASIC BLOCKS", source_only)
        self.assertNotIn("{references}", source_only)

    def test_instruction_ledger_arithmetic_and_component_sum_are_enforced(self) -> None:
        payload = prediction()
        payload["analysis_status"] = "PARTIAL"
        payload["cycle_components"] = [{
            "name": "predicted_thumb2_cycle_sum",
            "cycles": 10,
            "evidence": "predicted instructions",
        }]
        payload["estimated_source_execution_cycles"] = 10
        payload["estimated_source_execution_us"] = 10 / 48
        payload["predicted_assembly_outline"] = ["Task.entry x1: PUSH, LDR, ADD"]
        payload["predicted_functions"] = [{
            "function_name": "Task",
            "execution_count": 1,
            "entry_block_id": "entry",
            "stack_allocation_bytes": 0,
            "stack_deallocation_bytes": 0,
            "lr_saved": False,
            "valid_return_via": "BX_LR",
            "loop_bounds_proven": True,
            "blocks": [{
                "block_id": "entry",
                "execution_count": 1,
                "successors": [],
                "instructions": [{
                    "opcode": "adds",
                    "operands": "r0, #1",
                    "instruction_class": "alu_move_compare_shift",
                    "count_per_block": 5,
                    "timing_profile_record": "alu_move_compare_shift",
                }, {
                    "opcode": "bx",
                    "operands": "lr",
                    "instruction_class": "function_return",
                    "count_per_block": 1,
                    "timing_profile_record": "function_return_with_refill",
                }],
            }],
        }]
        payload["instruction_cycle_ledger"] = [{
            "instruction_class": "alu_move_compare_shift",
            "dynamic_count": 5,
            "cycles_each": 1,
            "total_cycles": 4,
            "evidence": "predicted basic blocks",
        }, {
            "instruction_class": "function_return_with_refill",
            "dynamic_count": 1,
            "cycles_each": 4,
            "total_cycles": 4,
            "evidence": "return",
        }]
        payload["unresolved"] = ["exact PFlash timing"]
        payload["warnings"] = ["predicted assembly"]
        validated = PredictionResponse.model_validate(payload)
        self.assertEqual(9, validated.estimated_source_execution_cycles)
        self.assertEqual(5, validated.instruction_cycle_ledger[0].total_cycles)
        self.assertIn("replaced deterministically", validated.warnings[-1])

    def test_structured_cfg_rejects_unknown_successor_and_unreachable_block(self) -> None:
        payload = structured_prediction()
        payload["predicted_functions"][0]["blocks"][0]["successors"] = ["missing"]
        with self.assertRaisesRegex(ValueError, "unknown successor"):
            PredictionResponse.model_validate(payload)
        payload = structured_prediction()
        payload["predicted_functions"][0]["blocks"].append({
            "block_id": "dead", "execution_count": 1, "successors": [],
            "instructions": [],
        })
        with self.assertRaisesRegex(ValueError, "unreachable executed basic block"):
            PredictionResponse.model_validate(payload)

    def test_zero_execution_infeasible_block_may_be_off_selected_path(self) -> None:
        payload = structured_prediction()
        payload["predicted_functions"][0]["blocks"].append({
            "block_id": "infeasible", "execution_count": 0, "successors": [],
            "instructions": [],
        })
        validated = PredictionResponse.model_validate(payload)
        self.assertEqual(0, validated.predicted_functions[0].blocks[1].execution_count)

    def test_structured_branch_counts_and_stack_balance_are_enforced(self) -> None:
        payload = structured_prediction()
        instruction = payload["predicted_functions"][0]["blocks"][0]["instructions"][0]
        instruction.update({
            "opcode": "bne", "instruction_class": "conditional_branch",
            "timing_profile_record": "conditional_branch_taken",
            "not_taken_timing_profile_record": "conditional_branch_not_taken",
            "taken_count": 1, "not_taken_count": 1,
        })
        with self.assertRaisesRegex(ValueError, "taken_count.*branch execution"):
            PredictionResponse.model_validate(payload)
        payload = structured_prediction()
        payload["predicted_functions"][0]["stack_allocation_bytes"] = 8
        with self.assertRaisesRegex(ValueError, "stack allocation/deallocation"):
            PredictionResponse.model_validate(payload)

    def test_structured_calls_require_callee_and_matching_execution_count(self) -> None:
        payload = structured_prediction()
        instruction = payload["predicted_functions"][0]["blocks"][0]["instructions"][0]
        instruction.update({
            "opcode": "bl", "instruction_class": "function_call",
            "timing_profile_record": "function_call_bl_with_refill",
            "callee": "Helper",
        })
        payload["predicted_functions"][0].update({
            "lr_saved": True, "valid_return_via": "POP_PC",
        })
        payload["predicted_functions"][0]["blocks"][0]["instructions"][1].update({
            "opcode": "pop", "operands": "{r7, pc}",
            "instruction_class": "push_or_pop_register_transfer",
            "timing_profile_record": "push_or_pop_register_transfer",
            "register_transfer_count": 2,
        })
        payload["instruction_cycle_ledger"][0].update({
            "instruction_class": "function_call_bl_with_refill",
            "cycles_each": 4, "total_cycles": 4,
        })
        payload["cycle_components"][0]["cycles"] = 4
        payload["estimated_source_execution_cycles"] = 4
        payload["estimated_source_execution_us"] = 4 / 48
        with self.assertRaisesRegex(ValueError, "no structured helper body"):
            PredictionResponse.model_validate(payload)

    def test_structured_ledger_is_recomputed_from_blocks(self) -> None:
        payload = structured_prediction()
        payload["instruction_cycle_ledger"][0]["dynamic_count"] = 2
        payload["instruction_cycle_ledger"][0]["total_cycles"] = 2
        payload["cycle_components"][0]["cycles"] = 6
        payload["estimated_source_execution_cycles"] = 6
        payload["estimated_source_execution_us"] = 6 / 48
        validated = PredictionResponse.model_validate(payload)
        self.assertEqual(5, validated.estimated_source_execution_cycles)
        self.assertEqual(1, validated.instruction_cycle_ledger[0].dynamic_count)
        self.assertIn("replaced deterministically", validated.warnings[-1])

    def test_holistic_source_only_estimate_requires_complete_o0_ledger(self) -> None:
        payload = prediction()
        payload["analysis_status"] = "PARTIAL"
        payload["cycle_components"] = [{
            "name": "holistic_build_profile_estimate",
            "cycles": 480,
            "evidence": "holistic",
        }]
        payload["estimated_source_execution_cycles"] = 480
        payload["estimated_source_execution_us"] = 10.0
        payload["unresolved"] = ["exact compiler output"]
        payload["warnings"] = ["engineering estimate"]
        with self.assertRaisesRegex(ValueError, "complete dynamic O0 cost ledger"):
            PredictionResponse.model_validate(payload)

        payload["source_analysis"].update({
            "dynamic_helper_calls": 2,
            "dynamic_nested_helper_calls": 1,
            "dynamic_divisions": 1,
            "dynamic_branch_evaluations": 8,
            "estimated_o0_stack_reads": 20,
            "estimated_o0_stack_writes": 12,
        })
        validated = PredictionResponse.model_validate(payload)
        self.assertEqual(20, validated.source_analysis.estimated_o0_stack_reads)

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
