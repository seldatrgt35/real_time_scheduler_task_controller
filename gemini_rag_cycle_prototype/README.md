# Gemini source-level execution-time prototype

Independent source-only prototype for:

```text
C source -> Gemini prediction -> one conservative execution-time estimate
```

The active workflow is source-only (`--no-rag`). It does not compile the query,
inspect ELF/assembly, call the existing STAR execution estimator, or perform
scheduler analysis. Gemini produces `estimated_execution_cycles` and
`estimated_execution_us`. Python validates and records those values without
replacing or recalculating them.

The cached RAG implementation and frozen baseline are retained for a later
controlled source-only versus RAG comparison; they are not used by the current
holdout-v3 experiment.

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
