"""AST visitors that extract task-level facts from Clang cursors."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable

from clang.cindex import Cursor, CursorKind, TypeKind

from task_admission_framework.database.api_database import ApiDatabase
from task_admission_framework.model.task_profile import TaskProfile


class AstVisitor(ABC):
    """Base visitor interface for Clang AST cursors."""

    @abstractmethod
    def visit(self, cursor: Cursor, profile: TaskProfile) -> None:
        """Process one cursor and update the task profile when relevant."""


class ControlFlowVisitor(AstVisitor):
    """Counts control-flow statements inside a function body."""

    def visit(self, cursor: Cursor, profile: TaskProfile) -> None:
        if cursor.kind == CursorKind.IF_STMT:
            profile.if_count += 1
        elif cursor.kind == CursorKind.FOR_STMT:
            profile.for_count += 1
        elif cursor.kind in {CursorKind.WHILE_STMT, CursorKind.DO_STMT}:
            profile.while_count += 1
        elif cursor.kind == CursorKind.SWITCH_STMT:
            profile.switch_count += 1
        elif cursor.kind == CursorKind.RETURN_STMT:
            profile.return_count += 1


class FunctionCallVisitor(AstVisitor):
    """Records function calls and maps known calls to API categories."""

    def __init__(self, api_database: ApiDatabase) -> None:
        self._api_database = api_database

    def visit(self, cursor: Cursor, profile: TaskProfile) -> None:
        if cursor.kind != CursorKind.CALL_EXPR:
            return

        call_name = self._extract_call_name(cursor)
        if not call_name:
            return

        profile.function_calls.append(call_name)

        if call_name == profile.task_name:
            profile.recursion_detected = True

        if self._api_database.is_tracked(call_name):
            profile.api_usage[call_name] = profile.api_usage.get(call_name, 0) + 1

        if self._api_database.is_dynamic_memory(call_name):
            profile.dynamic_memory = True

        if self._api_database.is_blocking(call_name) and call_name not in profile.blocking_calls:
            profile.blocking_calls.append(call_name)

    @staticmethod
    def _extract_call_name(cursor: Cursor) -> str | None:
        if cursor.spelling:
            return cursor.spelling
        if cursor.referenced and cursor.referenced.spelling:
            return cursor.referenced.spelling
        return cursor.displayname or None


class DataUsageVisitor(AstVisitor):
    """Detects pointer and floating-point usage."""

    _FLOAT_TYPES = {
        TypeKind.FLOAT,
        TypeKind.DOUBLE,
        TypeKind.LONGDOUBLE,
    }
    _POINTER_KINDS = {
        CursorKind.UNARY_OPERATOR,
        CursorKind.ARRAY_SUBSCRIPT_EXPR,
    }

    def visit(self, cursor: Cursor, profile: TaskProfile) -> None:
        if cursor.type.kind == TypeKind.POINTER:
            profile.pointer_operations += 1

        if cursor.kind in self._POINTER_KINDS and cursor.type.kind == TypeKind.POINTER:
            profile.pointer_operations += 1

        if cursor.type.kind in self._FLOAT_TYPES:
            profile.floating_point_usage = True


class CompositeVisitor(AstVisitor):
    """Delegates cursor processing to a list of focused visitors."""

    def __init__(self, visitors: Iterable[AstVisitor]) -> None:
        self._visitors = list(visitors)

    def visit(self, cursor: Cursor, profile: TaskProfile) -> None:
        for visitor in self._visitors:
            visitor.visit(cursor, profile)
