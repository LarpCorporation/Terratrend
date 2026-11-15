"""Scientific tests must never read or overwrite the user's saved credential."""
import pytest
import earthdata_credentials


@pytest.fixture(autouse=True)
def isolate_earthdata_credentials(tmp_path,monkeypatch):
    monkeypatch.setattr(earthdata_credentials,'DIRECTORY',tmp_path/'terratrend-credentials')
    monkeypatch.setattr(earthdata_credentials,'_find_secret_tool',lambda:None)
    monkeypatch.setattr(earthdata_credentials,'_cached',None)
    monkeypatch.setattr(earthdata_credentials,'_backend',None)
