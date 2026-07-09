"""C source parsing facade built on clang.cindex."""

from __future__ import annotations

from pathlib import Path

from clang.cindex import Index, TranslationUnit


class ClangAstParser:
    """Parses C source files into Clang translation units."""

    def __init__(self, clang_args: list[str] | None = None) -> None:
        self._clang_args = clang_args or self._default_clang_args()

    def parse(self, source_path: str | Path) -> TranslationUnit:
        path = Path(source_path)
        if not path.exists():
            raise FileNotFoundError(f"C source file not found: {path}")

        index = Index.create()
        return index.parse(
            str(path),
            args=self._clang_args,
            options=TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD,
        )

    @staticmethod
    def _default_clang_args() -> list[str]:
        return [
            "-x",
            "c",
            "-std=c11",
            "-D__STATIC_ANALYSIS__",
            "-D__S32K148__",
            "-DARM_MATH_CM4",
        ]
