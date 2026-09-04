# Gemini source-level execution-time prototype

Independent source-only prototype for:

```text
C source -> Gemini prediction -> one conservative execution-time estimate
```

The active workflow uses leakage-filtered board-measurement retrieval by default.
Use `--no-rag` only for the controlled source-only comparison. It does not compile the query,
inspect ELF/assembly, call the existing STAR execution estimator, or perform
scheduler analysis. Gemini produces `estimated_source_execution_cycles` and
`estimated_source_execution_us` from explicitly priced cycle components.
Unknown compiler/PFlash components remain `null` and are excluded from the
point-estimate sum. Python validates and records the values without replacing
or recalculating them.

Retrieval embeds only the requested task body rather than the whole
multi-function source file, helper bodies, macros, or initialization context.
Helpers contribute to structural reranking; macros, helper source, and
initialization are attached only after a reference is selected for the Gemini
prompt. Candidates must pass both embedding and source-structure gates.
The structure score includes loop nesting, branch/helper/array counts, assignment
and operator intensity, data types, and memory-access shape.
The default structural acceptance threshold is `0.75` and can be changed with
`--minimum-structural-similarity` for controlled experiments.
Ranking combines both scores, and at most one result is selected from each
source-file family. If no record clears both gates, Gemini receives no
measurement reference and must return a source-only PARTIAL result instead of
inventing hardware cost.

Validated board feedback is stored in
`tools/learning_feedback_board_results.csv`. After a new board result is added,
run `--rebuild-index` to embed it. A feedback task is no longer a blind holdout
after promotion to this dataset.

All records in the retrieval index contain measured board timing paired with C
source. The index includes the existing measured datasets and subsequently
validated `learning_feedback` records. Prior Gemini predictions and prediction
errors are never indexed. Query-identity and near-duplicate leakage filters
still prevent a task from retrieving its own measurement.

## Security

Revoke any API key pasted into chat, source, shell history, or logs. Put a new
rotated key only in the process environment:

```powershell
$env:GEMINI_API_KEY = "your-rotated-key"
```

Never commit `.env`.

## Install

```powershell
python -m pip install -r gemini_rag_cycle_prototype/requirements.txt
```

## Local Ollama backend

Gemini remains available, but generation and embeddings can run fully locally:

```powershell
ollama pull qwen2.5-coder:14b
ollama pull nomic-embed-text

$env:LLM_PROVIDER = "ollama"
$env:OLLAMA_MODEL = "qwen2.5-coder:14b"
$env:OLLAMA_EMBEDDING_MODEL = "nomic-embed-text"

# Required once before using RAG with Ollama embeddings.
python -m gemini_rag_cycle_prototype.cli --provider ollama --rebuild-index

# Source-only prediction (does not need an embedding model/index rebuild).
python -m gemini_rag_cycle_prototype.cli --provider ollama `
  --source "path/to/task.c" --function "TaskName" --no-rag `
  --output "gemini_rag_cycle_prototype/results/task_ollama.json"
```

The default Ollama endpoint is `http://127.0.0.1:11434`. Configuration options
include `OLLAMA_BASE_URL`, `OLLAMA_REQUEST_TIMEOUT_SECONDS`, `OLLAMA_NUM_CTX`,
`OLLAMA_NUM_PREDICT`, `OLLAMA_TEMPERATURE`, and `OLLAMA_SEED`. Each prediction
writes a `.run.json` sidecar containing provider/model provenance and duration.
Generation is read as a stream to keep long CPU-only runs alive. Defaults use a
16K context and a 6144-token output budget; the complete prompt and timing data
are unchanged. The default request timeout is 3600 seconds because a 14B model
running entirely on CPU may spend more than 15 minutes processing the prompt
before the first streamed response token is available.

## Discover measured data

```powershell
python -m gemini_rag_cycle_prototype.cli --discover
```

## Build cached Gemini embedding index

```powershell
python -m gemini_rag_cycle_prototype.cli --build-index
```

## Current blind holdout

```powershell
$source = "experiments/gemini_source_only_holdout_v3/automotive_holdout_v3_tasks.c"

python -m gemini_rag_cycle_prototype.cli --source $source `
  --function BatteryBalancing_Task10ms --no-rag `
  --output gemini_rag_cycle_prototype/results/holdout_v3_battery.json

python -m gemini_rag_cycle_prototype.cli --source $source `
  --function EpsTorqueArbitration_Task5ms --no-rag `
  --output gemini_rag_cycle_prototype/results/holdout_v3_eps.json

python -m gemini_rag_cycle_prototype.cli --source $source `
  --function ThermalNetworkSupervision_Task20ms --no-rag `
  --output gemini_rag_cycle_prototype/results/holdout_v3_thermal.json
```

The matching board ELF and debugger expressions are documented in
`experiments/gemini_source_only_holdout_v3/README.md`.

## Leakage controls

Retrieval excludes a record when hardware differs or query identity matches by
task ID, function name, source path, normalized source fingerprint, or
near-duplicate source.
The queried task measurement is not sent to Gemini. Retrieved measurements are
included only after code similarity ranking.

## Units

Repository fields ending in `_us_x1000` are divided by 1000. For example,
`28187` becomes `28.187 us`.

## Tests

```powershell
python -m unittest discover -s gemini_rag_cycle_prototype/tests -v
```

The real API integration builds the index, runs the blind prediction, and
checks that the query did not appear in retrieval. It requires a rotated key:

```powershell
$env:RUN_GEMINI_INTEGRATION = "1"
python -m unittest gemini_rag_cycle_prototype.tests.test_gemini_integration -v
```
