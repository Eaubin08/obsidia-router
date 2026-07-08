# Obsidia Router — Semantic Routing Before Inference

> A deterministic pre-inference layer that decides whether a model is needed
> **before** spending tokens.

**Track 1** (token-efficient agent) — AMD Developer Hackathon: ACT II.
Narrative extends to Track 3: this router is a visible slice of a larger
cognitive OS where the LLM is an **organ**, not the brain.

## The thesis

Classic agents route **between** models. Obsidia first decides **if** a model
is necessary. Every request is compiled into a structured intent
(UnifiedInputIR), checked against deterministic gates and invariants, and only
then — if the structure is not enough — escalated to the cheapest sufficient
Fireworks model.

```
natural language
  → IR (intent / layer / action / risk / needs)        deterministic
  → gates (DENY > HOLD > CLARIFY > ALLOW)               deterministic
  → topic routing                                       deterministic
  → inference level decision:
      Level 0  NO MODEL   status, HOLD, deny, clarification, commands-only
      Level 1  BRODY      local proprietary LLM organ (stubbed in this cut)
      Level 2  MEMORY     corpus lookup, no generation
      Level 3  FIREWORKS  cheapest sufficient model on the ladder
```

A good answer is not always a long answer. It can be: *I don't know*, *X is
missing*, *action not authorized*, *clarification required*, *HOLD*,
*commands-only*. Zero tokens spent, frame respected.

## Parametric efficiency

Track 1 measures token efficiency. Obsidia also reports parametric efficiency: how much task competence can be produced before carrying or calling a large learned model.

This public Track 1 cut embeds 0 GB of learned model weights. Brody is stubbed, memory is minimal, and Fireworks is used only when the deterministic structure cannot close the task locally.

## Quick start

Stdlib-only Python 3.12 — nothing to install.

```bash
# one request with full routing trace
python -m app.cli "explique le contexte de cette decision"

# interactive loop ('metrics' prints live counters)
python -m app.cli

# tests (static + dynamic bounded invariant tests)
python -m pytest tests/ -q

# benchmark: obsidia routing vs direct-to-model baseline (estimated tokens)
python benchmarks/run_benchmark.py

# MEASURED head-to-head: all 18 tasks really sent raw to the cheapest
# Fireworks model (classic-agent arm) vs the full Obsidia stack.
# Requires FIREWORKS_API_KEY, spends real credits, real request_ids.
python benchmarks/run_benchmark.py --live-baseline

# every run also executes the DYNAMIC BOUNDED PHASE: a seeded generator
# composes variations never written down in advance (default 30/family,
# 180 cases) and asserts the frame holds on all of them, at 0 token cost.
python benchmarks/run_benchmark.py --dynamic 100   # 600 generated cases
```

### Docker (required for submission)

```bash
docker build -t obsidia-router .
docker run obsidia-router                                   # benchmark, dry-run
docker run -e FIREWORKS_API_KEY=... obsidia-router          # live Fireworks calls
docker run -it obsidia-router python -m app.cli             # interactive demo
```

## Environment variables

| Variable | Required | Purpose |
|---|---|---|
| `FIREWORKS_API_KEY` | for live calls | Without it, level-3 decisions run in dry-run mode (route + token estimate, no network). |
| `FIREWORKS_BASE_URL` | no | Defaults to `https://api.fireworks.ai/inference/v1`. Scoring harnesses may override. |
| `ALLOWED_MODELS` | no | Comma-separated model ladder, cheapest first. Overrides the default gpt-oss-120b → GLM 5.1 → DeepSeek V4 Pro ladder (check the current serverless catalog via `GET /v1/models`). |

## Metrics

`benchmarks/run_benchmark.py` writes `results/benchmark_report.json` and a
judge-readable one-pager `results/REPORT.md` (headline metrics + governance
table: what the raw model answered to dangerous/ambiguous requests vs the
Obsidia verdict, with a deterministic frame-violation score):

- **Track 1**: fireworks_calls, fireworks_tokens, avg latency, route accuracy
- **Obsidia**: no_model_needed, commands_only_hold, denied,
  clarification_needed, memory_hits, brody_needed, fireworks_needed,
  remote_calls_avoided, estimated_tokens_saved, level0_rate

The report also regroups these existing metrics into **cognitive value
inputs** — a readonly projection of what the governed valuation layer of the
full Obsidia stack (deferred, non-token by policy) would read. Nothing is
minted, priced, or scored, and the projection does not influence Track 1
scoring, routing, or gates.

## Tests

- `tests/test_ir.py`, `test_gates.py`, `test_decision.py` — static behavior
- `tests/test_dynamic_invariants.py` — **bounded dynamic tests**: a seeded
  generator produces request variations never written down in advance and
  asserts invariants (world actions never reach a model; denied patterns
  survive rephrasing; no-auto-act/commit/push always present; escalation
  requires an ALLOW verdict).

## What is real vs simulated in this cut

| Component | Status |
|---|---|
| UnifiedInputIR, gates, topic router, level decision | **Real** — extracted and adapted from the Obsidia X-108 terminal (369 gate tests upstream). |
| Fireworks adapter | **Real** — OpenAI-compatible client; dry-run without credentials. |
| Brody (proprietary local LLM organ) | **Stubbed** — interface and contract kept; weights and private memory stay out of the public cut. |
| Memory index | **Minimal example** — demonstrates level-2 lookup mechanics. |

## Known limits

- The IR keyword tables are a deterministic heuristic slice, not the full OS.
- Brody being stubbed, level-1 answers are structural, not generative.
- Accuracy scoring against a reference set is wired via `expected_route`;
  semantic answer grading depends on the official harness.

## License

MIT — see [LICENSE](LICENSE).

## Comparison method

This project does **not** claim that Obsidia Router is a larger or better language model.

The benchmark compares two execution strategies:

| Strategy | Behavior |
|---|---|
| Direct model baseline | Every task is sent to Fireworks. |
| Obsidia Router | Every task is first compiled into IR, gate, level and route. Fireworks is called only when remote inference is actually required. |

The measured gap is therefore:

- inference avoided before model call;
- remote tokens avoided;
- governed frame violations reduced;
- escalation quality measured by route/path correctness.

The generated `results/REPORT.md` contains the current measured live numbers.
Remote token counts can vary slightly between live baseline runs because the raw
model answers are generated remotely.

Stable comparison axes reported by the benchmark:

| Metric | Direct model baseline | Obsidia Router |
|---|---:|---:|
| Remote model calls | 18 | 3 |
| Governed frame violations | measured live | measured live |
| Route accuracy | — | 100% |

Path quality, speed profile and escalation quality are reported as separate axes. No global quality score is introduced.
