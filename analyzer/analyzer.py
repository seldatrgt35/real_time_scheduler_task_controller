"""High-level static analyzer for C task source files."""

from __future__ import annotations

from pathlib import Path

from clang.cindex import Cursor, CursorKind, TranslationUnit

from task_admission_framework.analyzer.ast_parser import ClangAstParser
from task_admission_framework.analyzer.visitors import (
    CompositeVisitor,
    ControlFlowVisitor,
    DataUsageVisitor,
    FunctionCallVisitor,
)
from task_admission_framework.database.api_database import ApiDatabase
from task_admission_framework.model.task_profile import TaskProfile
from task_admission_framework.utils.logger import get_logger


class StaticAnalyzer:
    """Coordinates parsing, call graph construction, and AST traversal."""

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
        self._traverse_function(root_function, profile, function_definitions, [])
        return profile

    def _traverse_function(
        self,
        function_cursor: Cursor,
        profile: TaskProfile,
        function_definitions: dict[str, Cursor],
        call_stack: list[str],
    ) -> None:
        function_name = function_cursor.spelling
        if function_name in call_stack:
            profile.recursion_detected = True
            return

        if function_name not in profile.reachable_functions:
            profile.reachable_functions.append(function_name)

        next_stack = [*call_stack, function_name]
        for child in function_cursor.get_children():
            self._traverse_cursor(child, profile, function_definitions, next_stack)

    def _traverse_cursor(
        self,
        cursor: Cursor,
        profile: TaskProfile,
        function_definitions: dict[str, Cursor],
        call_stack: list[str],
    ) -> None:
        self._visitor.visit(cursor, profile)

        if cursor.kind == CursorKind.CALL_EXPR:
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
                )

        for child in cursor.get_children():
            self._traverse_cursor(child, profile, function_definitions, call_stack)

    @staticmethod
    def _is_function_definition(cursor: Cursor) -> bool:
        return cursor.kind == CursorKind.FUNCTION_DECL and cursor.is_definition()

    def _collect_function_definitions(
        self,
        translation_unit: TranslationUnit,
    ) -> dict[str, Cursor]:
        return {
            cursor.spelling: cursor
            for cursor in translation_unit.cursor.get_children()
            if self._is_function_definition(cursor)
        }

    @staticmethod
    def _extract_call_name(cursor: Cursor) -> str | None:
        if cursor.spelling:
            return cursor.spelling
        if cursor.referenced and cursor.referenced.spelling:
            return cursor.referenced.spelling
        return cursor.displayname or None

    @staticmethod
    def _add_call_graph_edge(profile: TaskProfile, caller: str, callee: str) -> None:
        callees = profile.call_graph.setdefault(caller, [])
        if callee not in callees:
            callees.append(callee)

    def _log_diagnostics(self, translation_unit: TranslationUnit) -> None:
        for diagnostic in translation_unit.diagnostics:
            self._logger.warning("%s", diagnostic)
