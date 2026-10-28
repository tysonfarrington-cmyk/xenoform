"""Every test runs against an empty local stills library (stills.root) so the shipped pools alone are what
the chain sees, and no test writes usage or grown stills into work/ui/objects. The Setup check never asks the
machine's own ComfyUI for its model lists: it reads the folder a test made, unless the test fakes a listing."""
import pytest


@pytest.fixture(autouse=True)
def _empty_library(tmp_path_factory, monkeypatch):
    monkeypatch.setenv("XENO_STILLS", str(tmp_path_factory.mktemp("stills")))


@pytest.fixture(autouse=True)
def _final_on_ltx23(monkeypatch):
    """The Final tier's fakes were written for the LTX-2.3 graph (nodes 100/101/28); the default is LTX-2.5 where its
    files are on disk, so every test pins LTX-2.3 unless it sets XENO_FINAL_MODEL itself."""
    monkeypatch.setenv("XENO_FINAL_MODEL", "ltx23")


@pytest.fixture(autouse=True)
def _comfy_lists_no_models(monkeypatch):
    monkeypatch.setattr("xenoform.models_setup._fetch_listing", lambda base, folder: None)
    monkeypatch.setattr("xenoform.models_setup._LISTED", {})
