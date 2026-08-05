"""Bound-aware primitive operation inference from Clang AST cursors."""

from __future__ import annotations

from dataclasses import dataclass, field

from clang.cindex import Cursor, CursorKind, TypeKind

from task_admission_framework.analyzer.dynamic_work import DynamicWorkAnalyzer
from task_admission_framework.analyzer.workload_classifier import WorkloadClassifier


@dataclass(slots=True)
class DynamicOperationInference:
    """Primitive operations weighted by statically proven execution counts."""

    counts: dict[str, int] = field(default_factory=dict)
    verified: bool = True
    notes: list[str] = field(default_factory=list)

    def add(self, name: str, occurrences: int) -> None:
        if occurrences > 0:
            self.counts[name] = self.counts.get(name, 0) + occurrences


class DynamicOperationAnalyzer(DynamicWorkAnalyzer):
    """Infer a compact set of CPU-relevant operations.

    Loop initializers execute once, conditions execute bound + 1 times, update
    expressions and bodies execute bound times. For an ``if`` statement, the
    condition is counted once and alternative bodies are merged as a
    conservative single path. Both mutually exclusive bodies are never summed
    as though they execute in the same invocation.
    """

    _BINARY_KINDS = {
        CursorKind.BINARY_OPERATOR,
        CursorKind.COMPOUND_ASSIGNMENT_OPERATOR,
    }
    _COMPARISONS = {"<", "<=", ">", ">=", "==", "!="}
    _ADD_SUB = {"+", "-", "+=", "-="}
    _MULTIPLY = {"*", "*="}
    _DIVIDE = {"/", "/="}
    _MODULO = {"%", "%="}
    _DIVIDE_MODULO = _DIVIDE | _MODULO
    _BITWISE = {"&", "|", "^", "&=", "|=", "^="}
    _SHIFT = {"<<", ">>", "<<=", ">>="}
    _OPERATORS = (
        _COMPARISONS
        | _ADD_SUB
        | _MULTIPLY
        | _DIVIDE_MODULO
        | _BITWISE
        | _SHIFT
        | {"="}
    )
    _FLOAT_TYPES = {
        TypeKind.FLOAT,
        TypeKind.DOUBLE,
        TypeKind.LONGDOUBLE,
    }
    _INTEGER_TYPES = {
        TypeKind.BOOL,
        TypeKind.CHAR_U,
        TypeKind.UCHAR,
        TypeKind.CHAR16,
        TypeKind.CHAR32,
        TypeKind.USHORT,
        TypeKind.UINT,
        TypeKind.ULONG,
        TypeKind.ULONGLONG,
        TypeKind.CHAR_S,
        TypeKind.SCHAR,
        TypeKind.WCHAR,
        TypeKind.SHORT,
        TypeKind.INT,
        TypeKind.LONG,
        TypeKind.LONGLONG,
    }
    # These board-calibrated operations are composite kernels: their measured
    # per-unit costs already include the primitive control/bitwise instructions
    # inside the loop body. Counting those primitives again would inflate the
    # estimate (for example, GPIO read XOR accumulation and alternating writes).
    _COMPOSITE_LOOP_WORKLOADS = {
        # The board coefficient for each of these classes was measured for the
        # complete loop kernel.  Its loop-control and primitive instructions
        # therefore must not be charged again as separate operations.
        "branch_evaluation",
        "bitwise_logic",
        "shift_rotate",
        "random_indexed_memory_access",
        "bulk_memory_copy_bytes",
        "bulk_memory_set_bytes",
        "sequential_memory_access",
        "q15_multiply",
        "q15_mac",
        "q31_multiply",
        "q31_mac",
        "fixed_point_saturation",
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
        "checksum_processed_bytes",
        "volatile_read",
        "volatile_write",
        "mmio_read",
        "mmio_write",
        "gpio_read",
        "gpio_write",
    }

    def infer(
        self,
        root_function: Cursor,
        function_definitions: dict[str, Cursor],
    ) -> DynamicOperationInference:
        result = DynamicOperationInference()
        self._walk_operation_function(
            root_function,
            multiplier=1,
            function_definitions=function_definitions,
            call_stack=[],
            parameter_constants={},
            result=result,
        )
        return result

    def _walk_operation_function(
        self,
        function_cursor: Cursor,
        *,
        multiplier: int,
        function_definitions: dict[str, Cursor],
        call_stack: list[str],
        parameter_constants: dict[str, int],
        result: DynamicOperationInference,
    ) -> None:
        name = function_cursor.spelling
        if name in call_stack:
            result.verified = False
            result.notes.append(f"Recursive operation count is unknown: {name}")
            return
        # Exact calibrated kernels are already charged once by DynamicWorkAnalyzer.
        # Their implementation-level arithmetic, branches and bit operations are
        # part of that measured kernel cost and must not be charged a second time.
        if WorkloadClassifier.explicit_kernel_class(name) is not None:
            return
        next_stack = [*call_stack, name]
        for child in function_cursor.get_children():
            self._walk_operation_cursor(
                child,
                multiplier=multiplier,
                function_definitions=function_definitions,
                call_stack=next_stack,
                parameter_constants=parameter_constants,
                result=result,
            )

    def _walk_operation_cursor(
        self,
        cursor: Cursor,
        *,
        multiplier: int,
        function_definitions: dict[str, Cursor],
        call_stack: list[str],
        parameter_constants: dict[str, int],
        result: DynamicOperationInference,
    ) -> None:
        if cursor.kind in self._LOOP_KINDS:
            bound = self.extract_loop_bound(cursor, parameter_constants)
            if bound is None:
                result.verified = False
                line = getattr(cursor.location, "line", 0)
                result.notes.append(
                    f"Loop at line {line or '?'} has no statically proven bound."
                )
                return
            if self.classify_cursor(cursor) in self._COMPOSITE_LOOP_WORKLOADS:
                return
            children = list(cursor.get_children())
            if cursor.kind == CursorKind.FOR_STMT and len(children) >= 4:
                self._walk_operation_cursor(
                    children[0],
                    multiplier=multiplier,
                    function_definitions=function_definitions,
                    call_stack=call_stack,
                    parameter_constants=parameter_constants,
                    result=result,
                )
                self._walk_operation_cursor(
                    children[1],
                    multiplier=multiplier * (bound + 1),
                    function_definitions=function_definitions,
                    call_stack=call_stack,
                    parameter_constants=parameter_constants,
                    result=result,
                )
                self._walk_operation_cursor(
                    children[2],
                    multiplier=multiplier * bound,
                    function_definitions=function_definitions,
                    call_stack=call_stack,
                    parameter_constants=parameter_constants,
                    result=result,
                )
                for child in children[3:]:
                    self._walk_operation_cursor(
                        child,
                        multiplier=multiplier * bound,
                        function_definitions=function_definitions,
                        call_stack=call_stack,
                        parameter_constants=parameter_constants,
                        result=result,
                    )
            else:
                for child in children:
                    self._walk_operation_cursor(
                        child,
                        multiplier=multiplier * bound,
                        function_definitions=function_definitions,
                        call_stack=call_stack,
                        parameter_constants=parameter_constants,
                        result=result,
                    )
            return

        if cursor.kind in self._CALL_KINDS:
            result.add("function_call", multiplier)
            call_name = self._extract_call_name(cursor)
            if call_name in function_definitions:
                callee = function_definitions[call_name]
                self._walk_operation_function(
                    callee,
                    multiplier=multiplier,
                    function_definitions=function_definitions,
                    call_stack=call_stack,
                    parameter_constants=self._bind_constant_arguments(
                        cursor,
                        callee,
                    ),
                    result=result,
                )
            return

        if cursor.kind == CursorKind.IF_STMT:
            self._walk_if_statement(
                cursor,
                multiplier=multiplier,
                function_definitions=function_definitions,
                call_stack=call_stack,
                parameter_constants=parameter_constants,
                result=result,
            )
            return
        if cursor.kind == CursorKind.SWITCH_STMT:
            result.add("switch_evaluation", multiplier)
        elif cursor.kind == CursorKind.ARRAY_SUBSCRIPT_EXPR:
            result.add("array_access", multiplier)
        elif cursor.kind == CursorKind.UNARY_OPERATOR:
            tokens = {token.spelling for token in cursor.get_tokens()}
            if "++" in tokens or "--" in tokens:
                result.add("integer_add_sub", multiplier)
            if "*" in tokens:
                result.add("pointer_dereference", multiplier)
        elif cursor.kind == CursorKind.CSTYLE_CAST_EXPR:
            self._count_numeric_conversion(cursor, multiplier, result)
        elif cursor.kind in self._BINARY_KINDS:
            self._count_binary_operation(cursor, multiplier, result)

        for child in cursor.get_children():
            self._walk_operation_cursor(
                child,
                multiplier=multiplier,
                function_definitions=function_definitions,
                call_stack=call_stack,
                parameter_constants=parameter_constants,
                result=result,
            )

    def _walk_if_statement(
        self,
        cursor: Cursor,
        *,
        multiplier: int,
        function_definitions: dict[str, Cursor],
        call_stack: list[str],
        parameter_constants: dict[str, int],
        result: DynamicOperationInference,
    ) -> None:
        """Count the condition and one conservative alternative path."""

        children = list(cursor.get_children())
        result.add("branch_evaluation", multiplier)
        if not children:
            return

        self._walk_operation_cursor(
            children[0],
            multiplier=multiplier,
            function_definitions=function_definitions,
            call_stack=call_stack,
            parameter_constants=parameter_constants,
            result=result,
        )

        alternatives: list[DynamicOperationInference] = []
        for branch in children[1:]:
            branch_result = DynamicOperationInference()
            self._walk_operation_cursor(
                branch,
                multiplier=multiplier,
                function_definitions=function_definitions,
                call_stack=call_stack,
                parameter_constants=parameter_constants,
                result=branch_result,
            )
            alternatives.append(branch_result)
        if len(alternatives) == 1:
            alternatives.append(DynamicOperationInference())
        if not alternatives:
            return

        all_names = {
            name
            for alternative in alternatives
            for name in alternative.counts
        }
        for name in all_names:
            result.add(
                name,
                max(
                    alternative.counts.get(name, 0)
                    for alternative in alternatives
                ),
            )
        result.verified = result.verified and all(
            alternative.verified for alternative in alternatives
        )
        for alternative in alternatives:
            result.notes.extend(alternative.notes)

    def _count_binary_operation(
        self,
        cursor: Cursor,
        multiplier: int,
        result: DynamicOperationInference,
    ) -> None:
        operator = self._root_operator(cursor)
        if operator is None or operator == "=":
            return
        uses_float = self._contains_float_operand(cursor)
        if operator in self._COMPARISONS:
            result.add(
                "floating_compare" if uses_float else "integer_compare",
                multiplier,
            )
        elif operator in self._ADD_SUB:
            result.add(
                "floating_add_sub" if uses_float else "integer_add_sub",
                multiplier,
            )
        elif operator in self._MULTIPLY:
            if uses_float:
                result.add("floating_multiply", multiplier)
            else:
                suffix = (
                    "constant"
                    if self._has_constant_operand(
                        cursor,
                        operator,
                        allow_constant_left=True,
                    )
                    else "variable"
                )
                result.add(f"integer_multiply_{suffix}", multiplier)
        elif operator in self._DIVIDE_MODULO:
            if uses_float:
                result.add("floating_divide", multiplier)
            else:
                suffix = (
                    "constant"
                    if self._has_constant_operand(
                        cursor,
                        operator,
                        allow_constant_left=False,
                    )
                    else "variable"
                )
                operation = "divide" if operator in self._DIVIDE else "modulo"
                result.add(f"integer_{operation}_{suffix}", multiplier)
        elif operator in self._BITWISE:
            result.add("bitwise_logic", multiplier)
        elif operator in self._SHIFT:
            result.add("shift_rotate", multiplier)

    def _count_numeric_conversion(
        self,
        cursor: Cursor,
        multiplier: int,
        result: DynamicOperationInference,
    ) -> None:
        children = list(cursor.get_children())
        if not children:
            return
        source = self._canonical_kind(children[0])
        target = self._canonical_kind(cursor)
        if (source in self._FLOAT_TYPES and target in self._INTEGER_TYPES) or (
            source in self._INTEGER_TYPES and target in self._FLOAT_TYPES
        ):
            result.add("numeric_conversion", multiplier)

    def _root_operator(self, cursor: Cursor) -> str | None:
        child_extents: list[tuple[int, int]] = []
        for child in cursor.get_children():
            try:
                child_extents.append(
                    (child.extent.start.offset, child.extent.end.offset)
                )
            except (AttributeError, TypeError):
                continue
        for token in cursor.get_tokens():
            if token.spelling not in self._OPERATORS:
                continue
            try:
                offset = token.location.offset
            except AttributeError:
                continue
            if not any(start <= offset < end for start, end in child_extents):
                return token.spelling
        return None

    def _contains_float_operand(self, cursor: Cursor) -> bool:
        return any(
            self._canonical_kind(child) in self._FLOAT_TYPES
            or self._contains_float_operand(child)
            for child in cursor.get_children()
        )

    def _has_constant_operand(
        self,
        cursor: Cursor,
        operator: str,
        *,
        allow_constant_left: bool,
    ) -> bool:
        children = list(cursor.get_children())
        candidates = children if allow_constant_left else children[-1:]
        if any(self._evaluate_integer(child) is not None for child in candidates):
            return True

        tokens = [token.spelling for token in cursor.get_tokens()]
        try:
            operator_index = tokens.index(operator)
        except ValueError:
            return False
        return self._last_integer(tokens[operator_index + 1 :]) is not None

    @staticmethod
    def _canonical_kind(cursor: Cursor) -> TypeKind:
        try:
            return cursor.type.get_canonical().kind
        except AttributeError:
            return cursor.type.kind
