# Obsidia Router — Track 3 / Unicorn Submission

> Every number in this document maps to a measured value with a named source.
> Claim discipline and allowed wording: [TRACK3_METRICS.md](TRACK3_METRICS.md).

## 1. One-line pitch

**Obsidia is not a bigger model. It is a pre-inference governance router that
decides when inference is necessary.**

## How this single repo serves both tracks

- **Track 1 validates the measured router**: the internal benchmark, the
  Docker submission harness, the strict output contract, and token efficiency
  under the official accuracy gate.
- **Track 3 reads the same system as an innovation**: pre-inference
  governance, gates before the model, the frontier boundary map, correct
  abstention as a scored outcome, and governed AMD/Fireworks usage as the
  single choke point for remote tokens.
- This is **one repo, not two separate apps**: every Track 3 claim points to
  a metric produced by the Track 1 surfaces.
- The public repo is the **router slice** of the broader Obsidia Cognitive
  OS. It is not the full private system, and does not claim to be (see §7).

> **Pre-screening note**: the automatic pre-screening inspects the repository
> and the PDF, but may not process demo video content. The slide deck and
> this README therefore carry the key metrics **in text form**; the videos
> are illustration, not the evidence.

## 2. What the project demonstrates

- An LLM should not be called by default. Calling a model is a decision, not
  a reflex.
- Every request is first compiled into a deterministic structure
  (UnifiedInputIR: intent, layer, action, risk, missing context).
- Gates decide **before** the model: DENY > HOLD > CLARIFY > ALLOW.
- Known paths are resolved locally — status, facts, math, sentiment, NER,
  code fingerprints — at zero token.
- Risky requests (push, deploy, rm -rf, ACT) are HOLD / DENY / CLARIFY at
  level 0. A HOLD is a valid answer.
- Two evaluation regimes, stated plainly. In the local governed path
  (demo, internal benchmark), missing structure produces CLARIFY rather than
  fabricated certainty — abstention at 0 token. In the official hidden-task
  evaluation path, unresolved **informational** requests may be escalated
  through a bounded answer contract, so the evaluator receives a controlled
  answer instead of a placeholder. Governed world actions (HOLD/DENY) are
  never escalated in either regime.
- Fireworks becomes useful only beyond the local frontier, under a bounded
  answer contract (capped tokens, forced English, calibrated default model).
- `KX108_ONLY` remains the decision authority on every row: no real action,
  no memory write, no kernel mutation — the layer emits verdicts only.
- Brody, Obsidure, Lean and the domain connectors are non-sovereign or
  route-only in this public cut: their interfaces and contracts are visible,
  their full engines stay in the private stack.

## 3. The core paradigm shift

- Classic agents must infer; **Obsidia can avoid inference.**
- **When the route is known, predicting becomes slower than checking** —
  a local deterministic decision takes well under a millisecond in the
  internal benchmark, while remote inference takes seconds.
- **The LLM is an organ, not the sovereign brain.** The router owns the
  frame; the model fills the gaps the structure cannot close.
- **The system is judged not only by its answers, but by whether it knows
  when not to call a model.** Correct abstention is a scored outcome, not
  a failure.

## 4. Evidence map

| Claim | Existing metric | Source command | Source report |
|---|---|---|---|
| Zero-token practice categories | 8/8 PASS, total_tokens_amd = 0 (PRACTICE) | `python benchmarks/answer_accuracy.py` | `results/amd_practice_category_metrics.json` |
| Internal benchmark at 0 remote | 18/18 route accuracy, 0 tokens, 0 remote calls (INTERNAL_DRY) | `python benchmarks/run_benchmark.py --track1-official --stack-v3b` | `results/REPORT.md` |
| Dynamic invariants | 180/180 held (seed 108) | `... --dynamic 100` | `results/REPORT.md` |
| Dirty dynamic invariants | 160/160 held (seed 208) | `... --dynamic-v2 100` | `results/REPORT.md` |
| Random replayable invariants | 400/400 held (10×40, seed 108) — consolidated 740/740 | `... --random-batches 10 --random-batch-size 40 --random-seed 108` | `results/REPORT.md` |
| Path quality | route/level/gate correctness per axis, no global vanity score | `run_benchmark.py` (path axes) | `results/REPORT.md` |
| Speed profile | 0.122 ms avg local decision; ~15,034 decisions/s dynamic throughput (separate measurements, run-dependent) | `run_benchmark.py` | `results/REPORT.md` |
| Escalation quality | escalation requires an ALLOW verdict; bounded remote answer contract | `run_benchmark.py`, `tests/test_dynamic_invariants.py` | `results/REPORT.md` |
| Frontier false local closures | **0** — no micro-solver ever answered outside its fingerprint | `python benchmarks/run_frontier_benchmark.py` | `results/FRONTIER_REPORT.md` |
| Break-even complexity | local verification remains favorable below complexity level 4 | same | `results/FRONTIER_REPORT.md` |
| V3B stack families | 15/15 routes closed (closure, not route accuracy) | `... --stack-v3b` | `results/REPORT.md` |
| Footprint | 0 GB embedded learned weights in a 1.88 MB stack (public cut only) | `benchmarks/footprint.py` via `run_benchmark.py` | `results/REPORT.md` |
| Cognitive value inputs | readonly projection, 5 whitelisted groups, mint/wallet/economic_scoring = false, status DEFERRED | `benchmarks/value_inputs.py` (enforced by `tests/test_value_inputs.py`) | `results/REPORT.md` |
| Governance baseline violations | Obsidia: 0/8 on governed tasks. Raw-model baseline: **optional live evidence** — requires `--live-baseline`, not measured in the committed snapshot | `run_benchmark.py --live-baseline` (⚠ spends tokens) | `results/REPORT.md` governance table |
| Adaptive model triage | which model/rung was selected and why, for every remote call; call counts kept below the highest allowed rung ? never a token/dollar saving claim | `app.router.model_triage`, `app.metrics.triage_metrics` | `benchmarks/run_benchmark.py` generator (section appears on the next safe run; committed REPORT predates LOT E), `track1_triage_receipts.json` |

## 4b. Govern before inference — four blocks, each backed by existing evidence

**HOLD — do not proceed while the request is not admissible.**
Evidence (MEASURED): GOVERNED_NEVER_MODEL = 6 tasks in the frontier report
(4 HOLD, 2 DENY variants across the internal sets), 0 remote tokens;
invariants `no_auto_act` / `no_auto_commit` / `no_auto_push` attached to
every verdict. Required nuance: the public cut **emits governed verdicts** —
it does not execute or physically block real-world actions. Decision
authority remains `KX108_ONLY`.

**CLARIFY — do not fabricate certainty when required structure is missing.**
Evidence (MEASURED): missing fields are produced deterministically by
UnifiedInputIR; 4 CLARIFY rows in the internal 18-task benchmark and
FRONTIER_ABSTAIN = 5 in the frontier report, all at 0 remote tokens in the
local governed path. Judge-mode nuance (EXECUTED): in the official
hidden-task path, an unresolved informational request escalates under the
bounded answer contract rather than returning a placeholder (see §2).

**LOCAL VERIFY — do not predict what can be calculated, matched or verified
locally.** Evidence (MEASURED): 15 deterministic local closures in the
frontier evidence (SOLO_SAFE), 8/8 practice tasks closed at 0 Fireworks
tokens, and **0 false local closures**. These are high-confidence
deterministic closures on recognized structures — not general local code
intelligence, not full program analysis, not formal verification of
arbitrary code.

**REMOTE INFERENCE — escalate only when the problem remains genuinely
open.** Evidence (MEASURED): FIREWORKS_USEFUL = 9 in the frontier evidence;
every remote call goes through the bounded remote answer contract; live
sample ≈389 tokens with 1/5 remote calls. Both boundaries are now
implemented: *when to infer* (frontier evidence above) and *which model
size* — a single triage authority (`app.router.model_triage`) picks the
smallest sufficient rung of the harness-provided `ALLOWED_MODELS` order for
every escalation path (router, brody escalation, clarification escalation).
Honest caveat: the ladder's cost order is stated by the harness, not
independently verified against the live Fireworks catalog.

## 5. Frontier story

The frontier benchmark (35 tasks, 6 families) maps every request into one of
four zones (`results/FRONTIER_REPORT.md`):

- **SOLO_SAFE** (15 tasks) — exact fingerprint or deterministic closure.
  0 tokens, ~0.18 ms average. Calling a model here is pure waste
  (~4786 tokens saved vs direct Fireworks, estimated).
- **GOVERNED_NEVER_MODEL** (6 tasks) — push, rm -rf, deploy, bypass,
  injection. Fireworks must **never** be called: a model call itself would
  violate no_auto_act / no_auto_commit / no_auto_push. Gates intercept at
  level 0.
- **FRONTIER_ABSTAIN** (5 tasks) — missing fingerprint, unknown entity,
  contradiction. The router abstains or asks for clarification instead of
  guessing.
- **FIREWORKS_USEFUL** (9+ tasks) — open reasoning, uncovered code, genuine
  ambiguity. The structure is not enough; remote inference earns its cost.

Obsidia does not try to close everything locally. The value also comes from
**correct abstention**: zero false local closures matters more than answering
everything. Fireworks is useful — but only when the router decides that local
structure no longer suffices.

## 6. Demo narrative (5 minutes)

| # | Step | Command | What the audience sees | What to say | Note |
|---|---|---|---|---|---|
| 1 | Track 1 safe harness | open `docs/TRACK1_SUBMISSION.md` | the exact judge path: `/input` → runner → `/output` | "This is everything the judge runs. One container, one contract." | doc only, zero risk |
| 2 | Tests + practice accuracy | `python -m pytest -q` then `python benchmarks/answer_accuracy.py` | 830 passed; 8/8 PASS, 0 token | "Eight official categories, zero remote token." | SAFE; run without a key in the env |
| 3 | Internal benchmark | `python benchmarks/run_benchmark.py --track1-official --stack-v3b` | 18/18 routes, 0 remote calls | "Every route correct without calling any model." | SAFE, regenerates REPORT.md |
| 4 | Frontier map | `python benchmarks/run_frontier_benchmark.py` then open `results/FRONTIER_REPORT.md` | the four-zone boundary table | "Green means no model needed. Red means never call a model. The interesting column is zero false local closures." | SAFE (dry mode is explicit in the report header) |
| 5 | Docker official runner | build + dry run + `validate_output.py` (commands in TRACK1_SUBMISSION.md §C) | exit 0, strict `[{task_id, answer}]`, validator PASS | "Same container the judge pulls. No key, still deterministic." | SAFE without `-e FIREWORKS_API_KEY` |
| 6 | Track 3 value | this document §3 and §5 | the paradigm slide | "We didn't build another LLM. We built the layer that decides whether an LLM is needed." | closing, no command |

## 7. What is real in this repo vs deferred

| Current public repo | Deferred / full Obsidia stack |
|---|---|
| Track 1 official runner + Docker harness | Brody full live (proprietary local LLM organ — stubbed here, interface kept) |
| Local solvers (facts, math, sentiment, NER, code fingerprints) | Obsidure full proposal engine (route-only here) |
| Deterministic gates (DENY > HOLD > CLARIFY > ALLOW) | Lean full proof runtime (route-only surface here) |
| Route metrics, path/speed/escalation axes | Full memory integration (public cut ships a minimal example index) |
| Dynamic / dirty / random invariant campaigns (740/740, seeded) | Value layer (cognitive value inputs are readonly projections; nothing minted, priced or scored) |
| Frontier benchmark + boundary map | Domain production connectors |
| V3B route-only stack families (15/15) | UI cockpit |

The public repo is the **evaluated and demonstrable slice** of a larger
system. It does not contain the full Obsidia architecture, and does not
pretend to.

### Local code analysis — exact technical status

The local solver strategy follows an Obsidure-compatible principle:
**inspect, reduce and verify locally before requesting remote prediction.**
The doctrine is already visible in the local-first architecture; the deeper
Obsidure code-analysis integration remains a declared next layer, not a
current benchmark claim. Component by component:

| Component | Status in this public cut |
|---|---|
| Local solvers | **Active** Track 1 router components (EXECUTED, MEASURED) |
| Obsidure | Proposal-only, non-sovereign **route** (`obsidure_route_only`) — it does not execute the solvers |
| CITER / critical-span extractor | **Implemented, not wired** into the remote execution path (unit-tested only) |
| AST analysis | **Not implemented** in the current public cut |
| Obsidure engine + CITER + AST integration | **Deferred** / future integration |

## 8. Track 3 submission text (platform-ready)

**Title** — Obsidia Router: semantic routing before inference.

**Tagline** — The layer that decides whether a model call is necessary —
before spending a single token.

**Problem** — Agent stacks call an LLM by default. Every status check, every
known fact, every dangerous command becomes a remote inference: slow,
expensive, and ungoverned. Most routers only choose *which* model to call.

**Solution** — Obsidia compiles every request into a deterministic structure
(IR), runs governance gates before any model (DENY > HOLD > CLARIFY > ALLOW),
closes known paths locally at zero token, abstains correctly at the frontier,
and escalates to Fireworks only when local structure is not enough — under a
bounded answer contract with a calibrated default model.

**Why AMD / Fireworks matters** — Track 1 is scored on accuracy first, then
total Fireworks tokens ascending. That is exactly the discipline Obsidia
optimizes: on the internal 18-task benchmark every task closes at 0 tokens;
on the live 5-task sample, 4 of 5 close locally and the single open-reasoning
task escalates under a ~389-token bounded contract. Fireworks is the single
choke point where remote tokens are spent — governed and measured.

**What we built** — A stdlib-only Python router (0 GB embedded weights,
1.88 MB stack), a Docker submission harness with a strict
`[{task_id, answer}]` contract, a 740/740 seeded invariant campaign, and a
frontier benchmark that maps where local closure ends and useful inference
begins (zero false local closures, break-even at complexity 4).

**What is novel** — The scored unit is the *decision to infer*, not the
inference. Correct abstention and governed refusal (HOLD/DENY at level 0)
are first-class zero-token answers. Governance is enforced before the model,
not prompted into it.

**Metrics** — 8/8 AMD practice categories at 0 token (PRACTICE) · 18/18
internal route accuracy, 0 remote (INTERNAL_DRY) · 15/15 V3B stack routes ·
740/740 seeded invariants · 0 false local closures · sub-millisecond local
decisions · live sample 4/5 local, ≈389 tokens (LIVE_SAMPLE). The hidden AMD
judge score remains external and unclaimed.

**Future work** — Wire the full Brody organ and memory integration from the
private stack; extend the frontier map with live comparative evidence
(`--live-baseline`, `--random-compare`); publish the deferred valuation layer
as a governed, non-token, readonly consumer of the value inputs already
projected here.
