# Track 1 submission — reproduction guide

How to build, run and validate the exact surface the AMD judge evaluates.
All commands are Windows PowerShell. No real API key ever appears in this file.

---

## A. What AMD runs

```text
/input/tasks.json
  → Docker CMD  (python scripts/run_official.py)
  → Obsidia Router: IR → gates → level decision → optional bounded Fireworks escalation
  → /output/results.json   [{"task_id": "...", "answer": "..."}] — nothing else
  → exit 0 (success) / non-zero (error)
```

The judge does **not** run:

- the internal benchmarks (`benchmarks/run_benchmark.py`, `answer_accuracy.py`, …);
- the interactive terminal (`python -m app.cli`);
- any Track 3 demo or documentation tooling;
- the full private Obsidia stack (Brody, Obsidure, Sigma, Lean, X-108 kernel).
  The container ships only the evaluated routing slice.

## B. Requirements

- Docker Desktop (or Docker Engine), `linux/amd64` capable.
- Python 3.10+ on the host — only for the local output validator.
- Environment variables injected by the AMD harness at run time:

| Variable | Role |
|---|---|
| `FIREWORKS_API_KEY` | enables live Fireworks calls; without it the container runs in dry-run mode |
| `FIREWORKS_BASE_URL` | Fireworks endpoint override (defaults to the official API) |
| `ALLOWED_MODELS` | comma-separated model ladder; the router never calls a model outside it |

## C. Safe dry run (zero token, no key required)

Build:

```powershell
docker build -t obsidia-router:track1-local .
```

Clean previous output:

```powershell
Remove-Item .\submission\track1\output\results.json -ErrorAction SilentlyContinue
```

Run the 8 AMD practice categories without any credentials:

```powershell
docker run --rm `
  -v "${PWD}\submission\track1\input:/input:ro" `
  -v "${PWD}\submission\track1\output:/output" `
  obsidia-router:track1-local
```

> Note: the container reads `/input/tasks.json`. To use the practice set as-is,
> either copy it to `tasks.json` in the mounted input directory, or mount the
> file directly:
> `-v "${PWD}\submission\track1\input\practice_tasks.json:/input/tasks.json:ro"`

Capture the exit code:

```powershell
$dockerRc = $LASTEXITCODE
Write-Host "DOCKER_EXIT_CODE=$dockerRc"
if ($dockerRc -ne 0) {
    throw "Track 1 container failed with exit code $dockerRc"
}
```

Validate the output contract:

```powershell
python .\submission\track1\validate_output.py `
  .\submission\track1\input\practice_tasks.json `
  .\submission\track1\output\results.json
```

Expected:

```text
TRACK1_OUTPUT_VALIDATION = PASS
tasks_in = 8
answers_out = 8
schema = STRICT
missing = 0
extra = 0
empty_answers = 0
```

## D. Live-compatible local run

> ⚠ **This command can spend Fireworks tokens when a real API key is present.**
> Run it deliberately, never as part of an automatic validation pack.

```powershell
docker run --rm `
  -e FIREWORKS_API_KEY=$env:FIREWORKS_API_KEY `
  -e FIREWORKS_BASE_URL=$env:FIREWORKS_BASE_URL `
  -e ALLOWED_MODELS=$env:ALLOWED_MODELS `
  -v "${PWD}\submission\track1\input:/input:ro" `
  -v "${PWD}\submission\track1\output:/output" `
  obsidia-router:track1-local
```

## E. Output contract

`/output/results.json` contains exactly one JSON list, one object per task,
no extra keys, English answers only:

```json
[
  {
    "task_id": "practice-01",
    "answer": "..."
  }
]
```

Per-call Fireworks timeout is clamped in code to 25 s (under the 30 s
per-answer cap); the clamp cannot be raised by environment or caller.

### Adaptive triage receipts (audit-only, never part of the judged schema)

By default, `scripts/run_official.py` writes only `results.json`.
The official Docker path therefore leaves `/output` with exactly the judged
artifact and no receipt or report file.

For an explicit local audit run, set:

```text
OBSIDIA_TRACK1_TRIAGE_RECEIPTS=1

This enables the metadata-only companion
track1_triage_receipts.json. The AMD harness never reads this sidecar,
and it never changes the strict {task_id, answer} payload. When the
variable is absent or false, the runner also removes any stale sidecar
left by an earlier audit run.

The sidecar is a metadata-only projection. It never stores the request text,
generated answer, memory content, or system-prompt content; only lengths,
routes, model identifiers, rung evidence, and token counters are written.

Per-task fields (`null` on any locally-closed task — no remote selection
happened, so there is nothing truthful to report):

| Field | Meaning |
|---|---|
| `selected_model` | model chosen by the single triage authority; equals the model transmitted to `fireworks.chat()` |
| `actual_model_used` | the model really captured on the transport call (equal to `selected_model` by construction) |
| `contract_model_preference` | the remote answer contract's older, informative default — never selects the call target |
| `selected_rung` | 0-indexed position in the resolved `ALLOWED_MODELS` ladder |
| `selection_reason` | short deterministic explanation of the rung |
| `ladder_size` | length of the resolved ladder for that call |
| `raw_prompt_chars` / `system_prompt_chars` | lengths only, never the prompt content |

A `summary` block aggregates these across the run: `model_call_distribution`,
`model_rung_distribution`, `first_rung_call_rate` /
`intermediate_rung_call_rate` / `last_rung_call_rate`,
`higher_rung_calls_avoided` (a **call count**, never a token/dollar claim),
`local_solver_hit_rate`, `code_tasks_closed_locally`, `remote_code_calls`,
and prompt-size totals. Zero remote calls in a given run yields safe zero
rates, never a division error — see `app.metrics.triage_metrics`.

## F. Evidence levels

- `PRACTICE` — the 8 AMD practice categories (this harness).
- `INTERNAL_DRY` — internal 18-task routing benchmark, zero token.
- `LIVE_FRONTIER` — deliberate real Fireworks calls on the frontier suite.
- `OFFICIAL_HIDDEN` — the AMD judge; unknown until executed.

> The practice harness validates container behavior. It does not predict the
> hidden AMD judge score.

## G. Submission image

```text
Public image: ghcr.io/eaubin08/obsidia-router:track1
Pinned image: ghcr.io/eaubin08/obsidia-router:track1-0a5fc69
Verified manifest digest: sha256:4339cd0d3a952cdc065e9223d441f623ed846ae451e09fa60f2743a73f5daa25
(verified against the registry with `docker buildx imagetools inspect` — OCI image index digest of the pinned tag)
Anonymous pull: verified
Official dry run: verified (8 tasks, 0 tokens, strict schema PASS, exit 0)
```

These fields are filled by the registry publication lot (GHCR workflow) and
are the single source of truth for the submitted image URL.
