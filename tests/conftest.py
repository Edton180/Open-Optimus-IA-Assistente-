import pytest


@pytest.fixture(autouse=True)
def pasta_isolada(tmp_path, monkeypatch):
    monkeypatch.setenv("OPTIMUS_HOME", str(tmp_path / "optimus"))
    yield tmp_path
