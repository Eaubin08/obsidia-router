# Track 3 metrics — claims, sources, allowed wording

Every Track 3 / storytelling claim in this repo must map to a measured value
with a named source file and an evidence level. No new numbers are invented
here; everything below points to `results/REPORT.md`,
`results/FRONTIER_REPORT.md`, a benchmark script, or a Track 3
`run_report.json`.

Evidence levels: `PRACTICE` · `INTERNAL_DRY` · `LIVE_FRONTIER` · `OFFICIAL_HIDDEN`
(see [BENCHMARKS.md](BENCHMARKS.md)).

---

## 0. Track 3 governed escalation runtime — verified results

- **Demo video**: https://www.youtube.com/watch?v=Bxe5saL0lvo&t=195s
- **Public container**: `ghcr.io/eaubin08/obsidia-router:track3-real-escalation`
- **Digest**: `sha256:a2ae4b0b5ac71786ec5322406e130c97f2df1d19cae133e3b8de395189a2283c`
- **Architecture**: linux/amd64
- **Source**: `app/track3/`, `tests/track3/`, `Dockerfile.track3-real`,
  `scripts/track3_real_entrypoint.py`, the container run's `run_report.json`.

| Surface | Result |
|---|---:|
| Track 3 tests | 359/359 passed |
| Real Qwen tests | 5/5 passed |
| Demonstration batch | 12 tasks |
| Receipt hashes | 12/12 valid |
| Readonly replays | 12/12 matched |
| Fireworks calls | 0 |
| Remote tokens | 0 |
| Memory writes | 0 |
| World actions | 0 |
| Kernel mutations | 0 |
| Decision authority | KX108_ONLY |

Escalation distribution of the 12-task demonstration batch (from the
validated container run's `run_report.json`): LEVEL 0 = 3, LEVEL 1 = 2,
LEVEL 2 = 2, LEVEL 3 local Qwen = 5, LEVEL 3 Brody readonly = 0.

- **Allowed**:
  > 359/359 Track 3 tests passed, including 5 real-Qwen integration tests
  > executed against the actual local Qwen2.5-3B model. The 5 real-model
  > tests skip automatically when no local Qwen endpoint is running.

  > Accuracy: 4/5 on the scored demonstration subset (5 of the 12 demo
  > tasks carried an expected answer).

  > Brody readonly is only called when a real loopback endpoint is
  > available; no loopback Brody endpoint was available in this run, so
  > LEVEL 3 Brody = 0.
- **Forbidden**:
  > ~~80% Track 3 accuracy~~ (without naming the 5-task scored subset)
  > ~~The private Brody was executed in the public runtime.~~
  > ~~The demonstration batch is a general benchmark.~~
  > ~~Track 3 numbers merged with Track 1 benchmark numbers.~~

The Track 3 runtime never calls Fireworks: 0 calls and 0 remote tokens by
construction, verified per run in `run_report.json`.

---

## 1. Accuracy

- **Measured value**: 8/8 (PRACTICE), 18/18 (INTERNAL_DRY), 15/15 V3B (INTERNAL_DRY)
- **Source**: `benchmarks/answer_accuracy.py`, `benchmarks/run_benchmark.py`, `results/REPORT.md`
- **Allowed**:
  > Obsidia maintained 100% measured accuracy across the published Track 1 validation surfaces.

  Detail: 8/8 AMD practice categories; 18/18 internal routing accuracy; 15/15 V3B stack routes closed (closure, not route accuracy).

  > Internal routing accuracy remained 100%: 18/18 routes correct.

  > 18/18 routes correct in the internal Track 1 validation set. 8/8 AMD practice categories passed.
- **Forbidden**:
  > ~~Obsidia achieved 100% official AMD accuracy.~~
  > ~~Obsidia has passed the hidden AMD accuracy gate.~~

The hidden official AMD evaluation remains external to these repository metrics.

## 2. Inference avoidance

Two distinct perimeters — never merge them:

- **INTERNAL_DRY**: 18/18 tasks closed locally, 0 tokens, 0 remote calls
  (`run_benchmark.py --track1-official`).
- **LIVE_FRONTIER**: observed live frontier run — 9 real paid Fireworks
  calls, spend compressed 4265 → 2650 → 2438 tokens (mean ≈271, median 275),
  routes unchanged, 0 false local closures
  (`benchmarks/run_frontier_benchmark.py --live`, deliberate spend).
- **Source**: `results/FRONTIER_REPORT.md`, root README evidence ladder.
- **Allowed**:
  > On the internal benchmark, every task closes locally at zero token. On the observed live frontier run, the 9 paid Fireworks calls were compressed from a 4265-token baseline to 2438 tokens without changing any route.
- **Forbidden**: presenting the dry benchmark as an official Fireworks run, or
  `0 tokens` without naming the INTERNAL_DRY perimeter.

## Inference-layer distribution

- Evidence level: `INTERNAL_DRY`
- Dataset: internal 18-task benchmark
- Level 0: 11/18 = 61.1%
- Level 1: 5/18 = 27.8%
- Level 2: 2/18 = 11.1%
- Level 3 / Fireworks: 0/18 = 0%
- Level 0 + Level 1: 16/18 = 88.9%
- Remote calls avoided: 18/18

In this benchmark, the 5 Level-1 tasks were closed by deterministic local
solvers, not by a live Brody call. Level 2 refers to the public cut's
minimal memory index, not the full private memory.

**Allowed**:

> On the internal 18-task benchmark, 61.1% of requests were resolved or
> governed before any model layer.

> 16 of 18 requests were closed through structural Level 0 handling or
> deterministic Level 1 solvers, before memory or remote inference.

> All 18 baseline remote calls were avoided on this INTERNAL_DRY benchmark.

**Forbidden**:

> ~~Obsidia eliminates 61.1% of inference on every workload.~~

> ~~61.1% of all future requests will never require a model.~~

> ~~The hidden AMD benchmark required zero model calls.~~

> ~~Brody answered 5 of the 18 tasks.~~

These layer-distribution figures belong exclusively to the 18-task
INTERNAL_DRY benchmark. They must not be merged with the LIVE_FRONTIER
evidence, where 9 real paid Fireworks calls were observed and compressed
from 4265 to 2438 tokens.

- INTERNAL_DRY measures how much of a known validation surface can close
  before remote inference.
- LIVE_FRONTIER measures the cost and behavior of the calls that remain
  genuinely necessary.

## 3. Governance

- **Measured**: gates run before any model; HOLD / DENY / CLARIFY answer at
  zero token; gate verdict distribution on the 18-task set: ALLOW 8, HOLD 4,
  DENY 2, CLARIFY 4. `decision_authority=KX108_ONLY`, `real_action=false`,
  `memory_write=false` on every row.
- **Source**: `app/gates/gates.py`, `results/REPORT.md` control section,
  `tests/test_gates.py`, `tests/test_governance.py`.
- **Allowed**:
  > World actions never reach a model. A HOLD verdict is a valid zero-token answer.
- **Forbidden**: claiming the governance layer executes or blocks real-world
  actions — it emits verdicts only (`emits_act=false`).

## 4. Robustness (740/740 invariants)

Exact composition — always cite it when using the total:

| Campaign | Cases | Seed | Result |
|---|---:|---|---|
| Dynamic bounded | 180 | 108 | 180/180 held |
| Dirty / dynamic-v2 | 160 | 208 | 160/160 held |
| Random batches | 400 (10×40) | 108 | 400/400 held |
| **Consolidated** | **740** | — | **740/740 held** |

- **Source**: `results/REPORT.md` (dynamic, dirty, random sections),
  `benchmarks/dynamic_cases.py`, `dynamic_cases_v2.py`, `random_dynamic.py`.
- **Evidence level**: INTERNAL_DRY (all zero-token, seeded, replayable).
- **Note**: `--dynamic 100` may generate a different volume. The published
  `180/160/400` figures belong to the identified seeded report snapshots and
  must not be mixed with another run.

## 5. Frontier

- **Measured**: 0 false local closures. Also: 15 local closures, 12
  frontier/escalation cases, 8 governed paths, 10 correct local-only
  abstentions; 9 FIREWORKS_USEFUL cases became real paid calls in the
  observed live run.
- **Break-even observation**: complexity level 4 in the current frontier benchmark.
- **Evidence level**: INTERNAL_DRY (dry run); `--live` produces the LIVE_COMPARATIVE variant.
- **Source**: `results/FRONTIER_REPORT.md`, `benchmarks/run_frontier_benchmark.py`.
- **Allowed**:
  > In the current frontier benchmark, local verification remains favorable below complexity level 4.

  > Zero false local closures: no micro-solver ever answered outside its fingerprint.
- **Forbidden**:
  > ~~Every task below level 4 should always be solved locally.~~

## 6. Footprint

- **Measured**: stack footprint 1.88 MB, 0 GB embedded learned weights.
- **Source**: `benchmarks/footprint.py`, `results/REPORT.md` parametric
  efficiency section.
- **Allowed**:
  > This public Track 1 cut embeds 0 GB of learned model weights in a 1.88 MB stack.
- **Forbidden**: implying the full private Obsidia architecture is 1.88 MB —
  this figure covers the public router cut only.

## 7. Speed

Two separate, run-dependent measurements (see BENCHMARKS.md):

- **Stable claim**: sub-millisecond local deterministic routing.
- **Stable claim**: more than 10,000 decisions/s observed in the current
  dynamic benchmark.
- **Latest committed snapshot**: `0.122 ms` local decision latency,
  `~15,034 decisions/s` at `0.067 ms/decision` (dynamic campaign).
- **Source of truth**: `results/REPORT.md`.

> These measurements come from different task mixes and benchmark conditions.
> They must not be converted into one another. Exact values are machine- and
> run-dependent.

- **Allowed**:
  > In the latest committed benchmark snapshot, local deterministic routing remained sub-millisecond and dynamic throughput exceeded 10,000 decisions per second.

  > A local deterministic decision takes well under a millisecond in the internal benchmark, while remote inference takes seconds. When the route is known, predicting becomes slower than verifying.
- **Forbidden**:
  > ~~These performance values are fixed hardware-independent guarantees.~~
  > ~~Local latency equals the inverse of dynamic throughput.~~

## 8. Cognitive value inputs

- **What it is**: a readonly projection that regroups metrics already
  computed by the benchmark into the inputs a governed valuation layer would
  read. Nothing is minted, priced, or scored; no wallet; no economic scoring;
  the projection has zero influence on routing, gates or Track 1 scoring.
- **Source**: `benchmarks/value_inputs.py` (hard rules enforced by
  `tests/test_value_inputs.py`).
- **Evidence level**: INTERNAL_DRY.

## 9. Adaptive model triage

- **Measured**: which model was selected, at which ladder rung, and why —
  for every remote call, on the runner, the benchmark and the CLI alike.
  `model_call_distribution`, `model_rung_distribution`,
  `first_rung_call_rate` / `intermediate_rung_call_rate` /
  `last_rung_call_rate`, `higher_rung_calls_avoided` (a call count),
  `local_solver_hit_rate`, `code_tasks_closed_locally`, `remote_code_calls`.
- **Source**: `app.router.model_triage` (the selection itself),
  `app.metrics.triage_metrics` (the aggregates), and the report generator
  in `benchmarks/run_benchmark.py`. The "Adaptive model triage" section
  will appear in `results/REPORT.md` on the next safe benchmark run; the
  currently committed report predates LOT E. Per-run metadata is written
  to `track1_triage_receipts.json`.
- **Evidence level**: INTERNAL_DRY (instrumentation always active);
  LIVE_FRONTIER for deliberate `--live` runs with a real `FIREWORKS_API_KEY`.
- **Allowed**:
  > The router records which rung of the ALLOWED_MODELS ladder it selected and why, for every remote call.
- **Forbidden**:
  > ~~Using a smaller model saves N% in tokens/dollars.~~ (per-model cost is not measured; only call counts are reported)
  > ~~The ladder order is verified as cost-ascending.~~ (it is stated by the harness, not independently checked)

---

## Narrative spine (each sentence backed by a metric above)

1. *"Obsidia is not a bigger model"* → §6 footprint.
2. *"It decides whether inference is necessary"* -> section 2 inference avoidance (INTERNAL_DRY 18/18 local, LIVE_FRONTIER 9 paid calls compressed).
3. *"When the route is known, predicting is slower than verifying"* → §7 speed + §5 break-even.
4. *"Local closure / abstention / useful Fireworks"* → §5 frontier (15/10/12, 0 false closures).
5. *"Gates before model"* → §3 governance.
6. *"KX108_ONLY, no real action, no memory write"* → §3 + §4 (740/740).
7. *"Frontier boundary map"* → §5.
8. *"Cognitive value inputs, readonly, no wallet"* → §8.
9. *"The router audits its own model choice"* → §9 adaptive model triage.
