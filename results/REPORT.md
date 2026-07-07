# Obsidia Router — Benchmark Report

> Obsidia is not compared as a larger model. Obsidia is compared as an
> inference-avoidance and governance layer.

## Headline metrics

| Metric | Baseline (direct model) | Obsidia | Gain |
|---|---:|---:|---:|
| Remote calls | 18 | 3 | 83% avoided |
| Remote tokens (measured) | 184 | 75 | 59% saved |
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

## Reading

The token savings are a consequence, not the mechanism. The mechanism is
that Obsidia compiles each request into a governable structure (IR ->
gates -> topic -> inference level) and only escalates to Fireworks when
remote inference is actually required. A good answer is sometimes: HOLD,
commands-only, clarification, or refusal — at zero token cost.

Reproduce: `python benchmarks/run_benchmark.py [--live-baseline]` or `docker run [-e FIREWORKS_API_KEY=...] obsidia-router`.