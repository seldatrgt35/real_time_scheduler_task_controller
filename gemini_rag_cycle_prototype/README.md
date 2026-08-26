# Gemini RAG cycle prediction prototype

Independent source-only prototype for:

```text
C source -> measured-task retrieval -> Gemini prediction -> cycles and us
```

It does not compile the query, inspect ELF/assembly, call the existing STAR
execution estimator, or perform scheduler analysis. Gemini produces the final
nominal and conservative-upper predictions. Python validates and records them
without replacing the values.

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

## Discover measured data

```powershell
python -m gemini_rag_cycle_prototype.cli --discover
```

## Build cached Gemini embedding index

```powershell
python -m gemini_rag_cycle_prototype.cli --build-index
```

## Blind prediction

```powershell
python -m gemini_rag_cycle_prototype.cli `
  --source experiments/llm_source_wcet_blind_test/automotive_sensor_matrix_task.c `
  --function AutomotiveSensorMatrix_Task10ms `
  --exclude-task-id AutomotiveSensorMatrix_Task10ms `
  --exclude-function AutomotiveSensorMatrix_Task10ms `
  --exclude-source-path experiments/llm_source_wcet_blind_test/automotive_sensor_matrix_task.c `
  --top-k 5 `
  --output gemini_rag_cycle_prototype/results/automotive_sensor_matrix_prediction.json
```

Add helper/header context with repeated `--context-file` arguments.

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
