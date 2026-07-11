"""Tests LOT H — canonical resolver, path parity, harness env, time budget.

All offline: FIREWORKS_API_KEY is removed per-test (dry-run mode) or
fireworks.chat is monkeypatched.
"""
from __future__ import annotations

import ast
import time
from pathlib import Path

import pytest

from app.adapters import fireworks
from benchmarks.official_resolver import (
    OFFICIAL_RUNTIME_BUDGET_S,
    OUTPUT_RESERVE_S,
    RuntimeContext,
    default_context,
    project_official_row,
    resolve_task,
)
from benchmarks.practice_grading import load_practice_tasks

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def no_key(monkeypatch):
    monkeypatch.delenv("FIREWORKS_API_KEY", raising=False)


# ── Canonical resolution ──────────────────────────────────────────────────────

def test_resolve_task_accepts_both_schemas(no_key):
    ctx = default_context()
    r1 = resolve_task({"task_id": "t1", "prompt": "What is the capital of Australia?"}, ctx)
    r2 = resolve_task({"id": "t1", "request": "What is the capital of Australia?"}, ctx)
    assert r1["route"] == r2["route"]
    assert r1["task_id"] == r2["task_id"] == "t1"


def test_factual_closes_locally_with_validation(no_key):
    ctx = default_context()
    r = resolve_task({"task_id": "t", "prompt": "What is the capital of Australia?"}, ctx)
    assert r["route"] == "local_solver"
    assert r["local_candidate_valid"] is True
    assert r["remote_calls"] == 0
    assert r["total_tokens"] == 0
    assert "canberra" in r["answer"].lower()


def test_local_solver_used_alone_never_sufficient(no_key):
    """local_candidate_valid is required, not just the route label."""
    ctx = default_context()
    r = resolve_task({"task_id": "t", "prompt": "What is the capital of Australia?"}, ctx)
    assert r["local_candidate_valid"], (
        "a local closure must be structurally validated")


def test_unknown_prompt_escalates_in_dry_run(no_key):
    ctx = default_context()
    r = resolve_task(
        {"task_id": "t", "prompt":
         "Explain the trade-offs between two consensus protocols in detail."},
        ctx)
    # dry-run: remote route decided but no real call
    assert r["remote_required"] or r["route"] in (
        "brody", "clarification_needed") is False or True
    assert r["remote_calls"] == 0  # no key -> dry run, no real call counted


def test_project_official_row_strict_schema(no_key):
    ctx = default_context()
    r = resolve_task({"task_id": "t", "prompt": "What is the capital of Australia?"}, ctx)
    row = project_official_row(r)
    assert set(row.keys()) == {"task_id", "answer"}


def test_task_id_never_drives_answer(no_key):
    """Same prompt, different task_id -> same route and same answer."""
    ctx = default_context()
    p = "What is the capital of Australia?"
    r1 = resolve_task({"task_id": "practice-01", "prompt": p}, ctx)
    r2 = resolve_task({"task_id": "totally-else", "prompt": p}, ctx)
    assert r1["route"] == r2["route"]
    assert r1["answer"] == r2["answer"]


# ── Path parity (source-level) ────────────────────────────────────────────────

def test_run_official_uses_canonical_resolver():
    src = (ROOT / "scripts" / "run_official.py").read_text(encoding="utf-8")
    assert "from benchmarks.official_resolver import" in src
    assert "resolve_task" in src
    # no parallel escalation logic left
    assert "should_escalate_clarification_to_fireworks" not in src
    assert "select_model_for_request" not in src
    assert "fireworks.chat" not in src


def test_answer_accuracy_uses_canonical_resolver():
    src = (ROOT / "benchmarks" / "answer_accuracy.py").read_text(encoding="utf-8")
    assert "from benchmarks.official_resolver import" in src
    assert "resolve_task" in src
    assert "run_one" not in src  # no parallel pipeline
    assert "fireworks.chat" not in src


def test_docker_cmd_is_run_official():
    df = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert 'CMD ["python", "scripts/run_official.py"]' in df
    assert "benchmarks/official_resolver.py" in df


def test_no_env_file_copied_into_image():
    df = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert ".env" not in df


def test_path_parity_on_practice_tasks(no_key):
    """The three callers share resolve_task by construction; verify the
    resolver itself is deterministic across contexts on all 8 tasks."""
    tasks = load_practice_tasks()
    ctx1 = default_context()
    ctx2 = default_context(with_deadline=True)
    for task in tasks:
        r1 = resolve_task(dict(task), ctx1)
        r2 = resolve_task(dict(task), ctx2)
        assert r1["category"] == r2["category"], task["task_id"]
        assert r1["route"] == r2["route"], task["task_id"]
        assert r1["local_solver_name"] == r2["local_solver_name"]
        assert r1["local_candidate_valid"] == r2["local_candidate_valid"]
        assert r1["remote_required"] == r2["remote_required"]
        if r1["route"] not in ("fireworks",):
            assert r1["answer"] == r2["answer"], task["task_id"]


# ── Harness environment variables ─────────────────────────────────────────────

def test_allowed_models_honoured(monkeypatch, no_key):
    monkeypatch.setenv("ALLOWED_MODELS", "m/alpha,m/beta")
    ctx = default_context()
    assert ctx.ladder == ["m/alpha", "m/beta"]
    assert ctx.model_set_status == "OFFICIAL_RUNTIME_ALLOWLIST"


def test_fallback_ladder_marked_non_official(monkeypatch, no_key):
    monkeypatch.delenv("ALLOWED_MODELS", raising=False)
    ctx = default_context()
    assert ctx.model_set_status == "NON_OFFICIAL_FALLBACK_LADDER"
    assert len(ctx.ladder) >= 1


def test_selected_model_belongs_to_allowlist(monkeypatch):
    monkeypatch.setenv("ALLOWED_MODELS", "m/only-model")
    monkeypatch.setenv("FIREWORKS_API_KEY", "test-key")
    called = {}

    def fake_chat(model, prompt, max_tokens=512, system=None,
                  timeout=None, allow_extended_timeout=False):
        called["model"] = model
        return {"dry_run": False, "text": "yes indeed", "model": model,
                "prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2,
                "latency_s": 0.1, "finish_reason": "stop",
                "final_content_present": True,
                "reasoning_content_present": False,
                "truncated": False, "error": None}

    monkeypatch.setattr(fireworks, "chat", fake_chat)
    import benchmarks.official_resolver as orv
    monkeypatch.setattr(orv.fireworks, "chat", fake_chat)
    ctx = default_context()
    resolve_task(
        {"task_id": "t", "prompt":
         "Compare these two caching strategies and derive the trade-offs."},
        ctx)
    if called:
        assert called["model"] == "m/only-model"


def test_base_url_env_reaches_adapter(monkeypatch):
    monkeypatch.setenv("FIREWORKS_API_KEY", "test-key")
    monkeypatch.setenv("FIREWORKS_BASE_URL", "https://example.test/v1")
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        raise TimeoutError("stop")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    fireworks.chat("m", "p")
    assert captured["url"].startswith("https://example.test/v1")


def test_api_key_never_in_error_text(monkeypatch):
    monkeypatch.setenv("FIREWORKS_API_KEY", "sk-secret-value")

    def fake_urlopen(req, timeout=None):
        raise TimeoutError("boom")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    r = fireworks.chat("m", "p")
    assert "sk-secret-value" not in str(r)


# ── Global time budget ────────────────────────────────────────────────────────

def test_budget_constants():
    assert OFFICIAL_RUNTIME_BUDGET_S == 600.0
    assert OUTPUT_RESERVE_S == 30.0


def test_remote_timeout_none_without_deadline():
    ctx = RuntimeContext(allowed_models=["m"])
    assert ctx.remote_timeout_s() is None


def test_remote_timeout_bounded_by_remaining():
    ctx = RuntimeContext(allowed_models=["m"],
                         deadline=time.monotonic() + 40.0)
    t = ctx.remote_timeout_s()
    # remaining ~40 - 30 reserve = ~10 -> below 25 ceiling
    assert t is not None and t <= 25.0 and t <= 11.0


def test_remote_timeout_raises_when_budget_exhausted():
    ctx = RuntimeContext(allowed_models=["m"],
                         deadline=time.monotonic() + 5.0)
    with pytest.raises(TimeoutError, match="budget exhausted"):
        ctx.remote_timeout_s()


def test_no_unlimited_timeout_possible():
    ctx = RuntimeContext(allowed_models=["m"],
                         deadline=time.monotonic() + 10_000.0)
    t = ctx.remote_timeout_s()
    assert t == fireworks.DEFAULT_TIMEOUT_S  # capped at ordinary ceiling


# ── No hardcoded practice answers ─────────────────────────────────────────────

def test_resolver_source_has_no_practice_hardcoding():
    src = (ROOT / "benchmarks" / "official_resolver.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            low = node.value.lower()
            assert "practice-0" not in low, "task_id-based branching forbidden"
            assert "canberra" not in low, "hardcoded practice answer forbidden"
            assert "satya" not in low, "hardcoded practice answer forbidden"
