# Obsidia Router -- semantic routing before inference
# Stdlib-only Python: no pip install needed at build time.
FROM python:3.12-slim

WORKDIR /obsidia-router
# Selective COPY: only the code the official runner needs. Local audit dirs,
# results/, tests/ and docs never enter the image (defense in depth on top of
# .dockerignore -- the judged image must not carry any pre-computed results).
COPY app/ app/
# scripts/: only the official runner — diagnostic smoke tests stay out
COPY scripts/run_official.py scripts/
COPY examples/ examples/
# benchmarks/: only the four modules run_official.py transitively imports
# (audited via sys.modules). No tasks.json, no fixtures, no reports.
COPY benchmarks/track1_runner.py \
     benchmarks/track1_remote_answer_contract.py \
     benchmarks/track1_escalation_guard.py \
     benchmarks/track1_response_profile.py \
     benchmarks/

ENV PYTHONUNBUFFERED=1
# Live Fireworks calls require FIREWORKS_API_KEY at run time:
#   docker run -e FIREWORKS_API_KEY=... -v /host/input:/input -v /host/output:/output obsidia-router
# Optional: FIREWORKS_BASE_URL, ALLOWED_MODELS (comma-separated, cheapest first)
#
# Official AMD Track 1 mode (default CMD):
#   reads  /input/tasks.json
#   writes /output/results.json  [{"task_id","answer"}] only
#   no benchmark phases, no REPORT.md, no receipts
#
# The image ships only the evaluated Track 1 slice. Benchmarks, tests and the
# interactive demo run from the repository, not from this container.
CMD ["python", "scripts/run_official.py"]
