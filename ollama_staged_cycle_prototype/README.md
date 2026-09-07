# Experimental staged Ollama cycle predictor

This folder is isolated from the existing Gemini/Ollama predictor. It does not
modify its prompts, schemas, RAG index, result files, or CLI behavior.

The experiment uses:

1. one Qwen call for source path and dynamic call multiplicities;
2. one small Qwen call per reachable function for a per-invocation ledger;
3. deterministic Python call-graph composition and cycle arithmetic;
4. cross-pass validation before a result can be marked `SUPPORTED`.

It does not use board RAG, compiled ELF/disassembly, measured board time, or an
arbitrary correction multiplier. Like the Gemini `--no-rag` path, it does use
the checked-in GCC 11.4 `-O0` transformation evidence, hardware profile,
instruction timing profile, complete source preamble/defines, initialization
context and source-derived indexed-access obligations.

```bash
python -m ollama_staged_cycle_prototype.cli \
  --source experiments/gemini_branch_blind_v10/automotive_branch_v10_task.c \
  --function RedundantPedalFaultArbitration_Task5ms \
  --output ollama_staged_cycle_prototype/results/v10_qwen14b_staged.json
```

The output is accepted only when the structure pass and independently composed
per-function calls agree. Otherwise it is saved as `VALIDATION_REQUIRED`
without a cycle/time estimate. Each raw model response is retained beside the
result for diagnosis.
