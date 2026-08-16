"""Automatic bounded-work inference from Clang AST cursors."""

from __future__ import annotations

import ast
import operator
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

    def __init__(self, constant_definitions: dict[str, int] | None = None) -> None:
        self._constant_definitions = dict(constant_definitions or {})

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

        explicit_class = WorkloadClassifier.explicit_kernel_class(name)
        if explicit_class is not None:
            loop_bound = self._single_kernel_loop_bound(
                function_cursor,
                parameter_constants,
            )
            if loop_bound is None:
                result.verified = False
                result.notes.append(
                    f"Explicit kernel '{name}' has no single proven loop bound."
                )
                return
            result.add(explicit_class, multiplier * loop_bound)
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

    def _single_kernel_loop_bound(
        self,
        function_cursor: Cursor,
        parameter_constants: dict[str, int],
    ) -> int | None:
        """Return the sole loop bound of an explicitly named feature kernel."""

        loops: list[Cursor] = []

        def collect(cursor: Cursor) -> None:
            if cursor.kind in self._LOOP_KINDS:
                loops.append(cursor)
                return
            for child in cursor.get_children():
                collect(child)

        for child in function_cursor.get_children():
            collect(child)
        if len(loops) != 1:
            return None
        return self.extract_loop_bound(loops[0], parameter_constants)

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
                explicit_class = WorkloadClassifier.explicit_kernel_class(
                    call_name
                )
                if explicit_class is not None:
                    try:
                        arguments = list(cursor.get_arguments())
                    except AttributeError:
                        arguments = []
                    explicit_units = (
                        self._evaluate_integer(arguments[0])
                        if arguments
                        else None
                    )
                    if explicit_units is not None:
                        result.add(
                            explicit_class,
                            multiplier * explicit_units,
                        )
                        return
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
        constants = {**self._constant_definitions, **(parameter_constants or {})}
        start = self._constant_expression_after(initializer, "=", constants)
        comparator = next(
            (item for item in ("<=", "<", ">=", ">") if item in condition),
            None,
        )
        limit = (
            self._constant_expression_after(condition, comparator, constants)
            if comparator is not None else None
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

    @classmethod
    def _constant_expression_after(
        cls, tokens: list[str], marker: str | None, constants: dict[str, int]
    ) -> int | None:
        if marker is None or marker not in tokens:
            return None
        expression = tokens[tokens.index(marker) + 1 :]
        normalized: list[str] = []
        for token in expression:
            if token in constants:
                normalized.append(str(constants[token]))
            elif cls._INTEGER_LITERAL.fullmatch(token):
                normalized.append(token.rstrip("uUlL"))
            elif token in {"(", ")", "+", "-", "*", "/", "%", "<<", ">>"}:
                normalized.append("//" if token == "/" else token)
            else:
                return None
        try:
            return int(cls._evaluate_constant_ast(ast.parse("".join(normalized), mode="eval").body))
        except (SyntaxError, TypeError, ValueError, ZeroDivisionError):
            return None

    @classmethod
    def _evaluate_constant_tokens(
        cls, tokens: list[str], constants: dict[str, int]
    ) -> int | None:
        normalized: list[str] = []
        for token in tokens:
            if token in constants:
                normalized.append(str(constants[token]))
            elif cls._INTEGER_LITERAL.fullmatch(token):
                normalized.append(token.rstrip("uUlL"))
            elif token in {"(", ")", "+", "-", "*", "/", "%", "<<", ">>"}:
                normalized.append("//" if token == "/" else token)
            else:
                return None
        try:
            tree = ast.parse("".join(normalized), mode="eval")
            return int(cls._evaluate_constant_ast(tree.body))
        except (SyntaxError, TypeError, ValueError, ZeroDivisionError):
            return None

    @classmethod
    def _evaluate_constant_ast(cls, node: ast.AST) -> int:
        binary = {
            ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
            ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
            ast.LShift: operator.lshift, ast.RShift: operator.rshift,
        }
        unary = {ast.UAdd: operator.pos, ast.USub: operator.neg}
        if isinstance(node, ast.Constant) and isinstance(node.value, int):
            return int(node.value)
        if isinstance(node, ast.BinOp) and type(node.op) in binary:
            return binary[type(node.op)](
                cls._evaluate_constant_ast(node.left),
                cls._evaluate_constant_ast(node.right),
            )
        if isinstance(node, ast.UnaryOp) and type(node.op) in unary:
            return unary[type(node.op)](cls._evaluate_constant_ast(node.operand))
        raise ValueError("unsupported constant expression")

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
        token_arguments = self._call_argument_tokens(call_cursor)
        bindings: dict[str, int] = {}
        for index, (parameter, argument) in enumerate(zip(parameters, arguments)):
            value = self._evaluate_integer(argument)
            if value is None and index < len(token_arguments):
                value = self._evaluate_constant_tokens(
                    token_arguments[index], self._constant_definitions
                )
            if value is not None and parameter.spelling:
                bindings[parameter.spelling] = value
        return bindings

    @staticmethod
    def _call_argument_tokens(call_cursor: Cursor) -> list[list[str]]:
        """Return source-level call arguments, avoiding macro extent artifacts."""

        tokens = [token.spelling for token in call_cursor.get_tokens()]
        try:
            opening = tokens.index("(")
        except ValueError:
            return []
        groups: list[list[str]] = [[]]
        depth = 0
        for token in tokens[opening + 1 :]:
            if token == "(" :
                depth += 1
                groups[-1].append(token)
            elif token == ")":
                if depth == 0:
                    break
                depth -= 1
                groups[-1].append(token)
            elif token == "," and depth == 0:
                groups.append([])
            else:
                groups[-1].append(token)
        return groups if any(groups) else []

    def _evaluate_integer(self, cursor: Cursor) -> int | None:
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
            sizes = self._descendant_type_sizes(cursor)
            if sizes:
                return max(sizes)
        if len(tokens) == 1:
            return self._last_integer(tokens)
        return self._evaluate_constant_tokens(tokens, self._constant_definitions)

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
