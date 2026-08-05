"""Pure token-based workload classification used by static analysis."""

from __future__ import annotations

import re


class WorkloadClassifier:
    """Classify bounded kernel tokens without user-supplied metadata."""

    EXPLICIT_KERNEL_MARKERS = (
        "basic_integer_add_sub", "integer_multiply_variable",
        "integer_divide_variable", "integer_modulo_variable",
        "branch_evaluation", "bitwise_logic", "shift_rotate",
        "sequential_memory_access", "random_indexed_memory_access",
        "bulk_memory_copy_bytes", "bulk_memory_set_bytes",
        "float32_add_sub", "float32_multiply", "float32_divide",
        "float64_add_sub", "float64_multiply", "float64_divide",
        "int32_to_float32", "float32_to_int32", "int32_to_float64",
        "float64_to_int32", "q15_multiply", "q15_mac",
        "q31_multiply", "q31_mac", "fixed_point_saturation",
        "sqrtf_call", "fabsf_call", "sinf_call", "cosf_call",
        "checksum_processed_bytes", "direct_function_call",
        "indirect_function_call", "switch_case_4", "switch_case_8",
        "switch_case_16", "volatile_read", "volatile_write",
        "mmio_read", "mmio_write", "gpio_read", "gpio_write",
    )

    @classmethod
    def explicit_kernel_class(cls, function_name: str) -> str | None:
        """Return an exact calibrated kernel name, never a substring guess."""

        normalized = function_name.strip().lower()
        return normalized if normalized in cls.EXPLICIT_KERNEL_MARKERS else None

    _FLOAT_LITERAL = re.compile(
        r"(?<![A-Za-z_])(?:\d+\.\d*|\.\d+|\d+[eE][+-]?\d+)[fFlL]?"
    )

    @classmethod
    def classify(
        cls,
        tokens: list[str],
        contains_float_type: bool = False,
    ) -> str:
        lowered = " ".join(tokens).lower()
        calibrated_floating_markers = (
            "float32_add_sub",
            "float32_multiply",
            "float32_divide",
            "float64_add_sub",
            "float64_multiply",
            "float64_divide",
            "int32_to_float32",
            "float32_to_int32",
            "int32_to_float64",
            "float64_to_int32",
        )
        for marker in calibrated_floating_markers:
            if marker in lowered:
                return marker

        calibrated_feature_markers = (
            "q15_multiply",
            "q15_mac",
            "q31_multiply",
            "q31_mac",
            "fixed_point_saturation",
            "sqrtf_call",
            "fabsf_call",
            "sinf_call",
            "cosf_call",
            "checksum_processed_bytes",
            "indirect_function_call",
            "direct_function_call",
            "switch_case_4",
            "switch_case_8",
            "switch_case_16",
            "volatile_read",
            "volatile_write",
            "mmio_read",
            "mmio_write",
            "gpio_read",
            "gpio_write",
        )
        for marker in calibrated_feature_markers:
            if marker in lowered:
                return marker

        math_call_names = {
            "sqrtf": "sqrtf_call",
            "fabsf": "fabsf_call",
            "sinf": "sinf_call",
            "cosf": "cosf_call",
        }
        for function_name, workload_class in math_call_names.items():
            if re.search(rf"\b{function_name}\b", lowered):
                return workload_class

        if (
            contains_float_type
            or any(cls._FLOAT_LITERAL.fullmatch(token) for token in tokens)
            or any(word in lowered for word in ("float", "double", "iir", "fir"))
        ):
            return "floating_point_iir"

        if "branch_evaluation" in lowered:
            return "branch_evaluation"

        if "bitwise_logic" in lowered:
            return "bitwise_logic"

        if "shift_rotate" in lowered:
            return "shift_rotate"

        if "random_indexed_memory" in lowered:
            return "random_indexed_memory_access"

        if "bulk_memory_copy" in lowered or "memcpy" in lowered:
            return "bulk_memory_copy_bytes"

        if "bulk_memory_set" in lowered or "memset" in lowered:
            return "bulk_memory_set_bytes"

        if any(
            word in lowered
            for word in (
                "sequential_memory",
                "source_buffer",
                "destination_buffer",
                "memory_copy",
                "buffer_copy",
            )
        ):
            return "sequential_memory_access"

        if "integer_modulo_variable" in lowered:
            return "integer_modulo_variable"

        if "integer_divide_variable" in lowered:
            return "integer_divide_variable"

        if "integer_multiply_variable" in lowered:
            return "integer_multiply_variable"

        if "basic_integer_add_sub" in lowered:
            return "basic_integer_add_sub"

        if any(
            word in lowered
            for word in ("can", "checksum", "crc", "payload", "frame_id")
        ) or any(token in tokens for token in ("^", "^=")):
            return "can_checksum"

        if (
            any(word in lowered for word in ("fixed", "q15", "q31"))
            or (("*" in tokens or "/" in tokens) and any(
                token in tokens for token in ("<<", ">>")
            ))
        ):
            return "fixed_point_filter"

        return "integer_control"
