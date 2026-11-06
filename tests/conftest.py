"""
Desktop Timer - Pytest konfiguráció és megosztott fixture-ök.
"""
from __future__ import annotations

import sys
from pathlib import Path
import pytest

# Projekt gyökérkönyvtár hozzáadása az import útvonalhoz
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def temp_data_dir(tmp_path: Path) -> Path:
    """Ideiglenes teszt adatkönyvtár."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir

