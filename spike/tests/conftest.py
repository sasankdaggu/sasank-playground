from __future__ import annotations

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

SPIKE_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(SPIKE_ROOT / ".env", override=False)


@pytest.fixture()
def spike_root() -> Path:
    return SPIKE_ROOT


@pytest.fixture()
def sample_fixture_dir(spike_root: Path) -> Path:
    d = spike_root / "tests" / "fixtures"
    d.mkdir(exist_ok=True)
    return d
