#!/usr/bin/env python3
"""Entrypoint for the Track 1 QWEN_ZERO Docker container.

Starts llama-server once on the loopback, waits for it to be ready,
then delegates to scripts/run_official.py with the same argv.
Never reloads the model between tasks. Cleans up on exit.
"""
import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

LLAMA_SERVER = Path("/app/llama-server")
MODEL_PATH    = Path("/models/qwen2.5-3b-instruct-q4_k_m.gguf")
HOST          = "127.0.0.1"
PORT          = 8080
READINESS_TIMEOUT_S = 180   # 3 min — conservative for CPU-only cold start
POLL_INTERVAL_S     = 3


def _log(msg: str) -> None:
    print(f"[qwen_zero] {msg}", flush=True)


def _wait_ready() -> bool:
    url = f"http://{HOST}:{PORT}/health"
    deadline = time.monotonic() + READINESS_TIMEOUT_S
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(POLL_INTERVAL_S)
    return False


def main() -> int:
    if not LLAMA_SERVER.exists():
        _log(f"ERROR: llama-server not found at {LLAMA_SERVER}")
        return 1
    if not MODEL_PATH.exists():
        _log(f"ERROR: GGUF not found at {MODEL_PATH}")
        return 1

    server_cmd = [
        str(LLAMA_SERVER),
        "--model",         str(MODEL_PATH),
        "--host",          HOST,
        "--port",          str(PORT),
        "--n-gpu-layers",  "0",
        "--threads",       "4",
        "--parallel",      "1",
        "--ctx-size",      "2048",
        "--no-mmap",
    ]

    _log(f"Starting llama-server ({MODEL_PATH.name})")
    server = subprocess.Popen(
        server_cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )

    _log(f"Waiting for readiness (up to {READINESS_TIMEOUT_S}s)...")
    t0 = time.monotonic()
    ready = _wait_ready()
    t_load = time.monotonic() - t0

    if not ready:
        stderr_tail = b""
        try:
            server.kill()
            stderr_tail = server.stderr.read(4096)
        except Exception:
            pass
        _log(f"ERROR: llama-server not ready after {READINESS_TIMEOUT_S}s")
        if stderr_tail:
            _log("last stderr: " + stderr_tail.decode("utf-8", errors="replace")[:500])
        return 1

    _log(f"llama-server ready in {t_load:.1f}s — running official runner")

    env = {
        **os.environ,
        "QWEN_LOCAL_ENDPOINT": f"http://{HOST}:{PORT}/v1",
        "TRACK1_QWEN_ZERO":    "1",
        "TRACK1_LOCAL_MODE":   "ZERO",
    }

    runner_args = [sys.executable, "scripts/run_official.py"] + sys.argv[1:]
    runner = subprocess.run(runner_args, env=env)
    exit_code = runner.returncode

    _log("Stopping llama-server...")
    try:
        server.send_signal(signal.SIGTERM)
        server.wait(timeout=10)
    except Exception:
        try:
            server.kill()
        except Exception:
            pass

    _log(f"Done — runner exit code: {exit_code}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
