import os
from pathlib import Path

import pytest

from beautycrawler.api.routers import products


def test_products_load_independent_of_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert os.getcwd() == str(tmp_path)
    loaded = products.load_products()
    assert loaded, "bundled sample data should not be empty"
    assert {"id", "name", "brand"} <= loaded[0].keys()
