"""
Desktop Timer - Pytest configuration and shared fixtures.
"""
from __future__ import annotations

import sys
from pathlib import Path
import pytest

# Add project root directory to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def temp_data_dir(tmp_path: Path) -> Path:
    """Temporary test data directory."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir
