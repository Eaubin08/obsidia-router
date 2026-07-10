# Obsidia Router -- semantic routing before inference
# Stdlib-only Python: no pip install needed at build time.
FROM python:3.12-slim

WORKDIR /obsidia-router
COPY . .

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
# Local dev override:
#   docker run obsidia-router python benchmarks/run_benchmark.py --stack-v3b
CMD ["python", "scripts/run_official.py"]
