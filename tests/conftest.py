"""Every test runs against an empty local stills library (stills.root) so the shipped pools alone are what
the chain sees, and no test writes usage or grown stills into work/ui/objects."""
import pytest


@pytest.fixture(autouse=True)
def _empty_library(tmp_path_factory, monkeypatch):
    monkeypatch.setenv("XENO_STILLS", str(tmp_path_factory.mktemp("stills")))
