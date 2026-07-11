"""LOT E hardening: metadata-only sidecar and complete token telemetry."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import patch


def _load_official_runner():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "run_official.py"
    spec = importlib.util.spec_from_file_location(
        "run_official_hardening_test", path
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_official_sidecar_is_metadata_only_and_keeps_token_breakdown(
    tmp_path, monkeypatch
):
    runner = _load_official_runner()

    monkeypatch.setenv(
        "ALLOWED_MODELS", "small,medium,gpt-oss-120b"
    )
    monkeypatch.delenv("FIREWORKS_API_KEY", raising=False)

    input_path = tmp_path / "tasks.json"
    output_path = tmp_path / "results.json"
    input_path.write_text(
        json.dumps([
            {
                "task_id": "local",
                "prompt": "explique le contexte de cette decision",
            },
            {
                "task_id": "remote",
                "prompt": (
                    "Compare microservices and monolithic architecture "
                    "trade-offs in depth"
                ),
            },
        ]),
        encoding="utf-8",
    )

    captured = []

    def fake_chat(model, prompt, max_tokens=512, system=None, timeout=None):
        captured.append({
            "model": model,
            "prompt_chars": len(prompt),
            "system_chars": len(system) if system else None,
        })
        return {
            "dry_run": False,
            "model": model,
            "text": "[captured answer]",
            "prompt_tokens": 7,
            "completion_tokens": 13,
            "total_tokens": 20,
            "latency_s": 0.01,
        }

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_official.py",
            "--input",
            str(input_path),
            "--output",
            str(output_path),
        ],
    )

    with patch("app.adapters.fireworks.chat", side_effect=fake_chat):
        assert runner.main() == 0

    results = json.loads(output_path.read_text(encoding="utf-8"))
    assert all(set(row) == {"task_id", "answer"} for row in results)

    sidecar = json.loads(
        (tmp_path / "track1_triage_receipts.json").read_text(
            encoding="utf-8"
        )
    )
    rows = {row["id"]: row for row in sidecar["tasks"]}

    forbidden = {
        "request",
        "prompt",
        "output",
        "answer",
        "memory_entry",
        "system",
        "contract_prompt",
    }
    for row in rows.values():
        assert forbidden.isdisjoint(row)

    assert rows["local"]["selected_model"] is None
    assert rows["local"]["actual_model_used"] is None
    assert rows["local"]["contract_model_preference"] is None
    assert rows["local"]["raw_prompt_chars"] is None
    assert rows["local"]["system_prompt_chars"] is None

    remote = rows["remote"]
    assert remote["selected_model"] == captured[0]["model"]
    assert remote["actual_model_used"] == captured[0]["model"]
    assert remote["prompt_tokens"] == 7
    assert remote["completion_tokens"] == 13
    assert remote["fireworks_tokens"] == 20
    assert remote["raw_prompt_chars"] == captured[0]["prompt_chars"]
    assert remote["system_prompt_chars"] == captured[0]["system_chars"]


def test_manual_escalation_blocks_copy_token_breakdown():
    root = Path(__file__).resolve().parents[1]
    for relative in (
        "scripts/run_official.py",
        "benchmarks/run_benchmark.py",
    ):
        source = (root / relative).read_text(encoding="utf-8")
        assert (
            '["prompt_tokens"] = _fw.get("prompt_tokens", 0)'
            in source
        )
        assert (
            '["completion_tokens"] = _fw.get("completion_tokens", 0)'
            in source
        )


def test_docs_do_not_claim_committed_report_already_has_section():
    root = Path(__file__).resolve().parents[1]
    metrics = (
        root / "docs" / "TRACK3_METRICS.md"
    ).read_text(encoding="utf-8")
    submission = (
        root / "docs" / "TRACK3_SUBMISSION.md"
    ).read_text(encoding="utf-8")

    assert "currently committed report predates LOT E" in metrics
    assert "committed REPORT predates LOT E" in submission
