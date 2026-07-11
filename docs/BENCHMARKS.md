# Benchmarks — command matrix, evidence levels, spend safety

This document lists every test, benchmark and runner in the repo, with its
exact token-spend status. The README only carries the official Track 1 path;
everything else lives here.

## Evidence levels

| Label | Meaning |
|---|---|
| `PRACTICE` | AMD practice categories (8 published tasks) |
| `INTERNAL_DRY` | Internal benchmark, deterministic, zero Fireworks token |
| `LIVE_SAMPLE` | Real Fireworks calls on a small local sample (5 tasks) |
| `OFFICIAL_HIDDEN` | The hidden AMD judge — unknown until it runs |

**Doctrine**: repository metrics never claim the hidden AMD judge score in
advance. `8/8`, `18/18`, `15/15` and `740/740` are measured on published
internal sets only.

## Command matrix

| Command | Purpose | Spend | Writes | Evidence | Recommendation |
|---|---|---|---|---|---|
| `python -m pytest -q` | full unit suite (35 files) | SAFE | no | INTERNAL_DRY | always |
| `python benchmarks/answer_accuracy.py` | 8 AMD practice categories | SAFE | `results/answer_accuracy_by_category.json`, `results/amd_practice_category_metrics.json` | PRACTICE | always |
| `python benchmarks/run_benchmark.py --track1-official --stack-v3b` | 18-task benchmark + 15 stack routes | SAFE | `results/benchmark_report.json`, `results/REPORT.md`, `results/results.json`, `results/receipts_internal.json` | INTERNAL_DRY | always |
| `... --dynamic N` | N×6 seeded variations (seed 108; default run = 180 cases) | SAFE | REPORT section | INTERNAL_DRY | bonus |
| `... --dynamic-v2 N` | seeded dirty variations (seed 208; default run = 160 cases) | SAFE | REPORT section | INTERNAL_DRY | bonus |
| `... --random-batches 10 --random-batch-size 40 --random-seed 108` | 400 random cases | SAFE | REPORT section | INTERNAL_DRY | bonus |
| `... --live-baseline` | all 18 tasks sent raw to Fireworks as baseline arm | **LIVE TOKEN SPEND** (≈18 calls) | REPORT baseline columns | LIVE_COMPARATIVE | deliberate only |
| `... --random-compare` | same dirty prompt: Obsidia vs raw LLM | **LIVE TOKEN SPEND** (variable) | REPORT section | LIVE_COMPARATIVE | deliberate only |
| `python benchmarks/run_frontier_benchmark.py` | frontier boundary map (dry) | SAFE | `results/frontier_benchmark_report.json`, `results/FRONTIER_REPORT.md` | INTERNAL_DRY | bonus |
| `python benchmarks/run_frontier_benchmark.py --live` | frontier with real Fireworks calls | **LIVE TOKEN SPEND** (≈12 calls) | same | LIVE_COMPARATIVE | deliberate only |
| `python benchmarks/probe_ladder.py` | 1 minimal call per ladder model | **LIVE TOKEN SPEND** (1×N models) | no | LIVE_DIAGNOSTIC | pre-demo diagnostic |
| `python scripts/fireworks_smoke_test.py` | API connectivity check | **LIVE TOKEN SPEND** (1-2 calls) | no | LIVE_DIAGNOSTIC | pre-demo diagnostic |
| `python scripts/model_matrix_smoke_test.py --dry-run` | contract design + model discovery, no calls | SAFE | no | INTERNAL_DRY | diagnostic |
| `python scripts/model_matrix_smoke_test.py` (no `--dry-run`) | N models × 3 categories, full completions | **POTENTIALLY EXPENSIVE** — requires `CONFIRM_SPEND=1` | no | LIVE_DIAGNOSTIC | rare recalibration only |
| `python scripts/run_official.py --input ... --output ...` | official AMD runner | LIVE if key set (~389 tokens on the 5-task sample), dry otherwise | output file only | LIVE_SAMPLE | submission path |
| `docker build` + `docker run` | AMD submission harness | LIVE if key set | `/output/results.json` | LIVE_SAMPLE | submission path |

## Measured baseline numbers (current, db6fa75)

| Metric | Value | Evidence level | Source |
|---|---:|---|---|
| Category accuracy | 8/8 | PRACTICE | `answer_accuracy.py` |
| Route accuracy | 18/18 | INTERNAL_DRY | `run_benchmark.py` |
| V3B stack routes | 15/15 | INTERNAL_DRY | `--stack-v3b` |
| Remote calls (18-task benchmark) | 0/18 | INTERNAL_DRY | `run_benchmark.py` |
| Live sample remote calls | 1/5 | LIVE_SAMPLE | `run_official.py` |
| Live sample token use | ≈389 | LIVE_SAMPLE | `run_official.py` |
| Dynamic invariants | 180/180 (seed 108) | INTERNAL_DRY | `--dynamic` |
| Dirty invariants | 160/160 (seed 208) | INTERNAL_DRY | `--dynamic-v2` |
| Random invariants | 400/400 (10×40, seed 108) | INTERNAL_DRY | `--random-batches` |
| Consolidated invariants | 740/740 = 180+160+400 | INTERNAL_DRY | sum of the three campaigns above |
| Frontier false local closures | 0 | INTERNAL_DRY | `run_frontier_benchmark.py` |
| Frontier break-even complexity | 4 (current benchmark observation) | INTERNAL_DRY | `FRONTIER_REPORT.md` |
| Stack footprint | 1.88 MB, 0 GB embedded weights | INTERNAL_DRY | `footprint.py` |
| Hidden judge accuracy | Unknown | OFFICIAL_HIDDEN | external |

### Latency vs throughput — separate measurements

Local decision latency and dynamic batch throughput are **separate
measurements and must not be converted into one another** without matching
benchmark conditions:

- **Local decision latency**: 0.211 ms average over non-Fireworks rows of the
  18-task benchmark (all local levels).
- **Dynamic phase throughput**: ~11,340 decisions/s measured in the dynamic
  campaign at 0.088 ms/decision (batch conditions, level-0-heavy families).

The two numbers come from different task mixes; neither is the inverse of the
other.

## Packs

### RUN_TRACK1_CORE_SAFE  [SAFE — zero token]

```powershell
python -m pytest -q; `
python benchmarks/answer_accuracy.py; `
python benchmarks/run_benchmark.py --track1-official --stack-v3b
```

### RUN_BONUS_SAFE  [SAFE — zero token]

```powershell
python benchmarks/run_benchmark.py --track1-official --stack-v3b --dynamic 100 --dynamic-v2 100 --random-batches 10 --random-batch-size 40 --random-seed 108; `
python benchmarks/run_frontier_benchmark.py
```

Generates all robustness reports (dynamic/dirty/random invariants, frontier
boundary map, footprint, cognitive value inputs — all readonly projections).

### RUN_SUBMISSION_LIVE  [LIVE if FIREWORKS_API_KEY set]

```powershell
python scripts/run_official.py --input .\tmp_live_input\tasks.json --output .\tmp_live_output\results.json; `
docker build -t obsidia-router .; `
docker run -e FIREWORKS_API_KEY=$env:FIREWORKS_API_KEY -v ${PWD}\tmp_live_input:/input -v ${PWD}\tmp_docker_output:/output obsidia-router
# validate: output is a pure JSON list of {"task_id", "answer"} only
```

No comparative baseline and no model matrix are included in this pack. This is the submission path only.

### RUN_EVIDENCE_CAPTURE_LIVE  [⚠ LIVE TOKEN SPEND]

> **⚠ This pack spends Fireworks tokens and must never be included in
> automatic validation or RUN_ALL workflows.** Run once, deliberately, to
> produce dated comparative evidence; then cite the generated reports.

```powershell
python benchmarks/run_benchmark.py --track1-official --stack-v3b --live-baseline
python benchmarks/run_benchmark.py --track1-official --stack-v3b --random-compare
python benchmarks/run_frontier_benchmark.py --live
```

## Diagnostic scripts (never in packs)

| Script | When to run | Spend |
|---|---|---|
| `benchmarks/probe_ladder.py` | before a live demo, to verify every ALLOWED_MODELS rung answers on this key | 1 minimal call per model |
| `scripts/fireworks_smoke_test.py` | connectivity check minutes before a live demo | 1-2 calls |
| `scripts/model_matrix_smoke_test.py` | model recalibration only; `--dry-run` is the default documented mode; live mode requires `CONFIRM_SPEND=1` | N models × 3 full completions |
