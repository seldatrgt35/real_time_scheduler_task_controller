# Qwen assembly evidence

`gcc_o0_assembly_patterns.json` is the assembly-only evidence corpus used by
`ollama_staged_cycle_prototype`. It contains 30 general compiler patterns for
the frozen profile `ARM GCC 11.4, Cortex-M4, Thumb-2, -O0`.

The target under prediction is never compiled to create or retrieve these
records. The corpus was generated once from generic micro fixtures with the
same S32DS GCC 11.4 toolchain and is used as frozen static data. Generator
sources are deliberately not part of the runtime prototype. No C example body
is returned by the evidence retriever or included in Qwen prompts.

The official GCC 11.4 ARM testsuite is used as a coverage catalogue, not copied
into the model prompt. Its tests span incompatible architectures and
optimization levels, so importing them verbatim would mix Cortex-A, NEON, MVE,
and non-`-O0` evidence into the Cortex-M4 profile.
