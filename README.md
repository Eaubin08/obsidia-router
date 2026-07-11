# Obsidia Router — Structure Before Inference

> Most routers optimize **which** model to call.
> Obsidia first decides **whether a model call is necessary**.

**Track 1** (token-efficient agent) — AMD Developer Hackathon: ACT II.
The narrative extends to **Track 3**: this router is the public, measurable
slice of a larger proprietary pre-inference governance stack, where the LLM
is an **organ**, not the brain.

A large LLM must infer; Obsidia can often **verify, route, hold, deny, or
answer before inference**. Every request is compiled into a structured intent
(UnifiedInputIR), checked against deterministic gates and invariants, and only
then — if the structure is not enough — escalated to the cheapest sufficient
Fireworks model, with a compressed prompt and a bounded completion budget.

This repository is not a claim that Obsidia is a bigger or better LLM. It is
a demonstration that a deterministic governance layer placed *before*
inference reduces both the **number** of remote calls and the **cost** of the
calls that remain — without ever closing a task it cannot actually solve.

## What is being demonstrated

- **Not just a router**: routing is one layer of a pre-inference pipeline
  (structure → gates → local capability → escalation → bounded output).
- **Not just prompt compression**: compression is the last optimization,
  applied only to the calls that survive every earlier layer.
- **A proprietary governance stack, public cut**: the full Obsidia
  architecture (Brody, complete memory, Obsidure, Sigma, Lean proofs, domain
  bridges, the X108 kernel runtime) is not fully exposed or activated here.
  The public cut is deliberately limited to what Track 1 evaluates: routing,
  gates, local solvers, the official runner, the Fireworks adapter, and the
  Docker harness.
- **Proof by staged evaluation**: each validation stage below demonstrates a
  different property. No single number carries the claim; the ladder does.

## How to read the metrics

This README does not report one global intelligence score. It reports a
**validation ladder**. Each layer measures a different property: correctness
of the public code, correctness of the official runner path, Docker
submission compliance, route correctness, remote calls avoided, token spend,
governance safety, frontier behavior, and live Fireworks cost compression.
Repository metrics are evidence surfaces, not the hidden AMD judge score.

### Token types

- `local tokens = 0` — local solvers, gates, holds, denials, clarifications
  and dry decisions do not call Fireworks.
- `total_tokens_amd` — Fireworks tokens spent on the AMD practice category
  path. Current value: **0**.
- `estimated_tokens_saved` — internal estimate against a direct-model
  baseline. Current value: **5584** on the 18-task benchmark.
- `dry token estimate` — token estimate produced without real Fireworks
  calls, used to inspect routing safely.
- `live Fireworks tokens` — real token count returned by Fireworks during
  deliberate `--live` runs.
- `prompt tokens + completion tokens` — a live total includes both the
  prompt sent to the model and the model response.
- `remote call` — a real Fireworks API call.
- `frontier/escalation bucket` — a benchmark category marking tasks that
  should *not* close locally; not every bucket entry necessarily becomes a
  paid Fireworks execution in the public cut.

### Route and safety metrics

- `route accuracy` — whether the router picked an accepted path.
- `remote_calls_avoided` — how many direct-model calls were avoided.
- `level-0 rate` — how much was handled before any model layer.
- `governed` — held, denied, or clarified instead of answered/generated.
- `correct abstention` — the local-only path correctly refuses to answer.
- `false_local_closures = 0` — the router never pretended to know locally
  just to save tokens. **This is the key frontier safety metric.**

### Dry vs live

- SAFE/dry commands are used for repeatable validation without spending
  tokens. Live commands are deliberate and spend Fireworks tokens.
- Dry proves route distribution and invariants. Live proves actual
  remote-token cost.
- The hidden AMD judge remains external to both.

## Evidence ladder

Read this as a proof ladder, not as one score: each block proves a
different property.

### A. Submission proof

| Stage | Command / surface | Result | What it proves |
|---|---|---|---|
| Pytest suite | `python -m pytest -q` | **1230 passed, 3 skipped** | The public cut is internally consistent; the 3 skipped tests are conditional report-integration tests, not failures. |
| AMD practice grader | `python benchmarks/answer_accuracy.py` | **8/8 PASS, 0 tokens, 0/8 remote** | All 8 public practice categories can be answered locally on this surface. |
| Official runner path | `scripts/run_official.py` + `validate_output.py` | **8/8, 0 tokens, schema STRICT PASS** | The same path used by the Docker container writes strict output. |
| Docker GHCR public run | `docker run ghcr.io/eaubin08/obsidia-router:track1-0a5fc69` | **8 tasks, 0 tokens, 0/8 remote, exit 0** | The submitted public image can be pulled and run end-to-end. |

### B. Routing and safety proof

| Stage | Command / surface | Result | What it proves |
|---|---|---|---|
| Internal routing benchmark | `run_benchmark.py --track1-official --stack-v3b` | **18/18 routes, 0 tokens, 5584 est. tokens saved** | The router avoids 18/18 baseline remote calls on this benchmark, saving an estimated 5584 tokens. |
| Dynamic bounded invariants | `tests/test_dynamic_invariants.py` | **180/180 held, 0 tokens, ≈0.073 ms/decision** | Generated rephrasings preserve gate behavior. |
| Dynamic dirty invariants | dirty phase V2 | **160/160 held, 0 tokens, ≈0.082 ms/decision** | Noise/typos/injection attempts do not leak into unsafe actions or unwanted model calls. |
| V3B stack benchmark | stack routes | **15/15, 0 remote tokens, KX108_ONLY** | Brody/Obsidure/Lean/domain surfaces are routed without enabling real action, memory writes, or kernel mutation. |

### C. Frontier and live-token proof

| Stage | Command / surface | Result | What it proves |
|---|---|---|---|
| Frontier dry benchmark | `run_frontier_benchmark.py` | **15 local / 12 frontier-escalation / 8 governed, false closures = 0** | The router keeps unsupported cases open/escalated/governed instead of over-closing. |
| Frontier live compression | `run_frontier_benchmark.py --live` | **4265 baseline → 2650 compact contract → 2438 final P5D** | The same routes were kept, false local closures stayed 0, and the 9 real paid Fireworks calls became cheaper. |
| Hidden AMD judge | external | **Unknown** | The official hidden evaluation is external; repository metrics are evidence surfaces, not a leaderboard claim. |

### Frontier numbers in plain English

- The frontier benchmark has **35 tasks**: 15 close locally, 8 are governed
  by hold/deny/clarify paths, and 12 are frontier/escalation cases where the
  router should *not* force a local answer.
- In the observed live run, **9** of those became real paid Fireworks calls.
- **4265** = original live frontier Fireworks spend before compact remote
  contracts. **2650** = spend after compact system prompts and tighter
  completion budgets. **2438** = spend after final P5D prompt hygiene and
  cap tightening.
- The route distribution did not change. `false_local_closures` stayed 0.
- The paid remote calls went from about 474 tokens/call to about 271
  tokens/call.
- The point is not "close everything locally"; the point is "know when to
  answer, when to govern, and when to pay for inference."

## Architecture layers

```
request
  → structure     (UnifiedInputIR: intent / layer / action / risk / needs)
  → gates         (DENY > HOLD > CLARIFY > ALLOW — deterministic)
  → local capability   (deterministic solvers, zero tokens)
  → memory / Brody interface   (public stubs in this cut)
  → Fireworks only if needed   (cheapest sufficient model, compressed prompt,
                                bounded completion budget)
  → bounded output / metrics   (strict contract, receipts, replay surfaces)
```

- **UnifiedInputIR** — every natural-language request is compiled into a
  structured intent before anything else happens.
- **Gates** — world actions (push, deploy, rm -rf, bypass attempts) are held
  or denied at level 0. A model is never consulted about whether to act.
- **Local deterministic solvers** — factual, math, sentiment, NER, code
  debugging, logic tasks that match a verified fingerprint close locally at
  zero tokens.
- **Memory / Brody** — public interface stubs; the full private layers stay
  out of this cut.
- **Fireworks escalation** — only when structure is insufficient. The prompt
  is stripped of noise (`track1_prompt_compressor`), the completion budget is
  capped per answer kind (`build_compact_override`), and the model comes from
  the harness-provided ladder.
- **Output contract** — strict `[{"task_id", "answer"}]` projection; internal
  telemetry never leaks into the judged output.
- **Global Obsidia stack** — not fully active in this repository (see
  "Real vs stubbed" below).

A good answer is not always a long answer. It can be: *I don't know*, *X is
missing*, *action not authorized*, *clarification required*, *HOLD*,
*commands-only*. Zero tokens spent, frame respected.

## Track 1 compliance

| Requirement | Status |
|---|---|
| Publicly pullable image | ✅ `ghcr.io/eaubin08/obsidia-router:track1` — anonymous pull verified |
| linux/amd64 | ✅ built with `--platform linux/amd64` |
| Reads `/input/tasks.json` at startup | ✅ default official runner path |
| Writes `/output/results.json` before exit | ✅ verified in GHCR run |
| Strict output schema `[{"task_id","answer"}]` | ✅ `TRACK1_OUTPUT_VALIDATION = PASS` |
| Exit code 0 on success | ✅ verified |
| Runtime < 10 min, startup < 60 s, per-answer < 30 s | ✅ practice run completes in seconds; per-call timeouts bounded by the runtime budget |
| Answers in English | ✅ enforced by contract prompts |
| No hardcoded / cached answers | ✅ answers derive from request signals; no task-ID branching, no answer tables |
| Env vars from harness | ✅ `FIREWORKS_API_KEY`, `FIREWORKS_BASE_URL`, `ALLOWED_MODELS` read dynamically |
| All Fireworks calls via `FIREWORKS_BASE_URL` | ✅ single adapter authority (`app/adapters/fireworks.py`) |
| Models only from `ALLOWED_MODELS` | ✅ single parsing authority; no hardcoded model IDs in the call path |
| Local solvers count zero tokens | ✅ 0 tokens on all local closures |
| ZERO_API_CALLS valid if accuracy passes | ✅ practice: 8/8 correct at 0 API calls |
| No secrets in image | ✅ selective COPY + `.dockerignore`; no `.env`, keys, results or receipts |

## Key numbers at a glance

- **Official practice path**: 8/8 correct, 0 Fireworks tokens, 0/8 remote calls.
- **Submitted Docker path**: public GHCR image, strict output schema, 8/8 practice tasks, exit 0.
- **Internal routing benchmark**: 18/18 accepted routes, 18/18 baseline remote calls avoided, 5584 estimated tokens saved.
- **Dynamic invariants**: 180/180 bounded variants and 160/160 dirty variants held at 0 tokens.
- **V3B stack routing**: 15/15 routes, no real action, no memory write, no kernel mutation.
- **Frontier suite**: 15 local closures, 12 frontier/escalation cases, 8 governed paths, 0 false local closures.
- **Live frontier compression**: 4265 → 2650 → 2438 real Fireworks tokens, same routes, 9 paid calls.
- **Hidden AMD judge**: unknown and external.

Frontier live detail: 9 real paid Fireworks calls in the observed live run,
mean ≈271 tokens per remote call, median 275. Level-0 rate on the internal
benchmark: 61%.

## Why the frontier matters

**The frontier benchmark is not trying to close everything locally. It
proves that Obsidia knows when to stop, when to govern, and when to pay for
inference.**

If every task closed locally, the result would look like hardcoding or
overfit. The 35-task frontier suite proves the opposite:

- **Unsupported and open-world cases do not get forced into local answers**:
  12 enter the frontier/escalation bucket, 8 are governed, and in the
  observed live run 9 became real paid Fireworks calls.
- **`false_local_closures = 0` is the safety proof**: no local solver ever
  answered a task outside its verified fingerprint just to save tokens.
- **Correct abstentions are a feature, not a failure** (10 correct local-only
  abstentions): the router knows the boundary of its own competence.
- Break-even complexity level: 4 — below it, deterministic structure wins;
  above it, remote inference is genuinely needed and is called with a
  compressed prompt and a capped budget.

The live compression sequence (4265 → 2650 → 2438 tokens) shows the two
distinct savings Obsidia produces:

1. **Fewer remote calls** when deterministic structure is sufficient;
2. **Cheaper remote calls** when inference is still necessary — same routes,
   same zero false closures, lower spend.

## What is real vs stubbed

**Real in this public Track 1 cut:**

| Component | Status |
|---|---|
| UnifiedInputIR, gates, topic router, level decision | Real — extracted and adapted from the Obsidia X-108 terminal |
| Local deterministic solvers | Real — fingerprint-bounded, zero token |
| Official resolver (`benchmarks/official_resolver.py`) | Real — single resolution authority for the judged path |
| Model triage (`app/router/model_triage.py`) | Real — single model-selection authority |
| Fireworks adapter | Real — OpenAI-compatible; dry-run without credentials |
| Prompt compression for remote calls (`track1_prompt_compressor.py`) | Real — strips noise, never adds content |
| Docker harness | Real — the judged image is the one documented here |
| Metrics and reports | Real — computed from existing records, zero extra calls |

**Stubbed / minimal:**

| Component | Status |
|---|---|
| Brody (proprietary local organ) | Stubbed — interface and contract kept; weights and private layers stay out |
| Memory index | Minimal example — demonstrates level-2 lookup mechanics |
| Obsidure / Lean / Sigma / OIE / domain bridges | Routing surfaces only — no private runtime |

**Not included:** the full private Obsidia OS, the full X108 kernel runtime,
private memories, connectors and domains.

Why: none of this is required for Track 1; it protects proprietary layers;
and Track 3 presents the larger thesis **without pretending the full stack is
active inside the Docker image**.

## Quick start

Stdlib-only Python 3.12 — nothing to install.

```bash
# one request with full routing trace
python -m app.cli "explique le contexte de cette decision"

# tests (static + dynamic bounded invariant tests)     [SAFE, zero token]
python -m pytest -q
# expected: 1230 passed, 3 skipped

# AMD practice category accuracy                        [SAFE, zero token]
python benchmarks/answer_accuracy.py
# expected: overall 8/8 PASS, total_tokens_amd = 0

# official judge path on the 8 practice tasks           [SAFE without key]
python scripts/run_official.py --input submission/track1/input/practice_tasks.json --output submission/track1/output/results.json
python submission/track1/validate_output.py submission/track1/input/practice_tasks.json submission/track1/output/results.json
# expected: TRACK1_OUTPUT_VALIDATION = PASS, 8/8 answers, strict schema

# main internal benchmark                               [SAFE, zero token]
python benchmarks/run_benchmark.py --track1-official --stack-v3b
# expected: 18/18 route accuracy, 0 tokens, 0 remote

# frontier boundary map (dry)                           [SAFE, zero token]
python benchmarks/run_frontier_benchmark.py
# expected: 15 local / 12 frontier-escalation / 8 governed, false_local_closures = 0
```

⚠ **Commands that spend Fireworks tokens** (`--live-baseline`,
`--random-compare`, `run_frontier_benchmark.py --live`, `probe_ladder.py`,
smoke tests without `--dry-run`) are documented in
[docs/BENCHMARKS.md](docs/BENCHMARKS.md) and must be run deliberately —
never as part of an automatic validation pack.

## Docker

Final submission images (public, anonymous pull verified):

- Pinned: `ghcr.io/eaubin08/obsidia-router:track1-0a5fc69`
- Latest: `ghcr.io/eaubin08/obsidia-router:track1`

The container runs the **official path** (`scripts/run_official.py`), not
pytest: it reads `/input/tasks.json`, writes `/output/results.json`, exits 0.

Linux / macOS:

```bash
docker pull ghcr.io/eaubin08/obsidia-router:track1-0a5fc69
docker run --rm \
  -v "$PWD/submission/track1/input/practice_tasks.json:/input/tasks.json:ro" \
  -v "$PWD/submission/track1/output:/output" \
  ghcr.io/eaubin08/obsidia-router:track1-0a5fc69
```

Windows PowerShell:

```powershell
docker pull ghcr.io/eaubin08/obsidia-router:track1-0a5fc69
docker run --rm `
  -v "${PWD}\submission\track1\input\practice_tasks.json:/input/tasks.json:ro" `
  -v "${PWD}\submission\track1\output:/output" `
  ghcr.io/eaubin08/obsidia-router:track1-0a5fc69
```

Live-compatible run (⚠ spends Fireworks tokens when a real key is present):
add `-e FIREWORKS_API_KEY=... -e FIREWORKS_BASE_URL=... -e ALLOWED_MODELS=...`
— in the official evaluation, the harness injects these variables.

The image ships only the evaluated Track 1 slice (`app/`, the official runner
and its contract modules including the prompt compressor). Benchmarks, tests
and the interactive demo run from the repository, not from the container.

Full judge-path reproduction guide (exit codes, output contract):
[docs/TRACK1_SUBMISSION.md](docs/TRACK1_SUBMISSION.md)

## Environment variables

| Variable | Required | Purpose |
|---|---|---|
| `FIREWORKS_API_KEY` | for live calls | Without it, level-3 decisions run in dry-run mode (route + token estimate, no network). No key = local-only behavior on paths that don't require Fireworks. |
| `FIREWORKS_BASE_URL` | no | Defaults to `https://api.fireworks.ai/inference/v1`. **All** Fireworks calls go through this URL — the scoring harness may override it. |
| `ALLOWED_MODELS` | no | Ordered allowlist read dynamically at runtime; the router picks the smallest sufficient rung of *this exact order*. The router never hardcodes model IDs in the call path and never calls a model outside this list when it is provided. |

## Metrics

`benchmarks/run_benchmark.py` writes `results/benchmark_report.json` and a
judge-readable one-pager `results/REPORT.md`:

- **Track 1**: fireworks_calls, fireworks_tokens, avg latency, route accuracy
- **Obsidia**: no_model_needed, commands_only_hold, denied,
  clarification_needed, memory_hits, brody_needed, fireworks_needed,
  remote_calls_avoided, estimated_tokens_saved, level0_rate

**Prompt compression metrics** (recorded on every remote call):
`estimated_prompt_tokens`, `completion_budget`, `over_300`, `compact_profile`,
`prompt_chars_before` / `prompt_chars_after`, `compression_ratio`,
`citer_used`.

**Model triage evidence** — every remote record carries three distinct
fields, never conflated: `selected_model` (chosen by the single triage
authority, always the model transmitted to `fireworks.chat()`),
`actual_model_used` (captured on the transport call; equal by construction,
kept for audit), and `contract_model_preference` (informative telemetry only,
never selects the call target). Rung position is reported as a call count,
never converted into a token or dollar saving, because the `ALLOWED_MODELS`
order is stated by the harness, not independently cost-verified.

## Known limits

- The hidden AMD judge score is unknown and external; nothing here claims it.
- Deterministic solvers are fingerprint-bounded: they close only what they
  can verify, and abstain otherwise (by design).
- This public cut is not the full Obsidia OS; Brody is stubbed and memory is
  minimal.
- Frontier live token values can vary between runs (remote generation,
  model/runtime variance); routes and the zero-false-closure invariant are
  the stable claims.
- No claim is made that Obsidia is a larger or better LLM — the comparison
  is between two execution strategies (direct model calls vs pre-inference
  governance), not between models.

## Submission assets

- Track 1 reproducible path: [docs/TRACK1_SUBMISSION.md](docs/TRACK1_SUBMISSION.md)
- Benchmark matrix (SAFE vs LIVE spend): [docs/BENCHMARKS.md](docs/BENCHMARKS.md)
- Track 3 / narrative: [docs/TRACK3_SUBMISSION.md](docs/TRACK3_SUBMISSION.md)
- Track 3 metric claims: [docs/TRACK3_METRICS.md](docs/TRACK3_METRICS.md)
- Demo script (safe by default): [docs/DEMO.md](docs/DEMO.md)
- Demo video and slide decks: submitted separately.

## License

Source-available proprietary license — see [LICENSE](LICENSE).

This repository is public for AMD Developer Hackathon evaluation, technical
review, and reproducibility of the documented benchmark and Docker paths.
Public access does not grant open-source reuse rights.
