"""Bound-aware O0 uint32 source-pattern extraction."""

from __future__ import annotations

from dataclasses import dataclass, field

from clang.cindex import Cursor, CursorKind, TypeKind

from task_admission_framework.analyzer.dynamic_operations import DynamicOperationAnalyzer


@dataclass(slots=True)
class ContextualIntegerInference:
    counts: dict[str, int] = field(default_factory=dict)
    verified: bool = True
    notes: list[str] = field(default_factory=list)

    def add(self, name: str, occurrences: int) -> None:
        if occurrences > 0:
            self.counts[name] = self.counts.get(name, 0) + occurrences


class ContextualIntegerAnalyzer(DynamicOperationAnalyzer):
    """Extract the board-validated uint32 patterns used by the O0 model."""

    _UNSIGNED_KINDS = {
        TypeKind.BOOL, TypeKind.CHAR_U, TypeKind.UCHAR, TypeKind.CHAR16,
        TypeKind.CHAR32, TypeKind.USHORT, TypeKind.UINT, TypeKind.ULONG,
        TypeKind.ULONGLONG,
    }
    _SIGNED_KINDS = {
        TypeKind.CHAR_S, TypeKind.SCHAR, TypeKind.SHORT, TypeKind.INT,
        TypeKind.LONG, TypeKind.LONGLONG,
    }

    def infer_contexts(
        self, root_function: Cursor, function_definitions: dict[str, Cursor]
    ) -> ContextualIntegerInference:
        result = ContextualIntegerInference()
        self._walk_context_function(
            root_function, 1, function_definitions, [], {}, set(), result
        )
        return result

    def _walk_context_function(
        self, function: Cursor, multiplier: int,
        definitions: dict[str, Cursor], call_stack: list[str],
        constants: dict[str, int], loop_indices: set[str],
        result: ContextualIntegerInference,
    ) -> None:
        if function.spelling in call_stack:
            result.verified = False
            result.notes.append(f"Recursive contextual count is unknown: {function.spelling}")
            return
        stack = [*call_stack, function.spelling]
        for child in function.get_children():
            self._walk_context_cursor(
                child, multiplier, definitions, stack, constants,
                loop_indices, result
            )

    def _walk_context_cursor(
        self, cursor: Cursor, multiplier: int,
        definitions: dict[str, Cursor], call_stack: list[str],
        constants: dict[str, int], loop_indices: set[str],
        result: ContextualIntegerInference,
    ) -> None:
        if cursor.kind == CursorKind.IF_STMT:
            result.add("branch_evaluation_u32", multiplier)
            # The board branch coefficient already includes condition evaluation
            # and the selected body. Do not sum mutually exclusive bodies or
            # double-count condition operators as separate work.
            return

        if cursor.kind in self._LOOP_KINDS:
            bound = self.extract_loop_bound(cursor, constants)
            if bound is None:
                result.verified = False
                result.notes.append(
                    f"Contextual integer loop at line {getattr(cursor.location, 'line', '?')} has no proven bound."
                )
                return
            children = list(cursor.get_children())
            new_indices = set(loop_indices)
            if cursor.kind == CursorKind.FOR_STMT and children:
                new_indices.update(self._declared_names(children[0]))
            result.add("loop_iterations", multiplier * bound)
            result.add("loop_invocations", multiplier)
            body = children[-1] if children else cursor
            compound_group = self._automotive_compound_loop_pattern(body)
            if compound_group is not None:
                result.add(compound_group, multiplier * bound)
                result.add(f"{compound_group}_invocations", multiplier)
                helper_calls = sum(
                    node.kind in self._CALL_KINDS
                    for node in self._descendants(body)
                )
                result.add(
                    "automotive_helper_call_u32",
                    multiplier * bound * helper_calls,
                )
                result.add("compound_group_loop_iterations", multiplier * bound)
                result.add("compound_group_loop_invocations", multiplier)
                return
            if self._is_dense_integer_control_loop(body):
                result.add("dense_integer_control_correction_u32", multiplier * bound)
            powertrain_group = self._powertrain_numeric_loop_pattern(body)
            if powertrain_group is not None:
                result.add(powertrain_group, multiplier * bound)
                result.add("powertrain_group_loop_iterations", multiplier * bound)
                result.add("powertrain_group_loop_invocations", multiplier)
                return
            communication_group = self._communication_loop_pattern(body)
            if communication_group is not None:
                result.add(communication_group, multiplier * bound)
                result.add("communication_group_loop_iterations", multiplier * bound)
                result.add("communication_group_loop_invocations", multiplier)
                return
            floating_group = self._floating_loop_pattern(body)
            if floating_group is not None:
                result.add(floating_group, multiplier * bound)
                result.add("floating_group_loop_iterations", multiplier * bound)
                result.add("floating_group_loop_invocations", multiplier)
                return
            fixed_group = self._fixed_point_loop_pattern(body)
            if fixed_group is not None:
                result.add(fixed_group, multiplier * bound)
                result.add("fixed_group_loop_iterations", multiplier * bound)
                result.add("fixed_group_loop_invocations", multiplier)
                return
            memory_group = self._memory_loop_pattern(body)
            if memory_group is not None:
                result.add(memory_group, multiplier * bound)
                result.add("memory_group_loop_iterations", multiplier * bound)
                result.add("memory_group_loop_invocations", multiplier)
                return
            composite = self._composite_loop_pattern(body)
            if composite is not None:
                result.add(composite, multiplier * bound)
                return
            self._count_loop_chains(body, multiplier * bound, new_indices, result)
            body_index = len(children) - 1
            for index, child in enumerate(children):
                child_multiplier = multiplier * bound if index == body_index else multiplier
                self._walk_context_cursor(
                    child, child_multiplier, definitions, call_stack,
                    constants, new_indices, result
                )
            return

        if cursor.kind in self._CALL_KINDS:
            name = self._extract_call_name(cursor)
            if name in definitions:
                callee = definitions[name]
                self._walk_context_function(
                    callee, multiplier, definitions, call_stack,
                    self._bind_constant_arguments(cursor, callee),
                    loop_indices, result
                )
            return

        if cursor.kind in self._BINARY_KINDS and self._is_uint32(cursor):
            operator = self._root_operator(cursor)
            if operator in self._ADD_SUB:
                operation = "add" if operator.startswith("+") else "subtract"
                context = self._operand_context(cursor, operator, loop_indices)
                result.add(f"{operation}_{context}_u32", multiplier)
            elif operator in self._MULTIPLY:
                result.add("multiply_local_u32", multiplier)
            elif operator in self._DIVIDE or operator in self._MODULO:
                operation = "divide" if operator in self._DIVIDE else "modulo"
                result.add(f"{operation}_{self._numerator_size(cursor)}_u32", multiplier)
            elif operator in {"&", "&="}:
                result.add("bitwise_and_u32", multiplier)
            elif operator in {"|", "|="}:
                result.add("bitwise_or_u32", multiplier)
            elif operator in {"^", "^="}:
                result.add("bitwise_xor_u32", multiplier)
            elif operator in {"<<", "<<="}:
                result.add("shift_left_u32", multiplier)
            elif operator in {">>", ">>="}:
                result.add("shift_right_u32", multiplier)

        for child in cursor.get_children():
            self._walk_context_cursor(
                child, multiplier, definitions, call_stack, constants,
                loop_indices, result
            )

    def _automotive_compound_loop_pattern(self, body: Cursor) -> str | None:
        """Recognize independently calibrated automotive loop compounds."""
        descendants = self._descendants(body)
        operators = [
            operator
            for node in descendants
            if node.kind in self._BINARY_KINDS
            if (operator := self._root_operator(node)) is not None
        ]
        kinds = set(operators)
        arrays = sum(
            node.kind == CursorKind.ARRAY_SUBSCRIPT_EXPR for node in descendants
        )
        conditionals = sum(node.kind == CursorKind.IF_STMT for node in descendants)
        loops = sum(node.kind in self._LOOP_KINDS for node in descendants)
        calls = {
            self._extract_call_name(node)
            for node in descendants if node.kind in self._CALL_KINDS
        }

        if loops and "^=" in kinds and "<<" in kinds and conditionals:
            return "automotive_can_crc_pack_u32"
        if arrays >= 3 and conditionals >= 3 and "|=" in kinds and "<<" in kinds:
            return "automotive_plausibility_debounce_u32"
        has_interpolation = (
            "StarInterpolateQ8" in calls
            or (arrays >= 2 and "*" in kinds and "/" in kinds)
        )
        if has_interpolation and conditionals and "<" in kinds:
            return "automotive_torque_map_limiter_i32"
        return None

    def _composite_loop_pattern(self, body: Cursor) -> str | None:
        """Recognize board-calibrated nested expressions as one codegen unit."""
        descendants = self._descendants(body)
        operators = [
            operator
            for node in descendants
            if node.kind in self._BINARY_KINDS
            if (operator := self._root_operator(node)) is not None
        ]
        kinds = set(operators)
        if any(node.kind == CursorKind.IF_STMT for node in descendants):
            return None
        if "<<" in kinds and ">>" in kinds and "|" in kinds:
            return "shift_rotate_u32"
        if "/" in kinds and "&" in kinds:
            return "divide_masked_index_u32"
        if "%" in kinds and "&" in kinds:
            return "modulo_masked_index_u32"
        if "*" in kinds and "&" in kinds:
            return "multiply_masked_index_u32"
        if "^" in kinds and "|" in kinds:
            return "bitwise_nested_u32"
        if operators.count("+") >= 2 and not kinds.intersection({"*", "/", "%"}):
            return "basic_add_expression_u32"
        return None

    def _powertrain_numeric_loop_pattern(self, body: Cursor) -> str | None:
        """Recognize the bounded signed Powertrain groups calibrated as units."""
        descendants = self._descendants(body)
        operators = {
            operator
            for node in descendants
            if node.kind in self._BINARY_KINDS
            if (operator := self._root_operator(node)) is not None
        }
        signed_nodes = [
            node for node in descendants
            if node.kind in self._BINARY_KINDS and self._is_int32(node)
        ]
        arrays = [
            node for node in descendants
            if node.kind == CursorKind.ARRAY_SUBSCRIPT_EXPR
        ]
        if not signed_nodes:
            return None
        has_int64 = any(self._canonical_size(node) == 8 for node in descendants)
        if len(arrays) >= 2 and has_int64 and "*" in operators and "/" in operators:
            return "powertrain_linear_interpolation_i32"
        conditionals = [node for node in descendants if node.kind == CursorKind.IF_STMT]
        if len(conditionals) >= 2:
            has_upper_bound = bool(operators.intersection({">", ">="}))
            has_lower_bound = bool(operators.intersection({"<", "<="}))
            if has_upper_bound and has_lower_bound:
                return "powertrain_saturation_clamp_i32"
        if arrays and operators.intersection({"&", "%"}):
            if not operators.intersection({"/", "<<", ">>"}):
                return "powertrain_lookup_1d_i32"
        if arrays and "*" in operators and "/" in operators:
            return "powertrain_signed_arithmetic_i32"
        return None

    def _is_dense_integer_control_loop(self, body: Cursor) -> bool:
        descendants = self._descendants(body)
        operators = {
            self._root_operator(node) for node in descendants
            if node.kind in self._BINARY_KINDS
        }
        return (
            any(node.kind == CursorKind.IF_STMT for node in descendants)
            and bool(operators.intersection(self._MULTIPLY))
            and bool(operators.intersection({"&", "&="}))
            and bool(operators.intersection({"|", "|="}))
            and bool(operators.intersection({"^", "^="}))
            and bool(operators.intersection({"<<", "<<="}))
            and bool(operators.intersection({">>", ">>="}))
        )

    def _communication_loop_pattern(self, body: Cursor) -> str | None:
        descendants = self._descendants(body)
        switches = [node for node in descendants if node.kind == CursorKind.SWITCH_STMT]
        if switches:
            case_count = sum(node.kind == CursorKind.CASE_STMT for node in descendants)
            return "switch_case_4_u32" if case_count <= 4 else None
        calls = [node for node in descendants if node.kind in self._CALL_KINDS]
        if calls:
            try:
                direct = all(call.referenced is not None and call.referenced.kind == CursorKind.FUNCTION_DECL for call in calls)
            except AttributeError:
                direct = False
            return "direct_function_call_u32" if direct else "indirect_function_call_u32"
        has_array = any(node.kind == CursorKind.ARRAY_SUBSCRIPT_EXPR for node in descendants)
        operators = {
            self._root_operator(node) for node in descendants
            if node.kind in self._BINARY_KINDS
        }
        if has_array and operators.intersection({"^", "^="}) and operators.intersection({"&", "&="}):
            return "checksum_processed_byte_u32"
        return None

    def _floating_loop_pattern(self, body: Cursor) -> str | None:
        descendants = self._descendants(body)
        if any(node.kind == CursorKind.ARRAY_SUBSCRIPT_EXPR for node in descendants):
            casts = [
                node for node in descendants
                if node.kind == CursorKind.CSTYLE_CAST_EXPR
            ]
            if any(self._canonical_size(node) == 4 for node in casts):
                return "int32_to_float32_u32"
        for node in descendants:
            if node.kind not in self._BINARY_KINDS:
                continue
            operator = self._root_operator(node)
            size = self._canonical_size(node)
            if size not in {4, 8} or not self._contains_float_operand(node):
                continue
            prefix = "float32" if size == 4 else "float64"
            if operator in self._ADD_SUB:
                return f"{prefix}_add_sub_u32"
            if operator in self._MULTIPLY:
                return f"{prefix}_multiply_u32"
            if operator in self._DIVIDE:
                return f"{prefix}_divide_u32"
        return None

    @staticmethod
    def _canonical_size(cursor: Cursor) -> int:
        try:
            return cursor.type.get_canonical().get_size()
        except (AttributeError, TypeError):
            return -1

    def _memory_loop_pattern(self, body: Cursor) -> str | None:
        statements = (
            list(body.get_children())
            if body.kind == CursorKind.COMPOUND_STMT
            else [body]
        )
        if len(statements) != 1:
            return None
        descendants = self._descendants(body)
        arrays = [node for node in descendants if node.kind == CursorKind.ARRAY_SUBSCRIPT_EXPR]
        if not arrays:
            return None
        assignments = [
            node for node in descendants
            if node.kind in self._BINARY_KINDS and self._root_operator(node) == "="
        ]
        if len(arrays) >= 2 and assignments:
            return "bulk_memory_copy_u32"
        if assignments and any(
            self._contains_kind(list(node.get_children())[0], CursorKind.ARRAY_SUBSCRIPT_EXPR)
            for node in assignments if list(node.get_children())
        ):
            return "bulk_memory_set_u32"
        if any(
            any(
                node.kind in self._BINARY_KINDS
                and self._root_operator(node) in {"*", "&"}
                for node in self._descendants(array)
            )
            for array in arrays
        ):
            return "random_indexed_memory_u32"
        return "sequential_memory_u32"

    def _fixed_point_loop_pattern(self, body: Cursor) -> str | None:
        tokens = [token.spelling for token in body.get_tokens()]
        token_set = set(tokens)
        numeric_tokens = {token.rstrip("uUlL") for token in tokens}
        if "15" in numeric_tokens and ">>" in token_set and "*" in token_set:
            return "q15_mac_u32" if "+=" in token_set else "q15_multiply_u32"
        if "1024" in numeric_tokens and "*=" in token_set:
            return "q31_multiply_u32"
        if "16" in numeric_tokens and "*" in token_set and "+=" in token_set:
            return "q31_mac_u32"
        return None

    def _count_loop_chains(
        self, body: Cursor, multiplier: int, loop_indices: set[str],
        result: ContextualIntegerInference,
    ) -> None:
        statements = list(body.get_children()) if body.kind == CursorKind.COMPOUND_STMT else [body]
        pending_index_adds = 0
        previous_was_multiply = False
        add_contexts: set[str] = set()
        bitwise_kinds: set[str] = set()
        for statement in statements:
            operation = self._primary_operation(statement, loop_indices)
            if operation is not None and operation.startswith("add_"):
                add_contexts.add(operation.removeprefix("add_"))
            if operation in {"bitwise_and", "bitwise_or", "bitwise_xor"}:
                bitwise_kinds.add(operation)
            if operation == "add_index":
                if previous_was_multiply:
                    result.add("multiply_before_index_u32", multiplier)
                pending_index_adds += 1
                previous_was_multiply = False
            elif operation == "multiply":
                result.add("index_before_multiply_u32", multiplier * pending_index_adds)
                pending_index_adds = 0
                previous_was_multiply = True
            else:
                previous_was_multiply = False
        if len(add_contexts) >= 3:
            result.add("mixed_add_context_u32", multiplier)
        if len(bitwise_kinds) >= 3:
            result.add("mixed_bitwise_context_u32", multiplier)

    def _primary_operation(self, cursor: Cursor, loop_indices: set[str]) -> str | None:
        if cursor.kind in self._BINARY_KINDS and self._is_uint32(cursor):
            operator = self._root_operator(cursor)
            if operator in self._ADD_SUB and operator.startswith("+"):
                context = self._operand_context(cursor, operator, loop_indices)
                return f"add_{context}"
            if operator in self._MULTIPLY:
                return "multiply"
            if operator in {"&", "&="}:
                return "bitwise_and"
            if operator in {"|", "|="}:
                return "bitwise_or"
            if operator in {"^", "^="}:
                return "bitwise_xor"
        for child in cursor.get_children():
            if (found := self._primary_operation(child, loop_indices)) is not None:
                return found
        return None

    def _operand_context(
        self, cursor: Cursor, operator: str, loop_indices: set[str]
    ) -> str:
        children = list(cursor.get_children())
        candidates = children if operator.startswith("+") else children[-1:]
        if any(self._contains_kind(child, CursorKind.ARRAY_SUBSCRIPT_EXPR) for child in candidates):
            return "memory"
        if any(self._evaluate_integer(child) is not None for child in candidates):
            return "constant"
        references = {
            node.spelling for child in candidates
            for node in self._descendants(child)
            if node.kind == CursorKind.DECL_REF_EXPR
        }
        return "index" if references & loop_indices else "local"

    def _numerator_size(self, cursor: Cursor) -> str:
        children = list(cursor.get_children())
        value = self._evaluate_integer(children[0]) if children else None
        return "small" if value is not None and 0 <= value <= 255 else "large"

    def _is_uint32(self, cursor: Cursor) -> bool:
        try:
            canonical = cursor.type.get_canonical()
            return canonical.kind in self._UNSIGNED_KINDS and canonical.get_size() == 4
        except (AttributeError, TypeError):
            return False

    def _is_int32(self, cursor: Cursor) -> bool:
        try:
            canonical = cursor.type.get_canonical()
            return canonical.kind in self._SIGNED_KINDS and canonical.get_size() == 4
        except (AttributeError, TypeError):
            return False

    def _declared_names(self, cursor: Cursor) -> set[str]:
        return {
            node.spelling for node in self._descendants(cursor)
            if node.kind == CursorKind.VAR_DECL and node.spelling
        }

    def _contains_kind(self, cursor: Cursor, kind: CursorKind) -> bool:
        return any(node.kind == kind for node in self._descendants(cursor))

    def _descendants(self, cursor: Cursor) -> list[Cursor]:
        output = [cursor]
        for child in cursor.get_children():
            output.extend(self._descendants(child))
        return output
