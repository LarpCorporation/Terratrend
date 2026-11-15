"""Tests must never read or overwrite the user's saved data.

Two things are isolated for the whole session:

* the remembered Earthdata/AppEEARS credential store, and
* the durable completed-result library, because job execution now persists a
  completed analysis and a test run must never appear in the Saved
  investigations list as a genuine scientific finding.
"""
import pytest
import earthdata_credentials
import result_store


@pytest.fixture(autouse=True)
def isolate_earthdata_credentials(tmp_path,monkeypatch):
    monkeypatch.setattr(earthdata_credentials,'DIRECTORY',tmp_path/'terratrend-credentials')
    monkeypatch.setattr(earthdata_credentials,'_find_secret_tool',lambda:None)
    monkeypatch.setattr(earthdata_credentials,'_cached',None)
    monkeypatch.setattr(earthdata_credentials,'_backend',None)


@pytest.fixture(autouse=True)
def isolate_saved_results(tmp_path, monkeypatch):
    """Point the durable result library at a disposable database."""
    database = tmp_path / "results.sqlite3"
    monkeypatch.setattr(result_store, "_db_path", lambda: str(database))
    yield database
