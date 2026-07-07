"""Random dynamic batches.

V1 and V2 are seeded reproducible benchmark suites.
This module adds exploratory random batches: cases vary across runs unless a
base seed is provided, and every batch records its seed for replay.
"""

from __future__ import annotations

import random
from typing import Any

from benchmarks.dynamic_cases_v2 import FAMILIES_V2, SUFFIXES_V2


def generate_random_batch(batch_id: int, batch_size: int, seed: int) -> list[dict[str, Any]]:
    """Generate one replayable random batch."""

    rng = random.Random(seed)
    families = list(FAMILIES_V2.keys())
    cases: list[dict[str, Any]] = []

    for idx in range(batch_size):
        family = rng.choice(families)
        spec = FAMILIES_V2[family]
        prefixes = spec.get("prefixes", [""])
        suffixes = spec.get("suffixes", SUFFIXES_V2)

        raw = rng.choice(prefixes) + rng.choice(spec["cores"]) + rng.choice(suffixes)

        cases.append({
            "batch_id": batch_id,
            "case_id": idx + 1,
            "seed": seed,
            "family": family,
            "request": raw,
            "expected_routes": spec["expected_routes"],
            "level0_only": spec["level0_only"],
            "no_remote_model": spec.get("no_remote_model", False),
            "max_level": spec.get("max_level"),
        })

    return cases


def generate_random_batches(
    num_batches: int,
    batch_size: int,
    base_seed: int | None = None,
) -> dict[str, Any]:
    """Generate replayable random batches.

    If base_seed is None, a fresh seed is chosen. The chosen seed is returned
    so the exact run can be replayed later.
    """

    if num_batches < 0:
        raise ValueError("num_batches must be >= 0")
    if batch_size < 0:
        raise ValueError("batch_size must be >= 0")

    if base_seed is None:
        base_seed = random.SystemRandom().randrange(1, 2_147_483_647)

    batches = []
    for idx in range(num_batches):
        seed = base_seed + idx
        batches.append({
            "batch_id": idx + 1,
            "seed": seed,
            "cases": generate_random_batch(idx + 1, batch_size, seed),
        })

    return {
        "base_seed": base_seed,
        "num_batches": num_batches,
        "batch_size": batch_size,
        "batches": batches,
    }
