# Parametric efficiency — Obsidia Track 1

## Token efficiency vs parametric efficiency

**Token efficiency** measures how many remote tokens are avoided compared to a direct-model baseline. This is the primary Track 1 metric.

**Parametric efficiency** measures how much task competence can be produced _before_ carrying or calling a large learned model. It answers the question: how much does the stack embed?

## Zero embedded model weight

This Track 1 cut embeds **0 GB of learned model weights**.

- No `.gguf`, `.ckpt`, `.safetensors`, `.pt`, or `.bin` model files are present in the repo.
- No persistent vector memory is loaded or required at runtime.
- No local inference engine (llama.cpp, onnxruntime, etc.) is bundled.

The stack measures competence from deterministic structure alone: IR compilation, gates, topic routing, and inference level selection — all without a local LLM.

## Remote calls avoided

Most tasks are resolved locally with zero Fireworks calls:

- `no_model_needed` — status, simple queries
- `hold_commands_only` — world actions that require human approval
- `denied` — out-of-frame requests
- `clarification_needed` — ambiguous requests missing required context
- `memory_hit` — corpus lookup at level 2

Only level-3 tasks escalate to Fireworks. Fireworks is a single choke point — the only place where remote tokens are spent.

## Fireworks single choke point

All remote inference passes through `app/adapters/fireworks.py`. No other file calls an external model. This makes token tracking exact and auditable.

## Remote answer contract — pre-generation cadrage

Before any Fireworks call (Track 1 official mode), a `remote_answer_contract` is built from request signals:

- `language` — French or English, detected from accents and keywords
- `answer_kind` — `comparison` / `structured_summary` / `code_file` / `direct_answer`
- `max_tokens` — calibrated budget applied before generation
- `model_preference` — `gpt-oss-120b` (calibrated by quality_discovery_v1)
- `contract_prompt` — suppresses meta-reasoning, planning, and "The user asks" preambles

The contract is built from request signals only. `task_id` is never used as decision logic for answer_kind, max_tokens, or model_preference.

## Model matrix calibration (quality_discovery_v1)

Budgets are set by observed natural completion lengths, not by intuition:

| Contract | Natural (gpt-oss) | +15% recommend | Final budget |
|---|---:|---:|---:|
| comparison | 561 tokens | 646 | **850** |
| structured_summary | 611 tokens | 703 | **900** |
| code_file | 1155 tokens | 1329 | **1700** |

### Model decisions

| Model | Status | Reason |
|---|---|---|
| `gpt-oss-120b` | **default** | 5/5 OK in quality_discovery_v1, no meta-reasoning |
| `glm-5p1` | excluded | hardwired "Analyze the Request" template, language failure, code_only failure |
| `deepseek-v4-pro` | excluded (default) | 2/3 timeout at 60s in quality discovery |
| `glm-5p2` | code candidate only | OK on code_file, still truncated on comparison and summary at 1200 tokens |
| Gemma | unavailable | absent from current Fireworks catalog |

## Brody stubbed

Brody (the proprietary local LLM organ) is stubbed in this cut. Interface and contract are present; weights and private memory are not included. Level-1 answers are structural, not generative.

`brody_live_enabled` is `False` unless `BRODY_ENDPOINT` is set in the environment.

## Persistent memory not required

Memory lookup (level 2) uses a minimal static index (`examples/memory_index.json`). No vector database, no persistent memory store, and no embedding model are required.

## No authority — report only

`parametric_efficiency` and `footprint` fields in `benchmark_report.json` are **report-only**. They have zero influence on:

- routing decisions
- gate verdicts
- inference level selection
- model ladder selection
- Track 1 scoring

`KX108_ONLY` is unchanged. `decision_authority` remains `"KX108_ONLY"` on every task.

## Summary table

| Metric | Value |
|---|---|
| Embedded model weights | 0 GB |
| Local model files | 0 |
| Persistent memory required | false |
| Brody full memory | disabled / stub |
| Fireworks single choke point | true |
| Budget calibration source | quality_discovery_v1 |
| Default model | gpt-oss-120b |
| Contract version | track1_remote_answer_contract_v0 |
| Budget headroom policy | human_margin_high_v0 |
