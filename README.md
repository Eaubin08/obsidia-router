# Obsidia Router — Structure Before Inference

> Most AI systems decide **which** model to call.
> Obsidia first decides **whether inference is necessary at all**.

**Quick links**

- 🎬 **[Watch the Obsidia Track 3 governed escalation demo](https://www.youtube.com/watch?v=Bxe5saL0lvo&t=195s)**
- 📦 **Track 3 container** — `ghcr.io/eaubin08/obsidia-router:track3-real-escalation`
- 📦 **Track 1 container** — `ghcr.io/eaubin08/obsidia-router:track1-qwen-zero`
- 📚 **[Architecture and documentation](docs/ARCHITECTURE.md)** · [Track 3 submission](docs/TRACK3_SUBMISSION.md) · [Track 3 metrics](docs/TRACK3_METRICS.md)

Obsidia is a governed intelligence architecture that separates structural
verification, model inference and action authority.

For AMD ACT II, one public system supports two complementary tracks:
Track 1 measures token-efficient routing; Track 3 ships a governed
escalation runtime with a real local model, canonical receipts and
readonly replay.

This repository is not a claim that Obsidia is a bigger or better LLM. It
demonstrates that a deterministic governance layer placed before inference
can reduce both the **number** of remote calls and the **cost** of the
calls that remain, while preserving zero false local closures on the
measured frontier suite.

<a id="start-here"></a>

## Start here

| I want to... | Go directly to |
|---|---|
| See the Track 3 escalation runtime | [Track 3 — Governed Escalation Runtime](#track3-runtime) |
| Check the Track 3 verified results | [Track 3 verified results](#track3-results) |
| Pull and run the public containers | [Public containers](#containers) |
| Watch the demo | [Demo video](#demo-video) |
| Review the measured Track 1 results | [Track 1 evidence](#track1-evidence) |
| Run the exact Track 1 Docker proof | [Track 1 Docker proof](#track1-docker-proof) |
| Explore the broader Obsidia vision | [Track 3 architecture vision](#track3) |
| Reproduce all public evidence | [Reproduction guide](#reproduce) |
| Check public vs proprietary boundaries | [Public and private scope](#public-private) |

<a id="two-tracks"></a>

## Two tracks, one system

| Track | Question | Public proof |
|---|---|---|
| Track 1 — Token-Efficient Routing | When is a remote model call actually necessary? | Router, Docker path, local solvers, governed escalation and measured token efficiency |
| Track 3 — Governed Escalation Runtime | What architecture can govern cognition, decision and action before execution? | Real escalation ladder LEVEL 0 → LEVEL 3, local Qwen inference, canonical receipts, readonly replay, public container |

Track 1 measures the mechanism. Track 3 runs the governed architecture end to end.

---

<a id="track3-runtime"></a>

## Track 3 — Governed Escalation Runtime

The Track 3 runtime executes a full governed escalation ladder. Every
request follows the same deterministic path, and inference is the last
resort, not the default:

```
Natural input
  → UnifiedInputIR
  → Active Plan
  → Capability Resolver
  → Gates (DENY > HOLD > CLARIFY > ALLOW)
  → LEVEL 1: deterministic local structures
  → LEVEL 2: readonly memory
  → LEVEL 3: Brody readonly (when a real loopback endpoint is available)
  → LEVEL 3: local Qwen (when inference is genuinely necessary)
  → KX108_ONLY decision authority
  → canonical receipt (SHA-256)
  → readonly replay
```

Every task produces an `ExecutionEnvelope` receipt with a canonical hash
and a full `escalation_trace` (one event per level attempted). The replay
tool re-derives IR, plan, gate verdict, solvers and memory lookup without
calling any model, and verifies the stored envelope structurally.

**Honest boundaries of the public runtime:**

- **Qwen2.5-3B-Instruct Q4_K_M is the real local model organ** of the
  public image — it runs on the loopback via `llama.cpp`, no remote calls.
- **Brody readonly is only called if a real loopback endpoint is
  available**; the private Brody is not embedded in the image.
- **`brody_stub` is never accepted as a final semantic answer.**
- Obsidure, Lean, Sigma, OIE and domain bridges remain **route-only or
  bridge-required** in this public runtime.
- **No private layer is included in the public image.**
- Fireworks is never called by the Track 3 runtime: 0 calls, 0 remote
  tokens, by construction and verified per run.

<a id="track3-results"></a>

### Track 3 verified results

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
| Public container | Available on GHCR |
| Architecture | linux/amd64 |

The 359 tests include 5 real-Qwen integration tests, executed against the
actual local Qwen2.5-3B model; these 5 are skipped automatically when no
local Qwen endpoint is running, so the suite stays reproducible on any
machine.

**Escalation distribution — 12-task demonstration batch** (from the
committed `run_report.json` of the validated container run):

| Level | Tasks | Meaning |
|---|---:|---|
| LEVEL 0 — structural / governance | 3/12 | HOLD, DENY or CLARIFY resolved before any model layer |
| LEVEL 1 — deterministic local solvers | 2/12 | closed locally at zero tokens |
| LEVEL 2 — readonly memory | 2/12 | closed from the readonly memory index |
| LEVEL 3 — local Qwen | 5/12 | genuine inference, loopback only |
| LEVEL 3 — Brody readonly | 0/12 | no loopback Brody endpoint was available in this run |

9/12 tasks resolved; the 3 LEVEL-0 outcomes are governed verdicts
(HOLD / DENY / CLARIFY), which are valid zero-token answers, not failures.
Local Qwen calls averaged ≈2.65 s in this batch (run-dependent); 16 local
tokens total, 0 remote tokens.

**Accuracy note:** 4/5 on the scored demonstration subset (5 of the 12
demo tasks carried an expected answer). This is a demonstration subset,
not a general benchmark, and must not be merged with the Track 1
internal benchmark results.

---

<a id="containers"></a>

## Public containers

### Track 3

| Field | Value |
|---|---|
| Tag | `ghcr.io/eaubin08/obsidia-router:track3-real-escalation` |
| Digest | `sha256:a2ae4b0b5ac71786ec5322406e130c97f2df1d19cae133e3b8de395189a2283c` |
| Architecture | linux/amd64 |
| Model | local Qwen2.5-3B-Instruct Q4_K_M (llama.cpp, loopback) |
| Fireworks key | not required |
| Network | supports `--network none` |
| Target resources | 4 GB RAM, 2 CPU |
| Base | built from the frozen Track 1 Qwen image |

The container reads `/input/tasks.json`, runs the full escalation ladder
per task, and writes `/output/results.json`, `/output/receipts/` and
`/output/run_report.json`:

```bash
docker run --rm --network none --memory 4g --cpus 2 \
  -v <input-dir>:/input:ro \
  -v <output-dir>:/output \
  ghcr.io/eaubin08/obsidia-router:track3-real-escalation
```

`<input-dir>` must contain a `tasks.json` array of
`{"task_id", "prompt"}` objects (optional `expected` and `category`
fields enable the scored subset in the run report).

### Track 1

| Field | Value |
|---|---|
| Tag | `ghcr.io/eaubin08/obsidia-router:track1-qwen-zero` |
| Digest | `sha256:6f81c4f529bcfe50394f1d4beee23c6cbbcc4b987feaeb726d6e30e8ecd225fe` |
| Architecture | linux/amd64 |

Run commands and strict output validation: [Track 1 Docker proof](#track1-docker-proof).

---

<a id="demo-video"></a>

## Demo video

🎬 **[Watch the Obsidia Track 3 governed escalation demo](https://www.youtube.com/watch?v=Bxe5saL0lvo&t=195s)**

---

<a id="track1"></a>

## Track 1 — Zero-token submission

Track 1 evaluates the public and reproducible cut of Obsidia. Each request
is compiled into a bounded structure, checked by deterministic gates,
resolved locally when possible, and escalated only when inference remains
necessary. The submitted Track 1 image removes the Fireworks fallback
entirely and replaces it with a fully local inference path.

**Architecture:**

- Deterministic local solvers close factual, math, sentiment, NER and code
  tasks first, at zero tokens and zero remote calls.
- When no deterministic solver closes the task, **Qwen2.5-3B-Instruct Q4_K_M**
  (running via `llama.cpp` on the loopback at `127.0.0.1:8080`) acts as the
  local fallback. No Fireworks call is made, even when `FIREWORKS_API_KEY` is
  present.
- Every Qwen output passes through the same provider-agnostic
  `validate_remote_output` pipeline used for remote answers
  (`allowed_labels`, `sentence_count`).
- If validation fails, one bounded `repair_remote_output` pass is applied;
  only the repaired output re-validates. No second model call.
- No final Fireworks fallback: tasks unresolved after the Qwen pass remain
  unresolved.

**Internal hidden-like benchmark result:**

> **127 / 128 correct — 99.2 %**
>
> This is an **internal** benchmark measured against a hidden-like task set.
> It is **not** the official AMD judge score, which is external and unknown.

**Measured Docker validation — public image run:**

| Metric | Value |
|---|---|
| Fireworks calls | 0 |
| Fireworks tokens | 0 |
| Startup (Qwen cold, public test) | 21.1 s |
| Runtime (8 tasks, public test) | 45.59 s |
| Runtime (128 tasks, local internal) | 80 s |
| Peak memory (local, --memory 3g) | 2.26 GiB |
| Compressed image size | 2.11 GB |
| Architecture | linux/amd64 |

<a id="track1-evidence"></a>

### Track 1 headline evidence

| Proof | Result | Meaning |
|---|---:|---|
| Test suite | 1860 passed | Public evaluation cut is internally consistent |
| AMD practice surface | 8/8, 0 remote, 0 tokens | Practice categories close locally |
| Internal hidden-like benchmark | 127/128 — 99.2% | **Not the official AMD judge score** |
| Internal routing | 18/18 accepted routes | Every route matched an accepted path, 5584 est. tokens saved |
| Level-0 rate | 11/18 = 61.1% | Resolved or governed before any model layer |
| Before memory or remote inference | 16/18 = 88.9% | Level 0 structure or deterministic Level 1 solvers |
| Internal remote calls | 0/18 | All baseline remote calls avoided on this INTERNAL_DRY set |
| Frontier safety | 0 false local closures | No solver answered outside its verified fingerprint |
| V3B routes | 15/15 | Route-only surfaces preserved KX108_ONLY boundaries |
| Hidden AMD judge | Unknown | External official evaluation |

This README does not report one global intelligence score — it reports a
proof ladder. Each row above measures a different property. The Track 1
figures belong exclusively to their named internal benchmarks; they must
not be merged with the Track 3 demonstration batch.

<a id="track1-docker-proof"></a>

### Track 1 Docker proof

This is the shortest independent verification path for Track 1. It uses
the same public container, input location, output location and strict
schema expected by the official Track 1 evaluation harness.

| Submission artifact | Verified value |
|---|---|
| Public image | `ghcr.io/eaubin08/obsidia-router:track1-qwen-zero` |
| OCI digest | `sha256:6f81c4f529bcfe50394f1d4beee23c6cbbcc4b987feaeb726d6e30e8ecd225fe` |
| Platform | `linux/amd64` |
| Input | `/input/tasks.json` |
| Output | `/output/results.json` |
| Output schema | Strict `[{"task_id","answer"}]` — `TRACK1_OUTPUT_VALIDATION = PASS` |
| Public test result | 8 tasks, 8 answers, 0 Fireworks calls, 0 Fireworks tokens |
| Startup (Qwen cold) | 21.1 s |
| Runtime (8 tasks) | 45.59 s |
| Process result | Exit code 0 |
| Anonymous pull | Verified |

Linux / macOS:

```bash
docker pull ghcr.io/eaubin08/obsidia-router:track1-qwen-zero

docker run --rm \
  -v "$PWD/submission/track1/input/practice_tasks.json:/input/tasks.json:ro" \
  -v "$PWD/submission/track1/output:/output" \
  ghcr.io/eaubin08/obsidia-router:track1-qwen-zero
```

Windows PowerShell:

```powershell
docker pull ghcr.io/eaubin08/obsidia-router:track1-qwen-zero

docker run --rm `
  -v "${PWD}\submission\track1\input\practice_tasks.json:/input/tasks.json:ro" `
  -v "${PWD}\submission\track1\output:/output" `
  ghcr.io/eaubin08/obsidia-router:track1-qwen-zero
```

Validate the output strictly:

```bash
python submission/track1/validate_output.py \
  submission/track1/input/practice_tasks.json \
  submission/track1/output/results.json
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

This image runs in `TRACK1_QWEN_ZERO=1` mode: even when `FIREWORKS_API_KEY` is
injected by the harness, no Fireworks call is made. All tasks are resolved by
deterministic local solvers or by the Qwen2.5-3B local model on the loopback.
The official hidden harness may inject different tasks; its result is external
and unknown. This Docker proof is not a validation of the hidden AMD judge score.

Full judge-path reproduction guide: [docs/TRACK1_SUBMISSION.md](docs/TRACK1_SUBMISSION.md).

[Back to Start here](#start-here)

---

<a id="track3"></a>

## Track 3 — architecture vision

Track 1 proves that Obsidia can reduce and bound inference. The Track 3
runtime above runs the governed ladder end to end. This section explains
the larger architecture behind both.

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

| Component | Architectural role |
|---|---|
| Unified interpretation | Converts natural input into a bounded structural representation |
| Active plan and capability resolution | Determines what capabilities are actually needed |
| Local deterministic structures | Resolve known routes without remote inference |
| Brody | Proprietary LLM organ connected to structured memory; readonly interface in the public runtime |
| Memory | Provides structured, non-sovereign, readonly context |
| Obsidure | Code and implementation organ that can propose changes (route-only here) |
| Lean-backed proof layer | Verifies selected formal properties; it does not decide |
| Sigma | Observes coherence and can alert or freeze; it does not decide |
| Domain bridges | Translate real-world domain states into a bounded kernel-readable alphabet |
| Gates | Apply pre-execution boundaries |
| X108 kernel | Retains final decision authority |

Not all of these layers execute inside the public repository. Proposal,
proof, memory and generation remain non-sovereign — decision authority
remains `KX108_ONLY`.

### Product direction

Obsidia targets AI workflows where decisions are costly, regulated or
difficult to reverse, including financial operations, infrastructure
changes, navigation systems and enterprise agents.

Domains translate real-world states into bounded kernel-readable structures,
while connectors remain bridge-only until action authority is explicitly
granted. No certification, regulatory compliance or production deployment
is claimed beyond what this repository demonstrates.

<a id="public-private"></a>

### Public evidence vs proprietary system

| Public and reproducible here | Broader proprietary system |
|---|---|
| Router, gates and UnifiedInputIR | Full Brody implementation |
| Deterministic solvers | Private structured memory |
| Track 3 escalation runtime, receipts, replay | Full Obsidure engine |
| Local Qwen inference (loopback) | Full Lean corpus and proof runtime |
| Benchmarks, validators and metrics | Sigma/OIE private layers |
| Route-only V3B surfaces | Production domain bridges and full X108 runtime |

> The public repository is evidence of the architecture, not a publication
> of the complete proprietary system.

[Back to Start here](#start-here)

---

<a id="reproduce"></a>

## Reproduce the evidence

Stdlib-only Python 3.12 — nothing to install.

```bash
# Track 3 test suite                                    [SAFE, zero remote token]
python -m pytest tests/track3 -q
# expected: all tests pass; the 5 real-Qwen tests skip without a local Qwen endpoint

# one request with full routing trace
python -m app.cli "explain the context of this decision"

# Track 1 tests                                         [SAFE, zero token]
python -m pytest -q

# AMD practice category accuracy                        [SAFE, zero token]
python benchmarks/answer_accuracy.py
# expected: overall 8/8 PASS, total_tokens_amd = 0

# main internal benchmark                               [SAFE, zero token]
python benchmarks/run_benchmark.py --track1-official --stack-v3b
# expected: 18/18 route accuracy, 0 tokens, 0 remote

# frontier boundary map (dry)                           [SAFE, zero token]
python benchmarks/run_frontier_benchmark.py
# expected: false_local_closures = 0
```

Container proofs: [Public containers](#containers) for Track 3,
[Track 1 Docker proof](#track1-docker-proof) for Track 1.

⚠ **Commands that spend Fireworks tokens** (`--live-baseline`,
`--random-compare`, `run_frontier_benchmark.py --live`, `probe_ladder.py`)
are documented in [docs/BENCHMARKS.md](docs/BENCHMARKS.md) and must be run
deliberately — never as part of an automatic validation pack. The Track 3
runtime never calls Fireworks.

[Back to Start here](#start-here)

---

## Documentation map

- Track 3 submission narrative: [docs/TRACK3_SUBMISSION.md](docs/TRACK3_SUBMISSION.md)
- Track 3 metric claims: [docs/TRACK3_METRICS.md](docs/TRACK3_METRICS.md)
- Track 1 reproducible path: [docs/TRACK1_SUBMISSION.md](docs/TRACK1_SUBMISSION.md)
- Benchmark matrix (SAFE vs LIVE spend): [docs/BENCHMARKS.md](docs/BENCHMARKS.md)
- Demo script (safe by default): [docs/DEMO.md](docs/DEMO.md)
- Generated reports: `results/REPORT.md`, `results/FRONTIER_REPORT.md`

## Known limits

- The hidden AMD judge score is unknown and external; nothing here claims it.
- Deterministic solvers are fingerprint-bounded: they close only what they
  can verify, and abstain otherwise (by design).
- This public cut is not the full Obsidia OS; the private Brody is not
  embedded, and memory is a minimal readonly index.
- The Track 3 demonstration batch (12 tasks) is a demonstration, not a
  general benchmark; its accuracy subset is 5 scored tasks.
- Latency figures depend on the machine and run conditions.
- No claim is made that Obsidia is a bigger or better LLM — the comparison
  is between two execution strategies, not between models.

## License

Source-available proprietary license — see [LICENSE](LICENSE).

This repository is public for AMD Developer Hackathon evaluation, technical
review, and reproducibility of the documented benchmark and Docker paths.
Public access does not grant open-source reuse rights.
