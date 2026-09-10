from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from gemini_rag_cycle_prototype.gcc_evidence import PROFILE_ID


def _function_body(source: str, function_name: str | None) -> str:
    if not function_name:
        return source
    match = re.search(rf"\b{re.escape(function_name)}\s*\([^;{{}}]*\)\s*\{{", source)
    if not match:
        return source
    opening = source.find("{", match.start())
    depth = 0
    for index in range(opening, len(source)):
        depth += source[index] == "{"
        depth -= source[index] == "}"
        if depth == 0:
            return source[opening + 1:index]
    return source[opening + 1:]


def _query_tags(source: str, function_name: str | None) -> set[str]:
    body = _function_body(source, function_name)
    tags: set[str] = set()
    if re.search(r"\bfor\s*\(", body):
        tags.update(("loop", "bounded_loop"))
    if re.search(r"\bwhile\s*\(", body):
        tags.update(("loop", "while_loop"))
    if re.search(r"\bdo\b", body):
        tags.update(("loop", "do_while_loop"))
    if re.search(r"\bif\s*\(", body):
        tags.update(("branch", "comparison"))
        if len(re.findall(r"\bif\s*\(", body)) > 1:
            tags.update(("nested_branch", "two_conditions"))
    if re.search(r"\bswitch\s*\(", body):
        tags.update(("branch", "switch"))
    if "&&" in body:
        tags.update(("branch", "short_circuit", "logical_and"))
    if "||" in body:
        tags.update(("branch", "short_circuit", "logical_or"))
    if "volatile" in body:
        tags.add("volatile")
    if "[" in body and "]" in body:
        tags.update(("array", "indexed_address"))
    if "->" in body or re.search(r"\b[A-Za-z_]\w*\.[A-Za-z_]\w*", body):
        tags.add("struct")
    if "*" in body:
        tags.add("pointer")
    if re.search(r"<<|>>", body):
        tags.add("shift")
    if re.search(r"(?<![&|])[&|^~](?![&|])", body):
        tags.add("bitwise")
    if re.search(r"(?<![/])/(?![/])", body):
        tags.add("divide")
    if "%" in body:
        tags.add("remainder")
    if re.search(r"(?<![*/])\*(?![=/])", body):
        tags.add("multiply")
    for width in ("uint8", "int8", "uint16", "int16", "uint32", "int32", "uint64"):
        if re.search(rf"\b{width}_t\b", body):
            tags.add(width)
    calls = [
        name for name in re.findall(r"\b([A-Za-z_]\w*)\s*\(", body)
        if name not in {"if", "for", "while", "switch", "sizeof"}
    ]
    if calls:
        tags.add("helper_call")
    return tags


def retrieve_assembly_evidence(
    source: str,
    path: Path,
    *,
    function_name: str | None = None,
    limit: int = 8,
) -> list[dict[str, Any]]:
    records = json.loads(path.read_text(encoding="utf-8"))
    query = _query_tags(source, function_name)
    weights = {
        "helper_call": 6,
        "loop": 6,
        "bounded_loop": 5,
        "while_loop": 5,
        "do_while_loop": 5,
        "branch": 5,
        "nested_branch": 6,
        "short_circuit": 7,
        "logical_and": 5,
        "logical_or": 5,
        "switch": 7,
        "volatile": 5,
        "array": 4,
        "indexed_address": 5,
        "pointer": 3,
        "struct": 6,
        "shift": 4,
        "bitwise": 4,
        "multiply": 5,
        "divide": 7,
        "remainder": 7,
        "uint64": 7,
    }
    ranked: list[tuple[float, int, str, set[str], dict[str, Any]]] = []
    for record in records:
        if record.get("compiler_profile_id", PROFILE_ID) != PROFILE_ID:
            continue
        tags = set(record.get("tags", []))
        shared = query & tags
        if not shared:
            continue
        overlap = sum(weights.get(tag, 2) for tag in shared)
        noise = sum(weights.get(tag, 2) for tag in tags - query)
        score = overlap - (0.15 * noise)
        ranked.append((score, overlap, record["pattern"], tags, record))
    ranked.sort(key=lambda item: (-item[0], -item[1], item[2]))

    # Preserve coverage of distinct source obligations. Without this step,
    # several near-identical loop records can occupy every result slot while a
    # helper-call or volatile-access example is omitted.
    selected: list[tuple[float, int, str, set[str], dict[str, Any]]] = []
    anchor_groups = (
        {"helper_call"},
        {"loop", "bounded_loop", "while_loop", "do_while_loop"},
        {"branch", "nested_branch", "short_circuit", "switch"},
        {"array", "indexed_address", "pointer"},
        {"volatile"},
        {"struct"},
        {"divide", "remainder"},
        {"multiply"},
        {"shift", "bitwise"},
        {"uint64"},
    )
    for group in anchor_groups:
        active = query & group
        if not active:
            continue
        candidate = next(
            (item for item in ranked if item[3] & active and item not in selected),
            None,
        )
        if candidate is not None:
            selected.append(candidate)
        if len(selected) == limit:
            break

    while len(selected) < limit:
        candidates = [item for item in ranked if item not in selected]
        if not candidates:
            break
        covered = set().union(*(item[3] for item in selected)) if selected else set()
        candidate = max(
            candidates,
            key=lambda item: (
                item[0]
                - 0.6 * sum(weights.get(tag, 2) for tag in item[3] & covered),
                item[1],
                item[2],
            ),
        )
        selected.append(candidate)
    compact: list[dict[str, Any]] = []
    for _, _, _, _, record in selected:
        blocks = []
        for block in record.get("basic_blocks", []):
            blocks.append({
                "id": block["id"],
                "execution_formula": block.get("execution_formula", "source-dependent"),
                "assembly": [
                    " ".join(
                        part for part in (
                            instruction.get("opcode", ""),
                            instruction.get("operands", ""),
                        ) if part
                    )
                    for instruction in block.get("instructions", [])
                ],
            })
        compact.append({
            "pattern": record["pattern"],
            "tags": record.get("tags", []),
            "compiler_profile_id": record.get("compiler_profile_id", PROFILE_ID),
            "direct_callees": record.get("direct_callees", []),
            "basic_blocks": blocks,
        })
    return compact
