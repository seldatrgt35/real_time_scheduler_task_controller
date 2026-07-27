"""Automatic bounded-work inference from Clang AST cursors."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from clang.cindex import Cursor, CursorKind, TypeKind
from task_admission_framework.analyzer.workload_classifier import WorkloadClassifier


def _available_cursor_kinds(*names: str) -> set[CursorKind]:
    return {
        cursor_kind
        for name in names
        if (cursor_kind := getattr(CursorKind, name, None)) is not None
    }


@dataclass(slots=True)
class DynamicWorkInference:
    """Conservative dynamic kernel-invocation counts inferred from source."""

    counts: dict[str, int] = field(default_factory=dict)
    verified: bool = True
    notes: list[str] = field(default_factory=list)

    def add(self, workload_class: str, occurrences: int) -> None:
        if occurrences <= 0:
            return
        self.counts[workload_class] = (
            self.counts.get(workload_class, 0) + occurrences
        )


class DynamicWorkAnalyzer:
    """Infer bounded leaf-loop and helper-call executions for one task.

    A work unit is one execution of a leaf loop body or leaf helper function.
    Sequential bounded loops are added; nested loop bounds are multiplied.
    Unknown loop bounds make the timing estimate unverified.
    """

    _LOOP_KINDS = {
        CursorKind.FOR_STMT,
        CursorKind.WHILE_STMT,
        CursorKind.DO_STMT,
    }
    _CALL_KINDS = _available_cursor_kinds(
        "CALL_EXPR",
        "CXX_MEMBER_CALL_EXPR",
        "CXX_OPERATOR_CALL_EXPR",
        "CXX_CONSTRUCT_EXPR",
    )
    _FLOAT_TYPES = {
        TypeKind.FLOAT,
        TypeKind.DOUBLE,
        TypeKind.LONGDOUBLE,
    }
    _INTEGER_LITERAL = re.compile(
        r"(?<![A-Za-z_])(?:0[xX][0-9A-Fa-f]+|\d+)[uUlL]*"
    )

    def infer(
        self,
        root_function: Cursor,
        function_definitions: dict[str, Cursor],
    ) -> DynamicWorkInference:
        result = DynamicWorkInference()
        self._walk_function(
            root_function,
            multiplier=1,
            function_definitions=function_definitions,
            call_stack=[],
            parameter_constants={},
            result=result,
        )
        if not result.counts and result.verified:
            result.add(self.classify_cursor(root_function), 1)
        return result

    def _walk_function(
        self,
        function_cursor: Cursor,
        *,
        multiplier: int,
        function_definitions: dict[str, Cursor],
        call_stack: list[str],
        parameter_constants: dict[str, int],
        result: DynamicWorkInference,
    ) -> None:
        name = function_cursor.spelling
        if name in call_stack:
            result.verified = False
            result.notes.append(f"Recursive call bound is unknown: {name}")
            return

        children = list(function_cursor.get_children())
        if not self._contains_dynamic_node(children, function_definitions):
            result.add(self.classify_cursor(function_cursor), multiplier)
            return

        next_stack = [*call_stack, name]
        for child in children:
            self._walk_cursor(
                child,
                multiplier=multiplier,
                function_definitions=function_definitions,
                call_stack=next_stack,
                parameter_constants=parameter_constants,
                result=result,
            )

    def _walk_cursor(
        self,
        cursor: Cursor,
        *,
        multiplier: int,
        function_definitions: dict[str, Cursor],
        call_stack: list[str],
        parameter_constants: dict[str, int],
        result: DynamicWorkInference,
    ) -> None:
        if cursor.kind in self._LOOP_KINDS:
            bound = self.extract_loop_bound(cursor, parameter_constants)
            if bound is None:
                result.verified = False
                location = getattr(cursor.location, "line", 0)
                result.notes.append(
                    f"Loop at line {location or '?'} has no statically proven bound."
                )
                return

            children = list(cursor.get_children())
            nested_multiplier = multiplier * bound
            if not self._contains_dynamic_node(children, function_definitions):
                result.add(self.classify_cursor(cursor), nested_multiplier)
                return
            for child in children:
                self._walk_cursor(
                    child,
                    multiplier=nested_multiplier,
                    function_definitions=function_definitions,
                    call_stack=call_stack,
                    parameter_constants=parameter_constants,
                    result=result,
                )
            return

        if cursor.kind in self._CALL_KINDS:
            call_name = self._extract_call_name(cursor)
            if call_name in function_definitions:
                callee = function_definitions[call_name]
                self._walk_function(
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
            else:
                result.add(self.classify_cursor(cursor), multiplier)
            return

        for child in cursor.get_children():
            self._walk_cursor(
                child,
                multiplier=multiplier,
                function_definitions=function_definitions,
                call_stack=call_stack,
                parameter_constants=parameter_constants,
                result=result,
            )

    def _contains_dynamic_node(
        self,
        cursors: list[Cursor],
        function_definitions: dict[str, Cursor],
    ) -> bool:
        for cursor in cursors:
            if cursor.kind in self._LOOP_KINDS:
                return True
            if cursor.kind in self._CALL_KINDS:
                return True
            if self._contains_dynamic_node(
                list(cursor.get_children()),
                function_definitions,
            ):
                return True
        return False

    def extract_loop_bound(
        self,
        cursor: Cursor,
        parameter_constants: dict[str, int] | None = None,
    ) -> int | None:
        """Extract a conservative constant bound from a canonical for loop."""

        if cursor.kind != CursorKind.FOR_STMT:
            return None

        tokens = [token.spelling for token in cursor.get_tokens()]
        try:
            first_semicolon = tokens.index(";")
            second_semicolon = tokens.index(";", first_semicolon + 1)
        except ValueError:
            return None

        initializer = tokens[:first_semicolon]
        condition = tokens[first_semicolon + 1 : second_semicolon]
        start = self._last_integer(initializer)
        limit = self._last_integer(condition)
        if limit is None:
            constants = parameter_constants or {}
            limit = next(
                (constants[token] for token in condition if token in constants),
                None,
            )
        if start is None:
            start = 0
        if limit is None:
            return None

        if "<=" in condition:
            return max(0, limit - start + 1)
        if "<" in condition:
            return max(0, limit - start)
        if ">=" in condition:
            return max(0, start - limit + 1)
        if ">" in condition:
            return max(0, start - limit)
        return None

    def _bind_constant_arguments(
        self,
        call_cursor: Cursor,
        callee_cursor: Cursor,
    ) -> dict[str, int]:
        try:
            arguments = list(call_cursor.get_arguments())
        except AttributeError:
            arguments = []
        parameters = list(callee_cursor.get_arguments())
        bindings: dict[str, int] = {}
        for parameter, argument in zip(parameters, arguments):
            value = self._evaluate_integer(argument)
            if value is not None and parameter.spelling:
                bindings[parameter.spelling] = value
        return bindings

    @classmethod
    def _evaluate_integer(cls, cursor: Cursor) -> int | None:
        evaluate = getattr(cursor, "evaluate", None)
        if callable(evaluate):
            try:
                result = evaluate()
                if result is not None:
                    return int(result.as_int())
            except (AttributeError, TypeError, ValueError):
                pass

        tokens = [token.spelling for token in cursor.get_tokens()]
        if "sizeof" in tokens:
            sizes = cls._descendant_type_sizes(cursor)
            if sizes:
                return max(sizes)
        if len(tokens) == 1:
            return cls._last_integer(tokens)
        return None

    @classmethod
    def _descendant_type_sizes(cls, cursor: Cursor) -> list[int]:
        sizes: list[int] = []
        for child in cursor.get_children():
            try:
                size = int(child.type.get_size())
            except (AttributeError, TypeError, ValueError):
                size = -1
            if size > 0:
                sizes.append(size)
            sizes.extend(cls._descendant_type_sizes(child))
        return sizes

    @classmethod
    def _last_integer(cls, tokens: list[str]) -> int | None:
        for token in reversed(tokens):
            if cls._INTEGER_LITERAL.fullmatch(token):
                return int(token.rstrip("uUlL"), 0)
        return None

    def classify_cursor(self, cursor: Cursor) -> str:
        tokens = [token.spelling for token in cursor.get_tokens()]
        return self.classify_tokens(tokens, self._contains_float_type(cursor))

    @classmethod
    def classify_tokens(
        cls,
        tokens: list[str],
        contains_float_type: bool = False,
    ) -> str:
        return WorkloadClassifier.classify(tokens, contains_float_type)

    def _contains_float_type(self, cursor: Cursor) -> bool:
        if cursor.type.kind in self._FLOAT_TYPES:
            return True
        return any(self._contains_float_type(child) for child in cursor.get_children())

    @staticmethod
    def _extract_call_name(cursor: Cursor) -> str | None:
        if cursor.spelling:
            return cursor.spelling
        if cursor.referenced and cursor.referenced.spelling:
            return cursor.referenced.spelling
        if cursor.displayname:
            return cursor.displayname
        for child in cursor.get_children():
            if name := DynamicWorkAnalyzer._extract_call_name(child):
                return name
        return None
