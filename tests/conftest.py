"""Shared pytest fixtures for openroland-jxl tests.

Every fixture and fixture file here is synthetic; no customer files,
names, or coordinates are used anywhere in this test suite.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    """Return the directory containing the synthetic ``.jxl`` fixtures."""
    return _FIXTURES_DIR


@pytest.fixture
def minimal_jxl(fixtures_dir: Path) -> Path:
    """Return the path of the unqualified, no-namespace JXL fixture."""
    return fixtures_dir / "minimal.jxl"


@pytest.fixture
def namespaced_jxl(fixtures_dir: Path) -> Path:
    """Return the path of the default-namespace JXL fixture.

    This fixture also exercises ``Environment``/EPSG metadata capture and
    ``FieldBook``/``PointRecord`` merge-by-ID behavior.
    """
    return fixtures_dir / "namespaced.jxl"


@pytest.fixture
def keyed_in_and_measured_jxl(fixtures_dir: Path) -> Path:
    """Return the path of the mixed KeyedIn/measured JXL fixture.

    This fixture also contains one point with a non-numeric Grid
    coordinate to exercise issue reporting.
    """
    return fixtures_dir / "keyed_in_and_measured.jxl"


@pytest.fixture
def survey_pro_jxl(fixtures_dir: Path) -> Path:
    """Return the Survey Pro-style fixture with attribute PointRecord IDs."""
    return fixtures_dir / "survey_pro.jxl"
