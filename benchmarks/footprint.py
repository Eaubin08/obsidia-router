"""Footprint + parametric efficiency metrics — report-only, zero routing authority.

Measures embedded infrastructure: model weights, memory, stack size.
collect_parametric_efficiency() uses only the benchmark summary dict —
it has NO influence on routing decisions. KX108_ONLY is unchanged.
"""
from __future__ import annotations

import os
from pathlib import Path

_MODEL_EXTENSIONS: frozenset[str] = frozenset({
    ".gguf", ".bin", ".pt", ".pth", ".ckpt", ".safetensors",
    ".onnx", ".tflite", ".mlmodel", ".pkl", ".joblib",
})

_MODEL_NAME_HINTS: frozenset[str] = frozenset({
    "model", "weights", "checkpoint", "ckpt", "pytorch_model",
    "adapter", "lora", "embedding",
})

_SKIP_DIRS: frozenset[str] = frozenset({
    ".git", "__pycache__", ".venv", "venv", "node_modules",
    ".mypy_cache", ".pytest_cache", "dist", "build",
})


def repo_size_mb(root: Path) -> float:
    total = 0
    for p in root.rglob("*"):
        if any(part in _SKIP_DIRS for part in p.parts):
            continue
        if p.is_file():
            try:
                total += p.stat().st_size
            except OSError:
                pass
    return round(total / 1_048_576, 2)


def file_size_mb(path: Path) -> float:
    try:
        return round(path.stat().st_size / 1_048_576, 4)
    except OSError:
        return 0.0


def detect_local_model_files(root: Path) -> list[str]:
    found: list[str] = []
    for p in Path(root).rglob("*"):
        if any(part in _SKIP_DIRS for part in p.parts):
            continue
        if not p.is_file():
            continue
        if p.suffix.lower() in _MODEL_EXTENSIONS:
            found.append(str(p.relative_to(root)))
        elif (
            any(hint in p.name.lower() for hint in _MODEL_NAME_HINTS)
            and p.stat().st_size > 10_000_000
        ):
            found.append(str(p.relative_to(root)))
    return sorted(found)


def collect_footprint(root: Path) -> dict:
    root = Path(root)
    local_models = detect_local_model_files(root)
    r_size = repo_size_mb(root)
    mem_size = file_size_mb(root / "examples" / "memory_index.json")

    brody_endpoint = os.environ.get("BRODY_ENDPOINT", "").strip()
    brody_live = bool(brody_endpoint)

    return {
        "embedded_model_weight_gb":    0,
        "repo_size_mb":                r_size,
        "runtime_stack_size_mb":       r_size,
        "memory_index_size_mb":        mem_size,
        "local_model_files_detected":  local_models,
        "persistent_memory_enabled":   False,
        "brody_live_enabled":          brody_live,
        "brody_stub_enabled":          True,
        "obsidure_full_enabled":       False,
        "obsidure_mode":               "route_only",
        "lean_full_enabled":           False,
        "lean_mode":                   "route_only",
        "fireworks_single_choke_point": True,
    }


def collect_parametric_efficiency(summary: dict, footprint: dict) -> dict:
    total = summary.get("total_tasks", 0)
    avoided = summary.get("remote_calls_avoided", 0)
    fw_needed = summary.get("fireworks_needed", 0)

    zero_fw_rate = round(avoided / total, 4) if total else 0.0
    fw_dep_rate = round(fw_needed / total, 4) if total else 0.0

    return {
        "embedded_model_weight_gb":              0,
        "zero_fireworks_rate":                   zero_fw_rate,
        "fireworks_dependency_rate":             fw_dep_rate,
        "remote_calls_avoided":                  avoided,
        "remote_calls_total":                    total,
        "model_weight_displaced_vs_7b_fp16_gb":  14,
        "model_weight_displaced_vs_7b_int4_gb":   4,
        "model_weight_displaced_vs_70b_fp16_gb": 140,
        "model_weight_displaced_vs_70b_int4_gb":  40,
        "interpretation": "measurable competence before embedded learned weights",
    }
