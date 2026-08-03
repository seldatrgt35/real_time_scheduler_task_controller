"""Pure token-based workload classification used by static analysis."""

from __future__ import annotations

import re


class WorkloadClassifier:
    """Classify bounded kernel tokens without user-supplied metadata."""

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
