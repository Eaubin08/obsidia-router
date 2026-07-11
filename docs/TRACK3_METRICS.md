# Track 3 metrics — claims, sources, allowed wording

Every Track 3 / storytelling claim in this repo must map to a measured value
with a named source file and an evidence level. No new numbers are invented
here; everything below points to `results/REPORT.md`,
`results/FRONTIER_REPORT.md` or a benchmark script.

Evidence levels: `PRACTICE` · `INTERNAL_DRY` · `LIVE_SAMPLE` · `OFFICIAL_HIDDEN`
(see [BENCHMARKS.md](BENCHMARKS.md)).

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
- **LIVE_SAMPLE**: official-runner live sample (5 tasks) — 4 local / 1 remote, ≈389 tokens
  (`scripts/run_official.py` with a live key).
- **Source**: `results/REPORT.md`, runner output.
- **Allowed**:
  > On the internal benchmark, every task closes locally at zero token. On the live 5-task sample, 4 of 5 tasks close locally; the single open-reasoning task escalates under a bounded contract (~389 tokens total).
- **Forbidden**: presenting the dry benchmark as an official Fireworks run, or
  `0 tokens` without naming the INTERNAL_DRY perimeter.

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

- **Measured**: 0 false local closures. Also: 15 LOCAL wins, 10 correct
  abstentions, 12 FIREWORKS_USEFUL calls.
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

Two separate measurements (see BENCHMARKS.md):

- **Local decision latency**: `0.211 ms` average on the internal 18-task benchmark.
- **Dynamic campaign throughput**: approximately `11,340 decisions/s`, measured
  at `0.088 ms/decision` under dynamic batch conditions.

> These measurements come from different task mixes and benchmark conditions.
> They must not be converted into one another.

- **Allowed**:
  > A local deterministic decision takes approximately 0.2 ms in the internal benchmark, while remote inference takes seconds. When the route is known, predicting becomes slower than verifying.
- **Forbidden**:
  > ~~0.211 ms equals 11,340 decisions per second.~~

## 8. Cognitive value inputs

- **What it is**: a readonly projection that regroups metrics already
  computed by the benchmark into the inputs a governed valuation layer would
  read. Nothing is minted, priced, or scored; no wallet; no economic scoring;
  the projection has zero influence on routing, gates or Track 1 scoring.
- **Source**: `benchmarks/value_inputs.py` (hard rules enforced by
  `tests/test_value_inputs.py`).
- **Evidence level**: INTERNAL_DRY.

---

## Narrative spine (each sentence backed by a metric above)

1. *"Obsidia is not a bigger model"* → §6 footprint.
2. *"It decides whether inference is necessary"* → §2 inference avoidance (LIVE_SAMPLE 4/5 local).
3. *"When the route is known, predicting is slower than verifying"* → §7 speed + §5 break-even.
4. *"Local closure / abstention / useful Fireworks"* → §5 frontier (15/10/12, 0 false closures).
5. *"Gates before model"* → §3 governance.
6. *"KX108_ONLY, no real action, no memory write"* → §3 + §4 (740/740).
7. *"Frontier boundary map"* → §5.
8. *"Cognitive value inputs, readonly, no wallet"* → §8.
