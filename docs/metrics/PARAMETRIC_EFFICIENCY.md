# Parametric efficiency — Obsidia Track 1

## Token efficiency vs parametric efficiency

**Token efficiency** measures how many remote tokens are avoided compared to
a direct-model baseline. This is the primary Track 1 metric.

**Parametric efficiency** measures how much task competence can be produced
_before_ carrying or calling a large learned model. It answers the question:
how much does the stack embed?

## Zero embedded model weight

This public Track 1 cut embeds **0 GB of learned model weights**.

- No `.gguf`, `.ckpt`, `.safetensors`, `.pt`, or `.bin` model files are
  present in the repo.
- No persistent vector memory is loaded or required at runtime.
- No local inference engine is bundled.

The stack measures competence from deterministic structure alone: IR
compilation, gates, topic routing, and inference level selection — all
without a local LLM.

## Deterministic structure before inference

Most tasks are resolved locally with zero Fireworks calls: status queries,
governed world actions (hold / deny / clarify), and recognized deterministic
structures. Local paths cost 0 remote tokens.

## Fireworks single choke point

All remote inference passes through `app/adapters/fireworks.py`. No other
file calls an external model. This makes token tracking exact and auditable.
Every remote call is bounded: the completion budget and the system contract
are fixed before generation, from request signals only — `task_id` is never
used as decision logic.

## Calibration note

Exact per-model calibration details (natural completion lengths, budget
derivation, model inclusion/exclusion analysis) are intentionally not part
of the public evaluation narrative. The figures in this repository are
specific to the public Track 1 cut, not the full private Obsidia stack.

## No authority — report only

`parametric_efficiency` and `footprint` fields in `benchmark_report.json`
are **report-only**. They have zero influence on routing decisions, gate
verdicts, inference level selection, model ladder selection, or Track 1
scoring. `decision_authority` remains `"KX108_ONLY"` on every task.

## Summary table

| Metric | Value |
|---|---|
| Embedded model weights | 0 GB |
| Local model files | 0 |
| Persistent memory required | false |
| Fireworks single choke point | true |
| Remote calls bounded before generation | true |
