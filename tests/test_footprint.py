"""Tests — footprint + parametric efficiency metrics."""
from __future__ import annotations

from pathlib import Path

import pytest

from benchmarks.footprint import (
    collect_footprint,
    collect_parametric_efficiency,
    detect_local_model_files,
    file_size_mb,
    repo_size_mb,
)

ROOT = Path(__file__).resolve().parent.parent


# ── repo_size_mb ──────────────────────────────────────────────────────────────

def test_repo_size_mb_positive():
    size = repo_size_mb(ROOT)
    assert size > 0


def test_repo_size_mb_float():
    size = repo_size_mb(ROOT)
    assert isinstance(size, float)


def test_repo_size_mb_missing_dir(tmp_path):
    size = repo_size_mb(tmp_path)
    assert size == 0.0


# ── file_size_mb ──────────────────────────────────────────────────────────────

def test_file_size_mb_existing(tmp_path):
    f = tmp_path / "sample.json"
    f.write_text("x" * 1048576)
    assert file_size_mb(f) == pytest.approx(1.0, abs=0.01)


def test_file_size_mb_missing():
    assert file_size_mb(Path("/does/not/exist.json")) == 0.0


# ── detect_local_model_files ─────────────────────────────────────────────────

def test_detect_local_model_files_returns_list():
    result = detect_local_model_files(ROOT)
    assert isinstance(result, list)


def test_detect_local_model_files_no_weights_in_repo():
    result = detect_local_model_files(ROOT)
    assert result == [], f"Unexpected model files found: {result}"


def test_detect_local_model_files_finds_gguf(tmp_path):
    f = tmp_path / "model.gguf"
    f.write_bytes(b"\x00" * 100)
    result = detect_local_model_files(tmp_path)
    assert any("model.gguf" in r for r in result)


def test_detect_local_model_files_skips_git(tmp_path):
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    f = git_dir / "model.bin"
    f.write_bytes(b"\x00" * 100)
    result = detect_local_model_files(tmp_path)
    assert result == []


# ── collect_footprint ─────────────────────────────────────────────────────────

def test_footprint_embedded_model_weight_zero():
    fp = collect_footprint(ROOT)
    assert fp["embedded_model_weight_gb"] == 0


def test_footprint_local_model_files_empty():
    fp = collect_footprint(ROOT)
    assert fp["local_model_files_detected"] == []


def test_footprint_persistent_memory_disabled():
    fp = collect_footprint(ROOT)
    assert fp["persistent_memory_enabled"] is False


def test_footprint_brody_stub_enabled():
    fp = collect_footprint(ROOT)
    assert fp["brody_stub_enabled"] is True


def test_footprint_obsidure_route_only():
    fp = collect_footprint(ROOT)
    assert fp["obsidure_full_enabled"] is False
    assert fp["obsidure_mode"] == "route_only"


def test_footprint_lean_route_only():
    fp = collect_footprint(ROOT)
    assert fp["lean_full_enabled"] is False
    assert fp["lean_mode"] == "route_only"


def test_footprint_fireworks_single_choke_point():
    fp = collect_footprint(ROOT)
    assert fp["fireworks_single_choke_point"] is True


def test_footprint_repo_size_positive():
    fp = collect_footprint(ROOT)
    assert fp["repo_size_mb"] > 0


def test_footprint_has_all_required_fields():
    fp = collect_footprint(ROOT)
    required = {
        "embedded_model_weight_gb",
        "repo_size_mb",
        "runtime_stack_size_mb",
        "memory_index_size_mb",
        "local_model_files_detected",
        "persistent_memory_enabled",
        "brody_live_enabled",
        "brody_stub_enabled",
        "obsidure_full_enabled",
        "obsidure_mode",
        "lean_full_enabled",
        "lean_mode",
        "fireworks_single_choke_point",
    }
    assert required <= set(fp.keys())


# ── collect_parametric_efficiency ─────────────────────────────────────────────

def _make_summary(total=18, avoided=15, fw=3) -> dict:
    return {
        "total_tasks": total,
        "remote_calls_avoided": avoided,
        "fireworks_needed": fw,
    }


def test_parametric_efficiency_embedded_weight_zero():
    pe = collect_parametric_efficiency(_make_summary(), collect_footprint(ROOT))
    assert pe["embedded_model_weight_gb"] == 0


def test_parametric_efficiency_zero_fireworks_rate():
    pe = collect_parametric_efficiency(_make_summary(18, 15, 3), collect_footprint(ROOT))
    assert pe["zero_fireworks_rate"] == pytest.approx(15 / 18, abs=0.001)


def test_parametric_efficiency_fireworks_dependency_rate():
    pe = collect_parametric_efficiency(_make_summary(18, 15, 3), collect_footprint(ROOT))
    assert pe["fireworks_dependency_rate"] == pytest.approx(3 / 18, abs=0.001)


def test_parametric_efficiency_7b_fp16():
    pe = collect_parametric_efficiency(_make_summary(), collect_footprint(ROOT))
    assert pe["model_weight_displaced_vs_7b_fp16_gb"] == 14


def test_parametric_efficiency_7b_int4():
    pe = collect_parametric_efficiency(_make_summary(), collect_footprint(ROOT))
    assert pe["model_weight_displaced_vs_7b_int4_gb"] == 4


def test_parametric_efficiency_70b_fp16():
    pe = collect_parametric_efficiency(_make_summary(), collect_footprint(ROOT))
    assert pe["model_weight_displaced_vs_70b_fp16_gb"] == 140


def test_parametric_efficiency_70b_int4():
    pe = collect_parametric_efficiency(_make_summary(), collect_footprint(ROOT))
    assert pe["model_weight_displaced_vs_70b_int4_gb"] == 40


def test_parametric_efficiency_interpretation():
    pe = collect_parametric_efficiency(_make_summary(), collect_footprint(ROOT))
    assert "competence" in pe["interpretation"]


def test_parametric_efficiency_has_all_fields():
    pe = collect_parametric_efficiency(_make_summary(), collect_footprint(ROOT))
    required = {
        "embedded_model_weight_gb",
        "zero_fireworks_rate",
        "fireworks_dependency_rate",
        "remote_calls_avoided",
        "remote_calls_total",
        "model_weight_displaced_vs_7b_fp16_gb",
        "model_weight_displaced_vs_7b_int4_gb",
        "model_weight_displaced_vs_70b_fp16_gb",
        "model_weight_displaced_vs_70b_int4_gb",
        "interpretation",
    }
    assert required <= set(pe.keys())


def test_parametric_efficiency_zero_total_safe():
    pe = collect_parametric_efficiency(
        {"total_tasks": 0, "remote_calls_avoided": 0, "fireworks_needed": 0},
        {},
    )
    assert pe["zero_fireworks_rate"] == 0.0
    assert pe["fireworks_dependency_rate"] == 0.0


def test_parametric_efficiency_no_routing_fields():
    pe = collect_parametric_efficiency(_make_summary(), collect_footprint(ROOT))
    routing_authority_keys = {"route", "decision", "gate", "level", "ir", "model_ladder"}
    assert not (routing_authority_keys & set(pe.keys())), (
        "parametric_efficiency must not contain routing authority fields"
    )
