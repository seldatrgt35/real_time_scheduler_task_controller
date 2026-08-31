from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).with_name("gcc_o0_pattern_fixture.c")
OUTPUT = Path(__file__).with_name("gcc_o0_patterns.json")
FLAGS = [
    "-mcpu=cortex-m4", "-mthumb", "-O0", "-fno-inline",
    "-ffunction-sections", "-fdata-sections", "-c",
]
PROFILE_ID = "gcc-11.4-cortex-m4-thumb-o0-default-float-abi-v1"

PATTERNS = {
    "PatternLeafIncrement": ("local_integer_assignment", ["local", "assignment", "leaf"]),
    "PatternSingleArgumentCall": ("single_argument_function_call", ["helper_call", "one_argument", "call_boundary"]),
    "PatternThreeArgumentHelper": ("three_argument_leaf_helper", ["helper", "three_arguments", "leaf", "arithmetic"]),
    "PatternThreeArgumentCall": ("three_argument_function_call", ["helper_call", "three_arguments", "call_boundary"]),
    "PatternBoundedLoop": ("bounded_array_loop", ["loop", "bounded_loop", "array", "pointer"]),
    "PatternConditionalBranch": ("conditional_branch", ["branch", "comparison", "assignment"]),
    "PatternVolatileReadWrite": ("volatile_pointer_read_write", ["volatile", "pointer", "assignment"]),
    "PatternNestedHelperCall": ("nested_helper_call", ["helper_call", "nested_helper", "call_boundary"]),
}


def _tool(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    base = Path(r"C:\NXP")
    matches = sorted(base.glob(f"S32DS.*/S32DS/build_tools/gcc_v11.4/**/bin/{name}.exe"))
    if not matches:
        raise FileNotFoundError(f"{name} not found in PATH or S32DS GCC 11.4")
    return str(matches[-1])


def _run(*args: str) -> str:
    return subprocess.run(args, check=True, text=True, capture_output=True).stdout


def _classify(opcode: str, operands: str) -> dict:
    op = opcode.lower()
    item: dict = {"opcode": op, "operands": operands}
    if op.startswith("ldr"):
        item["instruction_class"] = "sram_or_stack_load"
        item["memory_kind"] = "stack" if re.search(r"\[(?:r7|sp)\b", operands) else ("literal_pool" if "[pc" in operands else "source_or_pointer")
    elif op.startswith("str"):
        item["instruction_class"] = "sram_or_stack_store"
        item["memory_kind"] = "stack" if re.search(r"\[(?:r7|sp)\b", operands) else "source_or_pointer"
    elif op in {"push", "pop"}:
        item["instruction_class"] = "push_or_pop_register_transfer"
        regs = re.search(r"\{([^}]+)\}", operands)
        item["register_transfer_count"] = len(regs.group(1).split(",")) if regs else 0
        if op == "pop" and regs and "pc" in regs.group(1).lower():
            item["also_function_return"] = True
    elif op in {"bl", "blx"}:
        item["instruction_class"] = "function_call"
    elif op == "bx" and operands.strip() == "lr":
        item["instruction_class"] = "function_return"
    elif op == "b" or op.startswith("b."):
        item["instruction_class"] = "unconditional_branch"
    elif op.startswith("b"):
        item["instruction_class"] = "conditional_branch"
    elif op.startswith("mul"):
        item["instruction_class"] = "multiply"
    elif op.startswith(("sdiv", "udiv")):
        item["instruction_class"] = "divide"
    else:
        item["instruction_class"] = "alu_or_compare"
    return item


def _parse(disassembly: str) -> dict[str, list[dict]]:
    functions: dict[str, list[dict]] = {}
    current: list[dict] | None = None
    last: dict | None = None
    for line in disassembly.splitlines():
        header = re.match(r"^([0-9a-f]+) <([^>]+)>:$", line.strip())
        if header:
            current = functions.setdefault(header.group(2), [])
            last = None
            continue
        if current is None:
            continue
        insn = re.match(r"^\s*([0-9a-f]+):\s+(?:[0-9a-f]{4,8}\s+)+([a-zA-Z][\w.]*)\s*(.*?)\s*$", line)
        if insn:
            last = {"address": int(insn.group(1), 16), **_classify(insn.group(2), insn.group(3))}
            current.append(last)
            continue
        reloc = re.match(r"^\s*[0-9a-f]+:\s+(R_ARM_[A-Z0-9_]+)\s+(\S+)", line)
        if reloc and last is not None:
            symbol = reloc.group(2).split("+")[0]
            last.update({"relocation": reloc.group(1), "relocation_symbol": symbol})
            if last["instruction_class"] == "function_call":
                last.update({"callee": symbol, "operands": symbol})
    return functions


def _is_terminal(insn: dict) -> bool:
    return insn["instruction_class"] == "function_return" or bool(insn.get("also_function_return"))


def _blocks(name: str, instructions: list[dict]) -> tuple[list[dict], list[dict]]:
    terminal = max((i for i, x in enumerate(instructions) if _is_terminal(x)), default=len(instructions) - 1)
    executed, padding = instructions[: terminal + 1], instructions[terminal + 1 :]
    addresses = {x["address"] for x in executed}
    leaders = {executed[0]["address"]} if executed else set()
    for index, insn in enumerate(executed):
        if insn["instruction_class"] in {"conditional_branch", "unconditional_branch"}:
            target = re.search(r"\b([0-9a-f]+)\s*<", insn["operands"])
            if target and int(target.group(1), 16) in addresses:
                leaders.add(int(target.group(1), 16))
            if index + 1 < len(executed):
                leaders.add(executed[index + 1]["address"])
    blocks, block = [], None
    for insn in executed:
        if insn["address"] in leaders:
            block = {"id": f"block_{len(blocks)}", "execution_formula": "1", "instructions": []}
            blocks.append(block)
        clean = {k: v for k, v in insn.items() if k != "address"}
        block["instructions"].append(clean)
    if name == "PatternBoundedLoop" and len(blocks) >= 4:
        formulas = ["1", "N", "N+1", "1"]
        for block, formula in zip(blocks, formulas):
            block["execution_formula"] = formula
        for block in blocks:
            for insn in block["instructions"]:
                if insn["instruction_class"] == "conditional_branch":
                    insn["taken_executions"] = "N"
                    insn["not_taken_executions"] = "1"
        blocks[0]["loop_parameter"] = {"name": "N", "fixture_value": 8}
    clean_padding = []
    for instruction in padding:
        clean = {k: v for k, v in instruction.items() if k != "address"}
        clean.update({"role": "alignment_or_literal_padding", "executed_on_normal_path": False})
        clean_padding.append(clean)
    return blocks, clean_padding


def main() -> int:
    gcc, objdump = _tool("arm-none-eabi-gcc"), _tool("arm-none-eabi-objdump")
    with tempfile.TemporaryDirectory() as temp:
        obj = Path(temp) / "patterns.o"
        subprocess.run([gcc, *FLAGS, str(FIXTURE), "-o", str(obj)], check=True)
        parsed = _parse(_run(objdump, "-dr", str(obj)))
    toolchain = {
        "gcc_version": _run(gcc, "--version").splitlines()[0],
        "gcc_full_version": _run(gcc, "-dumpfullversion").strip(),
        "target": _run(gcc, "-dumpmachine").strip(),
        "objdump_version": _run(objdump, "--version").splitlines()[0],
    }
    records = []
    for function, (pattern, tags) in PATTERNS.items():
        blocks, padding = _blocks(function, parsed[function])
        calls = [i.get("callee") for b in blocks for i in b["instructions"] if i.get("callee")]
        chain = [function, *calls]
        if function == "PatternNestedHelperCall":
            chain.append("PatternLeafIncrement")
        records.append({
            "record_type": "gcc_o0_transformation", "pattern": pattern,
            "function": function, "tags": tags, "compiler_profile_id": PROFILE_ID,
            "toolchain": toolchain, "compile_flags": FLAGS,
            "assembly_scope": "function_body_only", "callee_bodies_included": False,
            "direct_callee": calls[0] if len(calls) == 1 else None,
            "direct_callees": calls, "callee_chain": chain,
            "dynamic_call_depth": 2 if function == "PatternNestedHelperCall" else (1 if calls else 0),
            "basic_blocks": blocks, "non_executed_padding": padding,
            "source_file": str(FIXTURE.relative_to(ROOT)).replace("\\", "/"),
        })
    OUTPUT.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    print(OUTPUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
