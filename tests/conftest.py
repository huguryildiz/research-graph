import pathlib
import shutil

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture
def example_run(tmp_path):
    """A writable copy of example-run. Never mutate the committed one."""
    target = tmp_path / "run"
    shutil.copytree(ROOT / "example-run", target)
    return target
