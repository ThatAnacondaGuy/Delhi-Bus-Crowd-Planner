from pathlib import Path

import pytest

from src.pipeline.db import connect


@pytest.fixture
def toy_gtfs_dir() -> Path:
    return Path(__file__).parent / "fixtures" / "toy_gtfs"


@pytest.fixture
def con():
    c = connect()
    yield c
    c.close()
