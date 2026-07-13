"""Track 3 Docker entrypoint — real escalation runtime with Qwen local.

Execution sequence:
  1. Start llama-server on 127.0.0.1:<LLAMA_PORT>
  2. Wait for readiness (log-file polling, no HTTP probe in shell)
  3. Run batch.py against /input/tasks.json
  4. Write /output/results.json, /output/receipts/, /output/run_report.json
  5. Stop llama-server
  6. exit 0 if outputs are valid, else exit 1

Environment:
  LLAMA_SERVER_BIN   path to llama-server binary (default /app/llama-server)
  LLAMA_MODEL_PATH   path to GGUF model (default /models/qwen2.5-3b-instruct-q4_k_m.gguf)
  LLAMA_PORT         port for llama-server (default 8080)
  LLAMA_THREADS      CPU threads (default 2)
  LLAMA_CTX_SIZE     context size tokens (default 2048)
  LLAMA_N_PREDICT    max tokens per completion (default 512)
  T3_INPUT           input file path (default /input/tasks.json)
  T3_OUTPUT          output directory (default /output)
  BRODY_ENDPOINT     if set, enables Brody readonly LEVEL_3 path

Invariants enforced by runtime:
  decision_authority = KX108_ONLY
  fireworks_attempted = False
  tokens_remote = 0
  mutations_performed = []
  external_calls = []
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

# When run as a script, sys.path[0] is the script directory, not the project root.
# Insert the project root so that `import app.*` resolves correctly.
sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Configuration ─────────────────────────────────────────────────────────────

LLAMA_BIN   = os.environ.get("LLAMA_SERVER_BIN", "/app/llama-server")
MODEL_PATH  = os.environ.get("LLAMA_MODEL_PATH",
                              "/models/qwen2.5-3b-instruct-q4_k_m.gguf")
PORT        = int(os.environ.get("LLAMA_PORT", "8080"))
THREADS     = int(os.environ.get("LLAMA_THREADS", "2"))
CTX_SIZE    = int(os.environ.get("LLAMA_CTX_SIZE", "2048"))
N_PREDICT   = int(os.environ.get("LLAMA_N_PREDICT", "512"))
T3_INPUT    = Path(os.environ.get("T3_INPUT",  "/input/tasks.json"))
T3_OUTPUT   = Path(os.environ.get("T3_OUTPUT", "/output"))

_READY_MARKERS = (
    "llama_server: model loaded",
    "llama_server: listening on",
    "all slots are idle",
    "server is listening",
    "HTTP server listening",
)

_LOG_PATH = T3_OUTPUT / "_llama_server.log"


def _start_llama_server() -> subprocess.Popen:
    T3_OUTPUT.mkdir(parents=True, exist_ok=True)
    cmd = [
        LLAMA_BIN,
        "--host",        "127.0.0.1",
        "--port",        str(PORT),
        "--model",       MODEL_PATH,
        "--ctx-size",    str(CTX_SIZE),
        "--threads",     str(THREADS),
        "--n-predict",   str(N_PREDICT),
        "--n-gpu-layers", "0",
    ]
    print(f"[entrypoint] starting llama-server pid=?", flush=True)
    print(f"[entrypoint] model={MODEL_PATH}", flush=True)
    log_fh = _LOG_PATH.open("w")
    proc = subprocess.Popen(
        cmd,
        stdout=log_fh,
        stderr=subprocess.STDOUT,
    )
    print(f"[entrypoint] llama-server pid={proc.pid}", flush=True)
    return proc


def _wait_ready(timeout_s: int = 120) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        time.sleep(1)
        try:
            log = _LOG_PATH.read_text(encoding="utf-8", errors="replace")
        except FileNotFoundError:
            continue
        if any(m in log for m in _READY_MARKERS):
            return True
    return False


def _stop_llama_server(proc: subprocess.Popen) -> None:
    try:
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=10)
    except Exception:
        proc.kill()


def _validate_outputs(output_dir: Path) -> bool:
    results_path = output_dir / "results.json"
    report_path  = output_dir / "run_report.json"

    if not results_path.exists() or not report_path.exists():
        print(f"[entrypoint] MISSING outputs: {results_path} {report_path}", flush=True)
        return False

    results = json.loads(results_path.read_text(encoding="utf-8"))
    report  = json.loads(report_path.read_text(encoding="utf-8"))

    # Invariant checks
    if report.get("fireworks_calls", 1) != 0:
        print(f"[entrypoint] FAIL: fireworks_calls != 0", flush=True)
        return False
    if report.get("tokens_remote_total", 1) != 0:
        print(f"[entrypoint] FAIL: tokens_remote_total != 0", flush=True)
        return False
    if report.get("mutations_count", 1) != 0:
        print(f"[entrypoint] FAIL: mutations_count != 0", flush=True)
        return False
    if report.get("world_actions_count", 1) != 0:
        print(f"[entrypoint] FAIL: world_actions_count != 0", flush=True)
        return False

    total     = report.get("tasks_total", 0)
    kx108_ok  = report.get("KX108_ONLY_count", 0)
    if total > 0 and kx108_ok != total:
        print(f"[entrypoint] FAIL: KX108_ONLY_count {kx108_ok} != tasks_total {total}", flush=True)
        return False

    print(f"[entrypoint] outputs valid — {total} tasks, "
          f"{report.get('tasks_resolved',0)} resolved", flush=True)
    print(f"[entrypoint] levels: "
          f"L0={report.get('level_0_count',0)} "
          f"L1={report.get('level_1_count',0)} "
          f"L2={report.get('level_2_count',0)} "
          f"L3_brody={report.get('level_3_brody_count',0)} "
          f"L3_qwen={report.get('level_3_qwen_count',0)}", flush=True)
    print(f"[entrypoint] tokens_local={report.get('tokens_local_total',0)} "
          f"remote=0 fireworks=0 mutations=0", flush=True)
    print(f"[entrypoint] replay PASS={report.get('replay_pass_count',0)} "
          f"FAIL={report.get('replay_fail_count',0)}", flush=True)
    return True


def main() -> int:
    print("[entrypoint] Track 3 — real escalation runtime", flush=True)
    print(f"[entrypoint] input={T3_INPUT} output={T3_OUTPUT}", flush=True)

    if not Path(LLAMA_BIN).exists():
        print(f"[entrypoint] ERROR: llama-server not found at {LLAMA_BIN}", flush=True)
        return 1
    if not Path(MODEL_PATH).exists():
        print(f"[entrypoint] ERROR: model not found at {MODEL_PATH}", flush=True)
        return 1
    if not T3_INPUT.exists():
        print(f"[entrypoint] ERROR: input not found at {T3_INPUT}", flush=True)
        return 1

    # ── Start llama-server ────────────────────────────────────────────────────
    server = _start_llama_server()

    print(f"[entrypoint] waiting for model load (up to 120s)...", flush=True)
    ready = _wait_ready(timeout_s=120)
    if not ready:
        print("[entrypoint] ERROR: llama-server did not become ready", flush=True)
        _stop_llama_server(server)
        return 1
    print(f"[entrypoint] llama-server ready on 127.0.0.1:{PORT}", flush=True)

    # ── Set endpoint for runtime ──────────────────────────────────────────────
    os.environ["QWEN_LOCAL_ENDPOINT"] = f"http://127.0.0.1:{PORT}/v1"

    # ── Run batch ────────────────────────────────────────────────────────────
    exit_code = 1
    try:
        from app.track3.batch import run_batch
        report = run_batch(
            input_path=T3_INPUT,
            output_dir=T3_OUTPUT,
            qwen_available=None,    # auto-detect via QWEN_LOCAL_ENDPOINT
            brody_available=None,   # auto-detect via BRODY_ENDPOINT
        )
        ok = _validate_outputs(T3_OUTPUT)
        exit_code = 0 if ok else 1
    except Exception as exc:
        print(f"[entrypoint] ERROR in batch: {exc}", flush=True)
        exit_code = 1
    finally:
        _stop_llama_server(server)
        print(f"[entrypoint] llama-server stopped", flush=True)

    print(f"[entrypoint] exit {exit_code}", flush=True)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
