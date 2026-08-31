from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


PROFILE_ID = "gcc-11.4-cortex-m4-thumb-o0-default-float-abi-v1"


def _function_body(source: str, function_name: str | None) -> str:
    if not function_name:
        return source
    match = re.search(rf"\b{re.escape(function_name)}\s*\([^;{{}}]*\)\s*\{{", source)
    if not match:
        return source
    start = source.find("{", match.start())
    depth = 0
    for index in range(start, len(source)):
        depth += source[index] == "{"
        depth -= source[index] == "}"
        if depth == 0:
            return source[start + 1:index]
    return source[start + 1:]


def _query_tags(source: str, function_name: str | None = None) -> set[str]:
    source = _function_body(source, function_name)
    tags: set[str] = set()
    if re.search(r"\b(for|while)\s*\(", source):
        tags.update(("loop", "bounded_loop"))
    if "volatile" in source:
        tags.add("volatile")
    if "[" in source and "]" in source:
        tags.add("array")
    if "*" in source:
        tags.add("pointer")
    if re.search(r"\bif\s*\(|\bswitch\s*\(", source):
        tags.update(("branch", "comparison"))
    if re.search(r"\b(?:u?int(?:8|16|32|64)_t|float|double|bool|char|short|long|int)\s+[A-Za-z_]\w*", source):
        tags.add("local")
    if re.search(r"(?<![=!<>])=(?!=)|\+=|-=|\^=|\|=|&=", source):
        tags.add("assignment")
    call_names = re.findall(r"\b([A-Za-z_]\w*)\s*\(", source)
    excluded = {"if", "for", "while", "switch", "sizeof"}
    calls = [name for name in call_names if name not in excluded]
    if calls:
        tags.add("helper_call")
    return tags


def retrieve_gcc_evidence(
    source: str, path: Path, *, function_name: str | None = None, limit: int = 5
) -> list[dict[str, Any]]:
    records = json.loads(path.read_text(encoding="utf-8"))
    query = _query_tags(source, function_name)
    weights = {"helper_call": 4, "nested_helper": 5, "loop": 4, "bounded_loop": 4,
               "volatile": 3, "array": 3, "pointer": 2, "branch": 3,
               "comparison": 2, "assignment": 1, "local": 1}
    ranked = []
    for record in records:
        if record.get("compiler_profile_id", PROFILE_ID) != PROFILE_ID:
            continue
        tags = set(record.get("tags", []))
        shared = query & tags
        overlap = sum(weights.get(tag, 1) for tag in shared)
        union = sum(weights.get(tag, 1) for tag in query | tags)
        if overlap:
            ranked.append((overlap / union, overlap, record["pattern"], record))
    ranked.sort(key=lambda item: (-item[0], -item[1], item[2]))
    return [item[3] for item in ranked[:limit]]
