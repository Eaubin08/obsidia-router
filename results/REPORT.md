# Obsidia Router — Benchmark Report

> Obsidia is not compared as a larger model. Obsidia is compared as an
> inference-avoidance and governance layer.

## Headline metrics

| Metric | Baseline (direct model) | Obsidia | Gain |
|---|---:|---:|---:|
| Remote calls | 18 | 3 | 83% avoided |
| Remote tokens (estimated) | 5584 | 75 | 99% saved |
| Frame violations (governed tasks) | n/a (needs --live-baseline) | 0/8 | governed |
| Route accuracy | — | 100% | — |
| No-model resolution rate (level 0) | 0% | 61% | — |

- Tasks: 18 across 8 families (status, IR, world actions, destructive, ambiguous, memory, local organ, remote reasoning)
- Distribution: 3 no-model, 4 HOLD, 2 denied, 2 clarify, 2 memory, 2 brody, 3 fireworks
- Invariants: no_auto_act / no_auto_commit / no_auto_push respected on every task (asserted by dynamic bounded tests)
- Avg routing latency: sub-millisecond deterministic pipeline; remote calls avg 0.0s
- Model ladder (cheapest sufficient): accounts/fireworks/models/gpt-oss-120b, accounts/fireworks/models/glm-5p1, accounts/fireworks/models/deepseek-v4-pro

## Governance table — governed tasks, side by side

_Run with `--live-baseline` to capture what the raw model actually answers to dangerous/ambiguous requests._

## Dynamic bounded phase — the test invents, Obsidia holds the frame

Seeded generator (seed 108): **180 variations** composed from prefix x core x suffix templates — never written down individually — run through the deterministic pipeline at zero token cost.

| Family | Held | Routes observed |
|---|---:|---|
| world_action | 30/30 | hold_commands_only=30 |
| destructive | 30/30 | denied=30 |
| status_no_model | 30/30 | no_model_needed=30 |
| ambiguous | 30/30 | clarification_needed=30 |
| question_local_organ | 30/30 | brody=30 |
| remote_reasoning | 30/30 | fireworks=30 |

**Invariants held: 180/180 (100%)** — 0.04 ms per decision, ~24710 decisions/second.

- world_actions_never_reach_model: **60/60** (families: world_action, destructive)
- no_auto_act respected: yes — on every generated case
- no_auto_commit respected: yes — on every generated case
- no_auto_push respected: yes — on every generated case
- route stability under variations: routes observed match the expected family sets on 180/180 cases (level-0 families: world_action, destructive, status_no_model, ambiguous)

## Latency

| Path | Latency |
|---|---:|
| Local deterministic decision (levels 0-2) | 0.083 ms avg |
| Fireworks remote call (level 3) | 0.0 s avg |
| Dynamic phase throughput | ~24710 decisions/s |

## Cognitive value inputs (readonly projection)

Existing benchmark metrics, regrouped as the inputs a governed
cognitive-value ledger would read. The valuation layer lives in the
full Obsidia stack, readonly/advisory, **deliberately deferred**, and
is governed upstream by a NOT_A_TOKEN policy. Nothing here is a new
score; every value is copied verbatim from the metrics above.

| Input group | Values (existing metrics) |
|---|---|
| avoided_inference | tokens_baseline=5584, tokens_obsidia=75, estimated_tokens_saved=4609, remote_calls_avoided=15, level0_rate=0.611 |
| frame_stability | baseline_violations=n/a, obsidia_violations=0, governed_tasks=8, invariants_held_rate=1.0 |
| time_cost | avg_routing_ms_local=0.083, avg_fireworks_call_s=0.0 |
| control | route_accuracy=1.0, gate_verdict_distribution={'ALLOW': 8, 'HOLD': 4, 'DENY': 2, 'CLARIFY': 4} |

Boundary: projection=readonly, mint=False, wallet=False, blockchain=False, economic_scoring=False, decision_authority=KX108_ONLY — DEFERRED — inputs only; valuation layer lives upstream.
This projection does not influence Track 1 scoring, routing, or gates.

## Reading

The token savings are a consequence, not the mechanism. The mechanism is
that Obsidia compiles each request into a governable structure (IR ->
gates -> topic -> inference level) and only escalates to Fireworks when
remote inference is actually required. A good answer is sometimes: HOLD,
commands-only, clarification, or refusal — at zero token cost.

Reproduce: `python benchmarks/run_benchmark.py [--live-baseline]` or `docker run [-e FIREWORKS_API_KEY=...] obsidia-router`.