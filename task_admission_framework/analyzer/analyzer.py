"""High-level static analyzer for C/C++ task source files."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from clang.cindex import Cursor, CursorKind, TranslationUnit

from task_admission_framework.analyzer.ast_parser import ClangAstParser
from task_admission_framework.analyzer.dynamic_work import DynamicWorkAnalyzer
from task_admission_framework.analyzer.contextual_integer import ContextualIntegerAnalyzer
from task_admission_framework.analyzer.dynamic_operations import (
    DynamicOperationAnalyzer,
)
from task_admission_framework.analyzer.visitors import (
    CompositeVisitor,
    ControlFlowVisitor,
    DataUsageVisitor,
    FunctionCallVisitor,
)
from task_admission_framework.database.api_database import ApiDatabase
from task_admission_framework.model.task_profile import TaskProfile
from task_admission_framework.utils.logger import get_logger


def _available_cursor_kinds(*names: str) -> set[CursorKind]:
    return {
        cursor_kind
        for name in names
        if (cursor_kind := getattr(CursorKind, name, None)) is not None
    }


def _cursor_kind_name(cursor: Cursor) -> str:
    return getattr(cursor.kind, "name", str(cursor.kind))


class StaticAnalyzer:
    """Coordinates parsing, call graph construction, and AST traversal.

    Each reachable function body is traversed once per root analysis. Static
    call sites are still counted per occurrence, but a repeatedly called
    helper's branches, loops, and data operations are not duplicated. This
    keeps structural complexity separate from dynamic execution frequency.
    Recursion cycles are cut off to avoid infinite traversal.
    """

    _CALL_KIND_NAMES = {
        "CALL_EXPR",
        "CXX_MEMBER_CALL_EXPR",
        "CXX_OPERATOR_CALL_EXPR",
        "CXX_CONSTRUCT_EXPR",
    }
    _CALL_KINDS = _available_cursor_kinds(
        "CALL_EXPR",
        "CXX_MEMBER_CALL_EXPR",
        "CXX_OPERATOR_CALL_EXPR",
        "CXX_CONSTRUCT_EXPR",
    )
    _TOKEN_CALL_EXCLUDES = {
        "if",
        "for",
        "while",
        "switch",
        "return",
        "sizeof",
        "static_cast",
        "reinterpret_cast",
        "const_cast",
        "dynamic_cast",
    }

    def __init__(
        self,
        parser: ClangAstParser | None = None,
        api_database: ApiDatabase | None = None,
    ) -> None:
        self._parser = parser or ClangAstParser()
        self._api_database = api_database or ApiDatabase()
        self._visitor = CompositeVisitor(
            [
                ControlFlowVisitor(),
                FunctionCallVisitor(self._api_database),
                DataUsageVisitor(),
            ]
        )
        self._logger = get_logger(self.__class__.__name__)

    def analyze_file(self, source_path: str | Path) -> list[TaskProfile]:
        translation_unit = self._parser.parse(source_path)
        self._log_diagnostics(translation_unit)
        function_definitions = self._collect_function_definitions(translation_unit)

        profiles: list[TaskProfile] = []
        for function_cursor in function_definitions.values():
            profiles.append(self._analyze_task(function_cursor, function_definitions))

        return profiles

    def _analyze_task(
        self,
        root_function: Cursor,
        function_definitions: dict[str, Cursor],
    ) -> TaskProfile:
        profile = TaskProfile(
            task_name=root_function.spelling,
            api_usage=self._api_database.empty_usage(),
        )
        self._dynamic_work_analyzer = DynamicWorkAnalyzer()
        self._traverse_function(
            root_function,
            profile,
            function_definitions,
            [],
            set(),
        )
        self._augment_function_calls_from_tokens(root_function, profile)
        dynamic_work = self._dynamic_work_analyzer.infer(
            root_function,
            function_definitions,
        )
        dynamic_operations = DynamicOperationAnalyzer().infer(
            root_function,
            function_definitions,
        )
        profile.inferred_workload_counts = dict(dynamic_work.counts)
        profile.inferred_operation_counts = dict(dynamic_operations.counts)
        profile.catalog_operation_counts = dict(dynamic_operations.catalog_counts)
        contextual_integer = ContextualIntegerAnalyzer().infer_contexts(
            root_function, function_definitions
        )
        profile.contextual_integer_counts = dict(contextual_integer.counts)
        profile.dynamic_bound_verified = (
            dynamic_work.verified and dynamic_operations.verified
            and contextual_integer.verified
        )
        profile.dynamic_bound_notes = list(
            dict.fromkeys([
                *dynamic_work.notes, *dynamic_operations.notes,
                *contextual_integer.notes,
            ])
        )
        return profile

    def _traverse_function(
        self,
        function_cursor: Cursor,
        profile: TaskProfile,
        function_definitions: dict[str, Cursor],
        call_stack: list[str],
        traversed_functions: set[str],
    ) -> None:
        function_name = function_cursor.spelling
        if function_name in call_stack:
            profile.recursion_detected = True
            return

        if function_name in traversed_functions:
            return
        traversed_functions.add(function_name)

        if function_name not in profile.reachable_functions:
            profile.reachable_functions.append(function_name)

        next_stack = [*call_stack, function_name]
        for child in function_cursor.get_children():
            self._traverse_cursor(
                child,
                profile,
                function_definitions,
                next_stack,
                traversed_functions,
            )

    def _traverse_cursor(
        self,
        cursor: Cursor,
        profile: TaskProfile,
        function_definitions: dict[str, Cursor],
        call_stack: list[str],
        traversed_functions: set[str],
    ) -> None:
        self._visitor.visit(cursor, profile)

        if self._is_call_cursor(cursor):
            call_name = self._extract_call_name(cursor)
            caller_name = call_stack[-1]
            if call_name:
                self._add_call_graph_edge(profile, caller_name, call_name)

            if call_name in function_definitions:
                self._traverse_function(
                    function_definitions[call_name],
                    profile,
                    function_definitions,
                    call_stack,
                    traversed_functions,
                )

        for child in cursor.get_children():
            self._traverse_cursor(
                child,
                profile,
                function_definitions,
                call_stack,
                traversed_functions,
            )

    @staticmethod
    def _is_function_definition(cursor: Cursor) -> bool:
        return cursor.kind in {
            CursorKind.FUNCTION_DECL,
            CursorKind.CXX_METHOD,
        } and cursor.is_definition()

    @classmethod
    def _is_call_cursor(cls, cursor: Cursor) -> bool:
        return (
            cursor.kind in cls._CALL_KINDS
            or _cursor_kind_name(cursor) in cls._CALL_KIND_NAMES
        )

    def _collect_function_definitions(
        self,
        translation_unit: TranslationUnit,
    ) -> dict[str, Cursor]:
        function_definitions: dict[str, Cursor] = {}
        self._collect_function_definitions_from_cursor(
            translation_unit.cursor,
            function_definitions,
        )
        return function_definitions

    def _collect_function_definitions_from_cursor(
        self,
        cursor: Cursor,
        function_definitions: dict[str, Cursor],
    ) -> None:
        if self._is_function_definition(cursor):
            function_definitions[cursor.spelling] = cursor

        for child in cursor.get_children():
            self._collect_function_definitions_from_cursor(child, function_definitions)

    @staticmethod
    def _extract_call_name(cursor: Cursor) -> str | None:
        if cursor.spelling:
            return cursor.spelling
        if cursor.referenced and cursor.referenced.spelling:
            return cursor.referenced.spelling
        if cursor.displayname:
            return cursor.displayname

        for child in cursor.get_children():
            child_name = StaticAnalyzer._extract_call_name(child)
            if child_name:
                return child_name

        return None

    @staticmethod
    def _add_call_graph_edge(profile: TaskProfile, caller: str, callee: str) -> None:
        callees = profile.call_graph.setdefault(caller, [])
        if callee not in callees:
            callees.append(callee)

    def _augment_function_calls_from_tokens(
        self,
        function_cursor: Cursor,
        profile: TaskProfile,
    ) -> None:
        """Recover C++ calls that libclang exposes poorly in incomplete ASTs.

        Some C++ translation units with missing project or standard-library
        includes still expose control-flow AST nodes but miss member-call nodes.
        This token pass only supplements missing call occurrences; it does not
        replace AST traversal.
        """

        fallback_calls = self._extract_token_call_names(function_cursor, profile.task_name)
        if not fallback_calls:
            return

        existing_counts = Counter(profile.function_calls)
        fallback_counts = Counter(fallback_calls)

        for call_name, fallback_count in fallback_counts.items():
            missing_count = fallback_count - existing_counts.get(call_name, 0)
            for _ in range(max(0, missing_count)):
                self._record_fallback_call(profile, call_name)

    def _extract_token_call_names(
        self,
        function_cursor: Cursor,
        task_name: str,
    ) -> list[str]:
        spellings = [token.spelling for token in function_cursor.get_tokens()]
        call_names: list[str] = []

        for index, spelling in enumerate(spellings[:-1]):
            if spellings[index + 1] != "(":
                continue

            if not self._is_token_call_name(spelling, task_name):
                continue

            call_names.append(spelling)

        return call_names

    def _is_token_call_name(self, spelling: str, task_name: str) -> bool:
        if spelling == task_name or spelling in self._TOKEN_CALL_EXCLUDES:
            return False
        if not spelling:
            return False
        return spelling[0].isalpha() or spelling[0] == "_"

    def _record_fallback_call(self, profile: TaskProfile, call_name: str) -> None:
        profile.function_calls.append(call_name)
        self._add_call_graph_edge(profile, profile.task_name, call_name)

        if self._api_database.is_tracked(call_name):
            profile.api_usage[call_name] = profile.api_usage.get(call_name, 0) + 1

        if self._api_database.is_dynamic_memory(call_name):
            profile.dynamic_memory = True

        if self._api_database.is_blocking(call_name):
            profile.blocking_calls.append(call_name)

    def _log_diagnostics(self, translation_unit: TranslationUnit) -> None:
        for diagnostic in translation_unit.diagnostics:
            self._logger.warning("%s", diagnostic)
