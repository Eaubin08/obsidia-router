# Obsidia Router — semantic routing before inference
# Stdlib-only Python: no pip install needed at build time.
FROM python:3.12-slim

WORKDIR /obsidia-router
COPY . .

ENV PYTHONUNBUFFERED=1
# Live Fireworks calls require FIREWORKS_API_KEY at run time:
#   docker run -e FIREWORKS_API_KEY=... obsidia-router
# Optional: FIREWORKS_BASE_URL, ALLOWED_MODELS (comma-separated, cheapest first)

# Default: run the benchmark (works without credentials, dry-run mode)
CMD ["python", "benchmarks/run_benchmark.py"]
