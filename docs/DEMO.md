# Demo Script

## Demo surfaces

- **Primary demo: the Obsidia Router video** — this script is what that video
  records. It is the main hackathon demo.
- README companion: the Obsidia Cognitive OS video — broader Track 3 vision,
  linked from the README, not the primary demo.
- The default terminal demo below stays **SAFE / zero-token**.
- AMD/Fireworks usage evidence is shown through the committed live sample
  (≈389 tokens, 1/5 remote — `LIVE_SAMPLE` in [BENCHMARKS.md](BENCHMARKS.md)),
  the Fireworks adapter (`app/adapters/fireworks.py`, the single choke
  point), the benchmark docs, and the slide deck — **not** by the SAFE demo
  itself, which deliberately spends nothing.

## Demo goal

Show that this project is not "one more LLM". It is a pre-inference layer
that decides — deterministically, before any token is spent — whether a model
call is necessary at all.

Everything in the default script is **SAFE (zero Fireworks token)**. Run the
demo in a shell **without** `FIREWORKS_API_KEY` set, so even a mistake cannot
spend tokens.

## Demo commands (all SAFE)

```powershell
# 0. clean state
git status --short

# 1. full test suite — routing, gates, schema, timeout clamp, English-only
python -m pytest -q
# expected: 830 passed

# 2. the 8 AMD practice categories, graded locally
python benchmarks/answer_accuracy.py
# expected: overall 8/8 PASS, total_tokens_amd = 0

# 3. main internal benchmark — routes, governance, V3B stack
python benchmarks/run_benchmark.py --track1-official --stack-v3b
# expected: 18/18 route accuracy, 0 tokens, 0 remote; 15/15 V3B

# 4. frontier boundary map (dry — the report header says so explicitly)
python benchmarks/run_frontier_benchmark.py
# then open results/FRONTIER_REPORT.md — four zones, 0 false local closures

# 5. the exact judge path, in Docker, no key
docker build -t obsidia-router .
docker run --rm `
  -v "${PWD}\submission\track1\input\practice_tasks.json:/input/tasks.json:ro" `
  -v "${PWD}\submission\track1\output:/output" `
  obsidia-router

# 6. strict output contract check
python .\submission\track1\validate_output.py `
  .\submission\track1\input\practice_tasks.json `
  .\submission\track1\output\results.json
# expected: TRACK1_OUTPUT_VALIDATION = PASS, 8/8, schema = STRICT
```

## Optional live commands

> ⚠ **Every command below spends real Fireworks tokens when
> `FIREWORKS_API_KEY` is set. Never run them as part of an automatic pack.
> Run them deliberately, one at a time.** Details: [BENCHMARKS.md](BENCHMARKS.md).

```powershell
# ladder connectivity — 1 minimal call per ALLOWED_MODELS rung
python benchmarks/probe_ladder.py

# official runner, live — the sample escalation costs ≈389 tokens historically
python scripts/run_official.py --input submission/track1/input/practice_tasks.json --output submission/track1/output/results.json

# frontier with real Fireworks calls (LIVE_COMPARATIVE)
python benchmarks/run_frontier_benchmark.py --live

# raw-model baseline on the 18 governed/internal tasks (~18 calls)
python benchmarks/run_benchmark.py --track1-official --stack-v3b --live-baseline

# same dirty prompt: Obsidia vs raw LLM (variable spend)
python benchmarks/run_benchmark.py --track1-official --stack-v3b --random-compare 20 --random-batches 10 --random-batch-size 40 --random-seed 108
```

## Spoken script (≈5 minutes, plain English)

**Intro — 30 s**
"Most agents ask *which* model to call. We ask a different question: is a
model call necessary at all? Obsidia compiles every request into a
deterministic structure, runs governance gates before any model, and only
escalates when local structure is not enough. The LLM is an organ, not the
brain."

**Benchmark — 60 s** *(run steps 1–3)*
"Eight hundred thirty tests. The eight official AMD practice categories:
eight out of eight, zero tokens. The internal eighteen-task benchmark:
eighteen out of eighteen routes correct, zero remote calls. Nothing here
touched a model — and a local decision takes about a tenth of a millisecond.
When the route is known, predicting is slower than checking."

**Frontier — 60 s** *(run step 4, show FRONTIER_REPORT.md)*
"This is the honest part. We don't claim everything closes locally. This map
has four zones: solo-safe, where calling a model is pure waste; governed,
where a model must never be called; abstention, where the router says 'I
don't know' instead of guessing; and Fireworks-useful, where remote inference
earns its cost. The metric we care most about: zero false local closures.
The router never claims a local answer it cannot defend. One honest detail:
on hidden judge tasks, an unresolved informational request escalates under a
bounded contract instead of returning a placeholder — abstention is for the
governed path, not a way to dodge the evaluator."

**Governance — 60 s**
"Push to main. Delete this folder. Deploy to production. These never reach a
model — a HOLD or a DENY is a valid zero-token answer. The decision authority
is the deterministic kernel, K-X-one-oh-eight only: no real action, no memory
write, verdicts only. Governance is enforced before the model, not prompted
into it."

**Docker / harness — 60 s** *(run steps 5–6)*
"This is the exact container the judge pulls. It reads tasks.json, writes a
strict list of task-id and answer, nothing else, and exits zero. No key
needed for the dry path — and the output validator proves the contract:
eight in, eight out, strict schema."

**Closing — 30 s**
"We didn't build a bigger model — zero gigabytes of weights in this stack.
We built the layer that decides when inference is necessary. Accuracy first,
then fewest tokens: that is exactly what this router optimizes."

## Backup if live API fails

- Everything in the default script is dry: **rerun it — no key required.**
- Show the committed snapshots instead of live output:
  `results/REPORT.md` (18/18, 0 remote, speed profile, governance table) and
  `results/FRONTIER_REPORT.md` (four zones, 0 false local closures).
- Show `python benchmarks/answer_accuracy.py` — 8/8 at zero token, live on
  stage, no network involved.
- Say it plainly: "Fireworks is a single choke point, not a dependency.
  Every governed and local path answers without it — that is the point of
  the architecture."
