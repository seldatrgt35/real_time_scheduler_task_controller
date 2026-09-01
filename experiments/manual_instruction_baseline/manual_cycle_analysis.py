from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DISASSEMBLY = ROOT / "artifacts" / "s32k148_manual_instruction_baseline" / (
    "star_s32k148_manual_instruction_baseline.disasm.txt"
)
OUTPUT = DISASSEMBLY.with_name("manual_path_cycle_ledger.json")

TIMING = {
    "alu_move_compare_shift": 1,
    "sram_or_stack_load": 2,
    "sram_or_stack_store": 1,
    "push_or_pop_register_transfer": 1,
    "function_call_bl_with_refill": 4,
    "function_return_with_refill": 4,
    "conditional_branch_taken": 4,
    "conditional_branch_not_taken": 1,
    "unconditional_branch_with_refill": 4,
}


def addresses(first: int, last: int) -> list[int]:
    pattern = re.compile(
        r"^\s*([0-9a-f]+):\s+(?:[0-9a-f]{4,8}\s+)+[a-zA-Z]"
    )
    result = []
    for line in DISASSEMBLY.read_text(encoding="utf-8-sig").splitlines():
        match = pattern.match(line)
        if match:
            address = int(match.group(1), 16)
            if first <= address <= last:
                result.append(address)
    return result


def parse() -> dict[int, tuple[str, str]]:
    result = {}
    pattern = re.compile(
        r"^\s*([0-9a-f]+):\s+(?:[0-9a-f]{4,8}\s+)+([a-zA-Z][\w.]*)\s*(.*?)\s*$"
    )
    for line in DISASSEMBLY.read_text(encoding="utf-8-sig").splitlines():
        match = pattern.match(line)
        if match:
            result[int(match.group(1), 16)] = (
                match.group(2).lower(), match.group(3)
            )
    return result


def classify(opcode: str, operands: str, branch_taken: bool | None) -> tuple[str, int]:
    op = opcode.split(".")[0]
    if op.startswith("ldr"):
        return "sram_or_stack_load", 1
    if op.startswith("str"):
        return "sram_or_stack_store", 1
    if op in {"push", "pop"}:
        registers = re.search(r"\{([^}]+)\}", operands)
        count = len(registers.group(1).split(",")) if registers else 1
        return "push_or_pop_register_transfer", count
    if op in {"bl", "blx"}:
        return "function_call_bl_with_refill", 1
    if op == "bx":
        return "function_return_with_refill", 1
    if op == "b":
        return "unconditional_branch_with_refill", 1
    if op.startswith("b"):
        return (
            "conditional_branch_taken" if branch_taken
            else "conditional_branch_not_taken",
            1,
        )
    return "alu_move_compare_shift", 1


def append_path(
    trace: list[tuple[int, bool | None]], selected: list[int],
    branch_outcomes: dict[int, bool] | None = None,
) -> None:
    outcomes = branch_outcomes or {}
    trace.extend((address, outcomes.get(address)) for address in selected)


def build_trace() -> list[tuple[int, bool | None]]:
    trace: list[tuple[int, bool | None]] = []

    clamp_common_a = addresses(0x410, 0x42C)
    clamp_common_b = addresses(0x432, 0x438)
    clamp_end = addresses(0x43E, 0x448)
    for _ in range(3):
        append_path(trace, clamp_common_a, {0x42C: True})
        append_path(trace, clamp_common_b, {0x438: True})
        append_path(trace, clamp_end)
    append_path(trace, clamp_common_a, {0x42C: True})
    append_path(trace, clamp_common_b, {0x438: False})
    append_path(trace, addresses(0x43A, 0x43C))
    append_path(trace, clamp_end)

    rate_path = (
        addresses(0x44A, 0x462)
        + addresses(0x464, 0x472)
        + [0x47E, 0x480, 0x482]
        + addresses(0x4A2, 0x4AC)
    )
    for _ in range(4):
        append_path(trace, rate_path, {0x462: False, 0x472: True})

    debounce_start = addresses(0x4AE, 0x4C6)
    debounce_end = addresses(0x4E2, 0x4EC)
    append_path(trace, debounce_start, {0x4C6: True})
    append_path(trace, [0x4D6, 0x4D8, 0x4DA], {0x4DA: True})
    append_path(trace, debounce_end)
    append_path(trace, debounce_start, {0x4C6: True})
    append_path(trace, addresses(0x4D6, 0x4E0), {0x4DA: False})
    append_path(trace, debounce_end)
    for _ in range(2):
        append_path(trace, debounce_start, {0x4C6: False})
        append_path(trace, addresses(0x4C8, 0x4D4), {0x4CC: False})
        append_path(trace, debounce_end)

    append_path(trace, addresses(0x5A4, 0x5B2))
    task_common = addresses(0x5B4, 0x5F4)
    task_tail = addresses(0x5FC, 0x63C)
    task_test = addresses(0x63E, 0x642)
    append_path(trace, task_test, {0x642: True})
    for channel in range(4):
        append_path(trace, task_common, {0x5F4: channel < 2})
        if channel < 2:
            append_path(trace, [0x5FA])
        else:
            append_path(trace, [0x5F6, 0x5F8])
        append_path(trace, task_tail)
        append_path(trace, task_test, {0x642: channel < 3})
    append_path(trace, addresses(0x644, 0x650))
    return trace


def main() -> int:
    instructions = parse()
    counts: Counter[str] = Counter()
    trace = build_trace()
    missing = [hex(address) for address, _ in trace if address not in instructions]
    if missing:
        raise ValueError(f"Trace contains addresses absent from disassembly: {missing}")
    for address, taken in trace:
        opcode, operands = instructions[address]
        family, units = classify(opcode, operands, taken)
        counts[family] += units
    rows = [
        {
            "instruction_class": family,
            "dynamic_count": count,
            "cycles_each": TIMING[family],
            "total_cycles": count * TIMING[family],
        }
        for family, count in counts.items()
    ]
    total = sum(row["total_cycles"] for row in rows)
    result = {
        "task": "ThrottleActuatorMonitor_Task5ms",
        "compiler_profile": "ARM GCC 11.4 -O0 explicit no-transform flags",
        "clock_hz": 48_000_000,
        "dynamic_instruction_events": len(trace),
        "ledger": rows,
        "manual_core_cycles": total,
        "manual_core_us": total / 48.0,
        "scope": (
            "Core instruction timing ledger for the initialized feasible path; "
            "exact S32K148 PFlash fetch effects are not included."
        ),
    }
    OUTPUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
