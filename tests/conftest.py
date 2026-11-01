"""Every test runs against an empty local stills library (stills.root) so the shipped pools alone are what
the chain sees, and no test writes usage or grown stills into work/ui/objects. The Setup check never asks the
machine's own ComfyUI for its model lists: it reads the folder a test made, unless the test fakes a listing."""
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _empty_library(tmp_path_factory, monkeypatch):
    monkeypatch.setenv("XENO_STILLS", str(tmp_path_factory.mktemp("stills")))


@pytest.fixture(autouse=True)
def _no_taste_file(tmp_path_factory, monkeypatch):
    """No taste file (configs/taste.json) unless a test loads one: the suite pins the cut as it is with no rules, the way
    the empty library pins the shipped pools; the taste tests point XENO_TASTE at the shipped file or a fixture."""
    monkeypatch.setenv("XENO_TASTE", str(tmp_path_factory.getbasetemp() / "no_taste_file.json"))


@pytest.fixture(autouse=True)
def _empty_morph_cache(tmp_path_factory, monkeypatch):
    """A morph cache of its own for every test (xenoform.morph_cache), so a fake render never lands in work/ui and no
    test is answered by another's clip."""
    monkeypatch.setenv("XENO_MORPH_CACHE", str(tmp_path_factory.mktemp("morph_cache")))


@pytest.fixture(autouse=True)
def _final_on_ltx23(monkeypatch):
    """The Final tier's fakes were written for the LTX-2.3 graph (nodes 100/101/28); the default is LTX-2.5 where its
    files are on disk, so every test pins LTX-2.3 unless it sets XENO_FINAL_MODEL itself."""
    monkeypatch.setenv("XENO_FINAL_MODEL", "ltx23")


@pytest.fixture(autouse=True)
def _comfy_lists_no_models(monkeypatch):
    monkeypatch.setattr("xenoform.models_setup._fetch_listing", lambda base, folder: None)
    monkeypatch.setattr("xenoform.models_setup._LISTED", {})


@pytest.fixture
def frozen_songs(monkeypatch):
    """The desk answers a bundled song from the frozen analyses (tests/fixtures/analyses), as the planner's tests read them,
    so a rebuilt song moves no plan these tests pin."""
    from xenoform import songs_api, ui

    frozen = Path(__file__).parent / "fixtures" / "analyses"
    monkeypatch.setattr(songs_api, "shipped_features_path", lambda row: frozen / f"{row['id']}.features.json")
    for key in [k for k in list(dict.keys(ui._FEATURES)) if str(k).startswith("song-")]:
        dict.pop(ui._FEATURES, key, None)
    yield
    for key in [k for k in list(dict.keys(ui._FEATURES)) if str(k).startswith("song-")]:
        dict.pop(ui._FEATURES, key, None)
