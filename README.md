# Obsidia Router — Structure Before Inference

> Most routers optimize **which** model to call.
> Obsidia first decides **whether a model call is necessary**.

Obsidia is a governed intelligence architecture that separates structural
verification, model inference and action authority.

For AMD ACT II, one public system supports two complementary tracks:
Track 1 measures token-efficient routing; Track 3 presents the broader
architecture that makes this behavior possible.

This repository is not a claim that Obsidia is a bigger or better LLM. It
demonstrates that a deterministic governance layer placed before inference
can reduce both the **number** of remote calls and the **cost** of the
calls that remain, while preserving zero false local closures on the
measured frontier suite.

<a id="start-here"></a>

## Start here

| I want to... | Go directly to |
|---|---|
| Understand the project in one minute | [Two tracks, one system](#two-tracks) |
| Review the measured Track 1 results | [Track 1 evidence](#track1-evidence) |
| Run the exact Docker submission proof | [Track 1 Docker proof](#track1-docker-proof) |
| Inspect the inference-layer distribution | [Model-layer metrics](#model-layer-metrics) |
| Understand when Fireworks is necessary | [Frontier benchmark](#track1-frontier) |
| Explore the broader Obsidia vision | [Track 3 architecture](#track3) |
| Reproduce all public evidence | [Reproduction guide](#reproduce) |
| Check public vs proprietary boundaries | [Public and private scope](#public-private) |

The fastest verification path is the
[Track 1 Docker proof](#track1-docker-proof): pull the public image, run the
official input/output contract, and validate the result.

<a id="two-tracks"></a>

## Two tracks, one system

| Track | Question | Public proof |
|---|---|---|
| Track 1 — Token-Efficient Routing | When is a remote model call actually necessary? | Router, Docker path, local solvers, governed escalation and measured token efficiency |
| Track 3 — Intelligence Before Inference | What architecture can govern cognition, decision and action before execution? | Broader Obsidia thesis, distributed intelligence, authority boundaries and product direction |

Track 1 measures the mechanism. Track 3 explains the system design behind it.

---

<a id="track1"></a>

## Track 1 — Measured Token-Efficient Routing

Track 1 evaluates the public and reproducible cut of Obsidia. Each request
is compiled into a bounded structure, checked by deterministic gates,
resolved locally when possible, and escalated to Fireworks only when
inference remains necessary. The public cut is deliberately limited to what
Track 1 evaluates: routing, gates, local solvers, the official runner, the
Fireworks adapter, and the Docker harness.

### How the public cut works

```
Request
  → UnifiedInputIR
  → Deterministic gates
  → Local solver or minimal memory
  → Bounded Fireworks escalation when required
  → Strict answer contract and audit metadata
```

- **UnifiedInputIR** compiles every request into a structured intent before
  anything else happens.
- **Gates** hold or deny world actions such as push, deploy, destructive
  deletion or bypass attempts. In the public evaluation path, action
  authority is resolved deterministically before any model call.
- **Local solvers / minimal memory** close factual, math, sentiment, NER,
  code and level-2 lookup tasks that match a verified fingerprint, at zero
  tokens.
- **Fireworks escalation** only fires when structure is insufficient: the
  prompt is stripped of noise, the completion budget is capped per answer
  kind, and the model comes from the harness-provided `ALLOWED_MODELS`
  ladder.
- **Output contract** projects a strict `[{"task_id", "answer"}]` result;
  internal telemetry never leaks into the judged output.

A good answer is not always a long answer. It can be *I don't know*, *X is
missing*, *action not authorized*, *clarification required*, *HOLD*,
*commands-only* — zero tokens spent, frame respected.

`KX108_ONLY` means the public stack exposes the kernel-authority surface
only: the benchmark may route across Brody/Obsidure/Lean/domain surfaces,
but it does not enable real actions, memory writes, or kernel mutation. The
broader private components are introduced in [Track 3](#track3).

<a id="track1-evidence"></a>

### Headline evidence

| Proof | Result | Meaning |
|---|---:|---|
| Test suite | 1233 passed | Public evaluation cut is internally consistent |
| AMD practice surface | 8/8, 0 remote, 0 tokens | Practice categories close locally |
| Internal routing | 18/18 accepted routes | Every route matched an accepted path, 5584 est. tokens saved |
| Level-0 rate | 11/18 = 61.1% | Resolved or governed before any model layer |
| Before memory or remote inference | 16/18 = 88.9% | Level 0 structure or deterministic Level 1 solvers |
| Internal remote calls | 0/18 | All baseline remote calls avoided on this INTERNAL_DRY set |
| Frontier safety | 0 false local closures | No solver answered outside its verified fingerprint |
| Live compression | 4265 → 2438 tokens | 42.8% lower observed spend across 9 paid calls, routes unchanged and false local closures remained zero |
| V3B routes | 15/15 | Route-only surfaces preserved KX108_ONLY boundaries |
| Hidden AMD judge | Unknown | External official evaluation |

This README does not report one global intelligence score — it reports a
proof ladder. Each row above measures a different property: code
correctness, route correctness, remote calls avoided, token spend,
governance safety, and live cost compression. `61.1%`, `88.9%` and the
internal `0` remote calls belong exclusively to the 18-task `INTERNAL_DRY`
benchmark; the 9 paid calls and `4265 → 2438` belong to the `LIVE_FRONTIER`
run. They must not be merged.

<a id="model-layer-metrics"></a>

### Inference-layer distribution

| Layer | Tasks | Share | Meaning |
|---|---:|---:|---|
| Level 0 — structural pre-inference | 11/18 | 61.1% | Resolved or governed before any model layer |
| Level 1 — deterministic local solvers | 5/18 | 27.8% | Closed by bounded local capabilities, without remote inference |
| Level 2 — minimal memory lookup | 2/18 | 11.1% | Resolved through the public cut's minimal memory index |
| Level 3 — Fireworks inference | 0/18 | 0% | No remote model call was required on this INTERNAL_DRY benchmark |

Level 0 breaks down into three structural resolutions (`no_model_needed`:
3), four HOLD verdicts (`hold_commands_only`: 4), two DENY verdicts
(`denied`: 2) and two CLARIFY verdicts (`clarification_needed`: 2).

Level 0 is both an efficiency layer and a governance layer. Avoiding
inference does not always mean answering: it can mean HOLD, DENY or
CLARIFY. In this benchmark the 5 Level-1 tasks were closed by deterministic
local solvers, not by a live Brody call, and Level 2 is the public cut's
minimal memory index, not the full private memory.

<a id="track1-frontier"></a>

### Frontier: when inference earns its cost

The frontier suite (35 tasks) checks whether Obsidia knows when to stop,
govern, or escalate — not whether it can close everything locally. If every
task closed locally, that would look like overfitting instead of judgment.

- **15 local closures**, **8 governed paths** (hold/deny/clarify), and
  **12 frontier/escalation cases** where the router should not force a
  local answer.
- In the observed live run, **9** of those became real paid Fireworks
  calls, compressed from **4265** to **2650** (compact system prompts,
  tighter completion budgets) to **2438** tokens (final prompt-hygiene
  pass) — mean ≈271 tokens/call, median 275. Routes were unchanged and
  false local closures stayed 0.
- `false_local_closures = 0` is the safety proof: no local solver ever
  answered outside its verified fingerprint to save tokens.
- **10 correct local-only abstentions**: the router knows the boundary of
  its own competence. In the current frontier suite, the observed
  transition appears around complexity level 4: lower-complexity tasks are
  generally handled by bounded local structure, while higher-complexity
  cases more often require escalation.

The goal is not to close everything locally. The goal is to know when to
verify, when to govern, when to abstain and when inference earns its cost.

### Official submission path

| Requirement | Status |
|---|---|
| Publicly pullable image | ✅ anonymous pull verified |
| linux/amd64 | ✅ built with `--platform linux/amd64` |
| Reads `/input/tasks.json` at startup | ✅ default official runner path |
| Writes `/output/results.json` before exit | ✅ verified in GHCR run |
| Strict output schema `[{"task_id","answer"}]` | ✅ `TRACK1_OUTPUT_VALIDATION = PASS` |
| Exit code 0 on success | ✅ verified |
| Runtime < 10 min, startup < 60 s, per-answer < 30 s | ✅ practice run completes in seconds |
| Answers in English | ✅ enforced by contract prompts |
| No hardcoded / cached answers | ✅ derived from request signals; no task-ID branching |
| Env vars from harness | ✅ `FIREWORKS_API_KEY`, `FIREWORKS_BASE_URL`, `ALLOWED_MODELS` read dynamically |
| All Fireworks calls via `FIREWORKS_BASE_URL` | ✅ single adapter authority (`app/adapters/fireworks.py`) |
| Models only from `ALLOWED_MODELS` | ✅ single parsing authority; no hardcoded model IDs |
| Local solvers count zero tokens | ✅ 0 tokens on all local closures |
| ZERO_API_CALLS valid if accuracy passes | ✅ practice: 8/8 correct at 0 API calls |
| No secrets in image | ✅ selective COPY + `.dockerignore` |

<a id="track1-docker-proof"></a>

### Track 1 Docker proof

This is the shortest independent verification path. It uses the same public
container, input location, output location and strict schema expected by
the official Track 1 evaluation harness.

| Submission artifact | Verified value |
|---|---|
| Public image | `ghcr.io/eaubin08/obsidia-router:track1-0a5fc69` |
| OCI index digest | `sha256:4339cd0d3a952cdc065e9223d441f623ed846ae451e09fa60f2743a73f5daa25` |
| Platform | `linux/amd64` |
| Input | `/input/tasks.json` |
| Output | `/output/results.json` |
| Output schema | Strict `[{"task_id","answer"}]` |
| Practice result | 8 tasks, 8 answers, 0 remote calls, 0 Fireworks tokens |
| Process result | Exit code 0 |
| Anonymous pull | Verified |

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

Validate the output strictly:

```bash
python submission/track1/validate_output.py \
  submission/track1/input/practice_tasks.json \
  submission/track1/output/results.json
```

```powershell
python .\submission\track1\validate_output.py `
  .\submission\track1\input\practice_tasks.json `
  .\submission\track1\output\results.json
```

Expected output:

```text
8 input tasks
8 output answers
0 missing answers
0 extra answers
0 empty answers
TRACK1_OUTPUT_VALIDATION = PASS
exit code = 0
```

The practice input closes locally and therefore spends zero Fireworks
tokens. The official hidden harness may inject a Fireworks key and
different tasks; its result remains external and unknown. This Docker
proof is not a validation of the hidden AMD judge score.

Live-compatible run (⚠ spends Fireworks tokens when a real key is present):
add `-e FIREWORKS_API_KEY=... -e FIREWORKS_BASE_URL=... -e ALLOWED_MODELS=...`
— in the official evaluation, the harness injects these variables. The
image ships only the evaluated Track 1 slice (`app/`, the official runner
and its contract modules including the prompt compressor); benchmarks,
tests and the interactive demo run from the repository, not the container.

Full judge-path reproduction guide: [docs/TRACK1_SUBMISSION.md](docs/TRACK1_SUBMISSION.md).

[Back to Start here](#start-here)

---

<a id="track1-qwen-zero"></a>

## Zero-token Track 1 candidate

This candidate removes the Fireworks fallback entirely and replaces it with a
fully local inference path.

**Architecture:**

- Deterministic local solvers close factual, math, sentiment, NER and code
  tasks first, at zero tokens and zero remote calls — identical to the main
  Track 1 path.
- When no deterministic solver closes the task, **Qwen2.5-3B-Instruct Q4_K_M**
  (running via `llama.cpp` on the loopback at `127.0.0.1:8080`) acts as the
  local fallback. No Fireworks call is made, even when `FIREWORKS_API_KEY` is
  present.
- Every Qwen output passes through the same provider-agnostic
  `validate_remote_output` pipeline used for Fireworks answers
  (`allowed_labels`, `sentence_count`).
- If validation fails, one bounded `repair_remote_output` pass is applied;
  only the repaired output re-validates. No second model call.
- No final Fireworks fallback: tasks unresolved after the Qwen pass remain
  unresolved.

**Internal hidden-like benchmark result:**

> **127 / 128 correct — 99.2 %**
>
> This is an **internal** benchmark measured against a hidden-like task set
> prepared in this session. It is **not** the official AMD judge score, which
> is external and unknown.

**Measured local Docker validation:**

| Metric | Value |
|---|---|
| Fireworks calls | 0 |
| Fireworks tokens | 0 |
| Runtime (128 tasks) | 80 s |
| Cold startup | 49 s |
| Peak memory | 2.26 GiB |
| Compressed image | 2.11 GB |
| Architecture | linux/amd64 |

**Run command (network-isolated, AMD 4 GB target):**

```bash
docker run --rm \
  --network none \
  --memory 4g \
  --cpus 2 \
  -e FIREWORKS_API_KEY=dummy \
  -e FIREWORKS_BASE_URL=http://127.0.0.1:9 \
  -e ALLOWED_MODELS=dummy-model \
  -v <input-dir>:/input:ro \
  -v <output-dir>:/output \
  ghcr.io/eaubin08/obsidia-router:track1-qwen-zero
```

Replace `<input-dir>` with the directory containing `tasks.json` and
`<output-dir>` with the directory where `results.json` will be written.

---

<a id="track3"></a>

## Track 3 — Intelligence Before Inference

Track 1 proves that Obsidia can reduce and bound inference. Track 3 asks
the larger question: what happens when intelligence, authority and proof
are distributed across an architecture instead of being collapsed into one
model?

### The problem

Modern AI systems often delegate the entire request to a probabilistic
model too early: remote compute runs even when the route is already
structurally known, and generation, decision and action end up mixed
together with no clear boundary between proposal and execution.

Obsidia separates these functions instead of letting a single model fuse
them, so that each request can be governed, resolved or escalated on its
own terms.

### The thesis

```
Cognition → Intention → Decision → Action → Proof
```

> Obsidia does not only ask, "What answer should a model generate?" It
> first asks, "Which parts of this request require inference, which parts
> can be verified locally, and which actions are allowed to exist?"

The LLM is an organ, not the sovereign brain. A direct-model pipeline must
infer. Obsidia can sometimes verify, govern or resolve before inference.
When the route is already known, predicting can be slower than verifying.

### One request, different outcomes

- A factual request may close through a deterministic solver.
- A structurally incomplete request may trigger CLARIFY.
- An unauthorized deployment request may be held before inference.
- Only an open-ended task that survives these layers reaches a model.

The same input surface can therefore produce an answer, an abstention, a
governance verdict or a bounded model call.

### The broader architecture

```
Input
  → Unified interpretation
  → Active plan and capability resolution
  → Structures, memory, tools and model organs
  → Governance kernel
  → Bounded answer or governed action
  → Proof, receipt and replay
```

| Component | Architectural role |
|---|---|
| Unified interpretation | Converts natural input into a bounded structural representation |
| Active plan and capability resolution | Determines what capabilities are actually needed |
| Local deterministic structures | Resolve known routes without remote inference |
| Brody | Proprietary LLM organ connected to structured memory; not the memory itself |
| Memory | Provides structured, non-sovereign context |
| Obsidure | Code and implementation organ that can propose changes |
| Lean-backed proof layer | Verifies selected formal properties; it does not decide |
| Sigma | Observes coherence and can alert or freeze; it does not decide |
| Domain bridges | Translate real-world domain states into a bounded kernel-readable alphabet |
| Gates | Apply pre-execution boundaries |
| X108 kernel | Retains final decision authority |

Not all of these layers execute inside the public repository. Proposal,
proof, memory and generation remain non-sovereign — decision authority
remains `KX108_ONLY`.

### Why AMD matters

Obsidia does not replace accelerated inference. It makes accelerated
inference selective: the system reduces the number and size of requests
that reach the remote model path.

For this demonstration, Fireworks provides the bounded inference interface.
Longer term, AMD and ROCm provide a credible deployment path for specialized
model organs, without implying that the complete private Obsidia stack
already runs on that infrastructure.

### Product direction

Obsidia targets AI workflows where decisions are costly, regulated or
difficult to reverse, including financial operations, infrastructure
changes, navigation systems and enterprise agents.

Domains translate real-world states into bounded kernel-readable structures,
while connectors remain bridge-only until action authority is explicitly
granted. No certification, regulatory compliance or production deployment
is claimed beyond what this repository demonstrates.

Product value: lower inference cost and latency on known routes; clearer
authority boundaries; safer handling of irreversible actions; replayable
evidence; model independence; and the ability to combine deterministic and
probabilistic intelligence.

> The long-term research direction is to measure governed cognitive value:
> not merely how many tokens were consumed, but how much useful, controlled
> and verifiable capability was produced between the human, the system's
> structures and its model organs. This is currently a readonly research
> direction — not a currency, token, wallet, economic scoring system or
> source of decision authority.

<a id="public-private"></a>

### Public evidence vs proprietary system

| Public and reproducible here | Broader proprietary system |
|---|---|
| Router, gates and UnifiedInputIR | Full Brody implementation |
| Deterministic solvers | Private structured memory |
| Official runner and Docker path | Full Obsidure engine |
| Bounded Fireworks adapter | Full Lean corpus and proof runtime |
| Benchmarks, validators and metrics | Sigma/OIE private layers |
| Route-only V3B surfaces | Production domain bridges and full X108 runtime |

> The public repository is evidence of the architecture, not a publication
> of the complete proprietary system.

[Back to Start here](#start-here)

---

<a id="reproduce"></a>

## Reproduce the evidence

| Evidence level | Meaning |
|---|---|
| `PRACTICE` | AMD practice categories, this harness |
| `INTERNAL_DRY` | Internal 18-task and frontier-dry benchmarks, zero token |
| `LIVE_FRONTIER` | Deliberate real Fireworks calls (`--live`), spends tokens |
| `OFFICIAL_HIDDEN` | The AMD judge — unknown until executed |

Stdlib-only Python 3.12 — nothing to install.

```bash
# one request with full routing trace
python -m app.cli "explain the context of this decision"

# tests                                                 [SAFE, zero token]
python -m pytest -q
# expected: 1233 passed

# AMD practice category accuracy                        [SAFE, zero token]
python benchmarks/answer_accuracy.py
# expected: overall 8/8 PASS, total_tokens_amd = 0

# official judge path on the 8 practice tasks           [SAFE without key]
python scripts/run_official.py --input submission/track1/input/practice_tasks.json --output submission/track1/output/results.json
python submission/track1/validate_output.py submission/track1/input/practice_tasks.json submission/track1/output/results.json

# main internal benchmark                               [SAFE, zero token]
python benchmarks/run_benchmark.py --track1-official --stack-v3b
# expected: 18/18 route accuracy, 0 tokens, 0 remote

# frontier boundary map (dry)                           [SAFE, zero token]
python benchmarks/run_frontier_benchmark.py
# expected: 15 local / 12 frontier-escalation / 8 governed, false_local_closures = 0
```

Docker submission proof: see [Track 1 Docker proof](#track1-docker-proof)
above for the pull/run/validate commands and expected output.

⚠ **Commands that spend Fireworks tokens** (`--live-baseline`,
`--random-compare`, `run_frontier_benchmark.py --live`, `probe_ladder.py`,
smoke tests without `--dry-run`) are documented in
[docs/BENCHMARKS.md](docs/BENCHMARKS.md) and must be run deliberately —
never as part of an automatic validation pack.

### Environment variables

| Variable | Required | Purpose |
|---|---|---|
| `FIREWORKS_API_KEY` | for live calls | Without it, level-3 decisions run in dry-run mode. No key = local-only behavior on paths that don't require Fireworks. |
| `FIREWORKS_BASE_URL` | no | Defaults to `https://api.fireworks.ai/inference/v1`. **All** Fireworks calls go through this URL — the scoring harness may override it. |
| `ALLOWED_MODELS` | no | Ordered allowlist read dynamically at runtime; the router never hardcodes model IDs and never calls a model outside this list when it is provided. |

### Metrics recorded

`benchmarks/run_benchmark.py` writes `results/benchmark_report.json` and a
judge-readable one-pager `results/REPORT.md`, covering route accuracy,
tokens/latency, and governance counters (`no_model_needed`,
`hold_commands_only`, `denied`, `clarification_needed`, `memory_hits`,
`fireworks_needed`, `remote_calls_avoided`, `estimated_tokens_saved`,
`level0_rate`).

Every remote call also records prompt-compression metrics
(`estimated_prompt_tokens`, `completion_budget`, `compact_profile`,
`prompt_chars_before/after`, `compression_ratio`, `citer_used`) and model
triage evidence — `selected_model`, `actual_model_used`, and
`contract_model_preference` kept as three distinct, never-conflated fields.

[Back to Start here](#start-here)

---

## Documentation map

- Track 1 reproducible path: [docs/TRACK1_SUBMISSION.md](docs/TRACK1_SUBMISSION.md)
- Benchmark matrix (SAFE vs LIVE spend): [docs/BENCHMARKS.md](docs/BENCHMARKS.md)
- Track 3 / narrative: [docs/TRACK3_SUBMISSION.md](docs/TRACK3_SUBMISSION.md)
- Track 3 metric claims: [docs/TRACK3_METRICS.md](docs/TRACK3_METRICS.md)
- Demo script (safe by default): [docs/DEMO.md](docs/DEMO.md)
- Generated reports: `results/REPORT.md`, `results/FRONTIER_REPORT.md`

## Known limits

- The hidden AMD judge score is unknown and external; nothing here claims it.
- Deterministic solvers are fingerprint-bounded: they close only what they
  can verify, and abstain otherwise (by design).
- This public cut is not the full Obsidia OS; Brody is stubbed and memory is
  minimal.
- Frontier live token values can vary between runs (remote generation,
  model/runtime variance); routes and the zero-false-closure invariant are
  the stable claims.
- No claim is made that Obsidia is a bigger or better LLM — the comparison
  is between two execution strategies, not between models.
- Latency figures depend on the local machine and run conditions.

## License

Source-available proprietary license — see [LICENSE](LICENSE).

This repository is public for AMD Developer Hackathon evaluation, technical
review, and reproducibility of the documented benchmark and Docker paths.
Public access does not grant open-source reuse rights.
