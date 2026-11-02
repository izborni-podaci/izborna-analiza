from pathlib import Path

import pytest

from izbori.history import Archive

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
R2026 = "680072"


@pytest.fixture(scope="session")
def archive() -> Archive:
    return Archive(DATA)


@pytest.fixture(scope="session")
def round2026(archive):
    return archive.load(R2026)


@pytest.fixture(scope="session")
def raw2026() -> bytes:
    return (DATA / "rounds" / R2026 / "results.csv").read_bytes()
