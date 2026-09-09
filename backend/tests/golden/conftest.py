# -*- coding: utf-8 -*-
"""Golden suite fixtures (S2). Needs the loaded database (skipped without DATABASE_URL) and the plausibility envelope in
FPS_DATASET_DIR (pipeline/src/pipeline/plausibility_envelope.py). One CompositionRoot per session: the same engine the API serves."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

PROFILES_DIR = Path(__file__).resolve().parent / "profiles"
SNAPSHOTS_DIR = Path(__file__).resolve().parent / "snapshots"


def load_profiles() -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) | {"name": p.stem} for p in sorted(PROFILES_DIR.glob("*.json"))]


@pytest.fixture(scope="session")
def engine():
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set (golden tests need the loaded database)")
    from finalprosports.domain.composition.policy.plausibility_policy import PlausibilityEnvelope
    from finalprosports.infrastructure.composition_root import CompositionRoot
    from finalprosports.infrastructure.config.paths import dataset_dir
    root = CompositionRoot.from_env()
    env_path = dataset_dir() / "plausibility_envelope.json"
    if not env_path.exists():
        pytest.skip(f"plausibility envelope not found: {env_path.name} (run make envelope)")
    envelope = PlausibilityEnvelope.from_dict(json.loads(env_path.read_text(encoding="utf-8")))
    pid = root.configured_professional_id
    return {"root": root, "pid": pid, "envelope": envelope, "rules": root.rules.all(pid), "catalog": root.catalog}


def pytest_addoption(parser):
    parser.addoption("--update-snapshots", action="store_true", default=False, help="golden: accept the current engine output as the new snapshot")


@pytest.fixture(scope="session")
def update_snapshots(request) -> bool:
    return bool(request.config.getoption("--update-snapshots") or os.environ.get("GOLDEN_UPDATE"))
