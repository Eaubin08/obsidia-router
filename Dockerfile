# Obsidia Router — semantic routing before inference
# Stdlib-only Python: no pip install needed at build time.
FROM python:3.12-slim

WORKDIR /obsidia-router
COPY . .

ENV PYTHONUNBUFFERED=1
# Live Fireworks calls require FIREWORKS_API_KEY at run time:
#   docker run -e FIREWORKS_API_KEY=... -v /host/input:/input -v /host/output:/output obsidia-router
# Optional: FIREWORKS_BASE_URL, ALLOWED_MODELS (comma-separated, cheapest first)
#
# Official hackathon mode (default CMD):
#   reads  /input/tasks.json
#   writes /output/results.json   (public, harness-clean)
#   skips  receipts_internal.json (governance audit — not submitted to harness)
#
# Local dev override:
#   docker run obsidia-router python benchmarks/run_benchmark.py --stack-v3b
CMD ["python", "benchmarks/run_benchmark.py", \
     "--track1-official", \
     "--tasks-file", "/input/tasks.json", \
     "--out-dir", "/output", \
     "--no-receipts"]
