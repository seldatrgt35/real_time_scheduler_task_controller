"""AST visitors that extract task-level facts from Clang cursors."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable

from clang.cindex import Cursor, CursorKind, TypeKind

from task_admission_framework.database.api_database import ApiDatabase
from task_admission_framework.model.task_profile import TaskProfile


def _available_cursor_kinds(*names: str) -> set[CursorKind]:
    return {
        cursor_kind
        for name in names
        if (cursor_kind := getattr(CursorKind, name, None)) is not None
    }


def _cursor_kind_name(cursor: Cursor) -> str:
    return getattr(cursor.kind, "name", str(cursor.kind))


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

    def __init__(self, api_database: ApiDatabase) -> None:
        self._api_database = api_database

    def visit(self, cursor: Cursor, profile: TaskProfile) -> None:
        if not self._is_call_cursor(cursor):
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

        if self._api_database.is_blocking(call_name):
            profile.blocking_calls.append(call_name)

    @classmethod
    def _is_call_cursor(cls, cursor: Cursor) -> bool:
        return (
            cursor.kind in cls._CALL_KINDS
            or _cursor_kind_name(cursor) in cls._CALL_KIND_NAMES
        )

    @staticmethod
    def _extract_call_name(cursor: Cursor) -> str | None:
        if cursor.spelling:
            return cursor.spelling
        if cursor.referenced and cursor.referenced.spelling:
            return cursor.referenced.spelling
        if cursor.displayname:
            return cursor.displayname

        for child in cursor.get_children():
            child_name = FunctionCallVisitor._extract_call_name(child)
            if child_name:
                return child_name

        return None


class DataUsageVisitor(AstVisitor):
    """Counts explicit pointer and floating-point operations."""

    _FLOAT_TYPES = {
        TypeKind.FLOAT,
        TypeKind.DOUBLE,
        TypeKind.LONGDOUBLE,
    }
    _ARITHMETIC_KINDS = {
        CursorKind.BINARY_OPERATOR,
        CursorKind.COMPOUND_ASSIGNMENT_OPERATOR,
        CursorKind.UNARY_OPERATOR,
    }

    def visit(self, cursor: Cursor, profile: TaskProfile) -> None:
        if cursor.kind == CursorKind.ARRAY_SUBSCRIPT_EXPR:
            profile.pointer_operations += 1
        elif cursor.kind == CursorKind.UNARY_OPERATOR and self._has_pointer_token(cursor):
            profile.pointer_operations += 1
        elif (
            cursor.kind == CursorKind.BINARY_OPERATOR
            and cursor.type.kind == TypeKind.POINTER
        ):
            profile.pointer_operations += 1
        elif cursor.kind == CursorKind.MEMBER_REF_EXPR and self._uses_arrow(cursor):
            profile.pointer_operations += 1

        if cursor.type.kind in self._FLOAT_TYPES:
            profile.floating_point_usage = True
            if cursor.kind in self._ARITHMETIC_KINDS:
                profile.floating_point_operations += 1

    @staticmethod
    def _has_pointer_token(cursor: Cursor) -> bool:
        tokens = {token.spelling for token in cursor.get_tokens()}
        return "*" in tokens or "&" in tokens

    @staticmethod
    def _uses_arrow(cursor: Cursor) -> bool:
        return any(token.spelling == "->" for token in cursor.get_tokens())


class CompositeVisitor(AstVisitor):
    """Delegates cursor processing to a list of focused visitors."""

    def __init__(self, visitors: Iterable[AstVisitor]) -> None:
        self._visitors = list(visitors)

    def visit(self, cursor: Cursor, profile: TaskProfile) -> None:
        for visitor in self._visitors:
            visitor.visit(cursor, profile)
