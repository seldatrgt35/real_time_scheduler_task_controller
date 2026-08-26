# LLM source-only WCET blind experiment

Purpose: compare source-only LLM estimates, the frozen STAR framework estimate,
and an S32K148 board measurement without leaking either prediction or board
result into the LLM prompt.

Protocol:

1. Start a new ChatGPT conversation and paste `PROMPT_TR.md` unchanged.
2. Start a new Gemini conversation and paste the same prompt unchanged.
3. Do not tell either model the STAR estimate or any board result.
4. Save each JSON response before flashing the board.
5. Flash the existing nested-loop ELF and record the board maximum.
6. Fill `results_template.csv` and compare nominal error and WCET coverage.

Frozen STAR prediction before board execution:

- nominal: 33.7085767960 us
- WCET: 38.7648633154 us

Board ELF:

`artifacts/s32k148_nested_loop_wcet/star_s32k148_nested_loop_wcet.elf`
