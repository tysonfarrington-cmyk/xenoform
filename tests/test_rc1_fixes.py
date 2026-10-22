"""contest-rc1: paid cloud opt-in, real cancel of queued morphs, story grammar, honest timing copy."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from xenoform import cloud_morph as cm
from xenoform import morph_pass as mp
from xenoform.turbo import JobCancelled

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "xenoform" / "ui_static"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("XENO_PAID_CLOUD", raising=False)
    monkeypatch.setenv("XENO_CLOUD_NEVER", "1")
    monkeypatch.delenv("COMFY_ORG_API_KEY", raising=False)


# --- 1. Paid cloud renders are opt-in -------------------------------------------------

def test_paid_cloud_is_off_by_default_and_needs_an_explicit_opt_in(monkeypatch):
    assert cm.paid_cloud_enabled() is False
    assert cm.paid_cloud_enabled({"comfy": {"addons": True}}) is False  # Add-ons alone is not the opt-in
    assert cm.paid_cloud_enabled(None, requested=True) is True  # the Settings toggle
    assert cm.paid_cloud_enabled({"comfy": {"paid_cloud": True}}) is True
    monkeypatch.setenv("XENO_PAID_CLOUD", "1")
    assert cm.paid_cloud_enabled() is True and cm.paid_env_state() == "on"
    monkeypatch.setenv("XENO_PAID_CLOUD", "0")
    assert cm.paid_cloud_enabled(None, requested=True) is False and cm.paid_env_state() == "off"


def test_estimate_route_refuses_without_opt_in_and_demo_reports_the_switch(monkeypatch):
    from fastapi.testclient import TestClient

    from xenoform.ui import create_app

    client = TestClient(create_app())
    demo = client.get("/api/demo").json()
    assert demo["paid_cloud"]["env"] == "" and demo["paid_cloud"]["label"] == cm.OPT_IN_LABEL
    res = client.post("/api/cloud/estimate", json={"audio_id": "demo", "vibe": "black"})
    assert res.status_code == 403
    monkeypatch.setenv("XENO_PAID_CLOUD", "0")
    res = client.post("/api/cloud/estimate", json={"audio_id": "demo", "vibe": "black", "paid_cloud": True})
    assert res.status_code == 403


def test_desk_hides_cloud_quality_unless_opted_in():
    app = (STATIC / "app.js").read_text(encoding="utf-8")
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert 'id="paid-cloud"' in html and "Paid cloud renders (partner node, not open weights)" in html
    assert "if (!state.paidCloud)" in app
    assert "cloud_quality: !!(state.paidCloud" in app
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "100% open weights by default" in readme and "XENO_PAID_CLOUD" in readme


# --- 3d. Stop cancels the morphs already queued ----------------------------------------

class FakeJob:
    def __init__(self, job_id, status):
        self.id = job_id
        self.status = status
        self.cancelled = False

    def refresh(self):
        return self

    def cancel(self):
        self.cancelled = True
        self.status = "canceled"
        return self


def test_stop_cancels_every_unfinished_job_and_stops_the_chain():
    jobs = [FakeJob("a", "succeeded"), FakeJob("b", "in_progress"), FakeJob("c", "pending"), FakeJob("d", "pending")]
    with pytest.raises(JobCancelled, match="3 queued morphs"):
        mp.wait_or_cancel(jobs[1], jobs, lambda: True, poll_s=0)
    assert [j.cancelled for j in jobs] == [False, True, True, True]


def test_wait_returns_when_the_job_finishes_and_no_stop():
    job = FakeJob("a", "pending")
    calls = {"n": 0}

    def refresh():
        calls["n"] += 1
        if calls["n"] >= 3:
            job.status = "succeeded"
        return job

    job.refresh = refresh
    mp.wait_or_cancel(job, [job], lambda: False, poll_s=0)
    assert job.status == "succeeded" and not job.cancelled


def test_morph_pass_and_cloud_pass_take_the_desk_cancel():
    import inspect

    assert "cancel" in inspect.signature(mp.run_morph_pass).parameters
    assert "cancel" in inspect.signature(cm.run_cloud_quality).parameters
    src = (ROOT / "src" / "xenoform" / "turbo.py").read_text(encoding="utf-8")
    assert "run_morph_pass(directed, scenes, Path(audio_path), out_path, work, tuned, state, report, cancel=cancel)" in src


def test_cloud_pass_never_starts_after_a_stop(tmp_path, monkeypatch):
    def fake_chain(engine, *a, **kw):
        if engine != "local":
            raise AssertionError("the paid pass must not start after Stop")
        return {"file": str(tmp_path / "x.mp4")}

    monkeypatch.setattr(cm, "run_chain", fake_chain)
    with pytest.raises(JobCancelled, match="Nothing was sent"):
        cm.run_cloud_quality({"duration": 4.0}, tmp_path / "a.wav", tmp_path / "o.mp4", tmp_path, {}, {"vibe": "black"},
                             lambda *a: None, cancel=lambda: True)


# --- 3c. Story text reads as sentences, verbs are not used as nouns ----------------------

VIBE_LINES = [
    "A gold pour becomes a ring in a dark forge.",
    "A paper boat crosses a bright kitchen.",
    "A flower opens on a green hill.",
    "A neon sign holds one quiet street.",
    "A swimmer crosses a calm harbour.",
    "A star field turns over a dark shore.",
    "Black glass grows from one living form into the next.",
]


@pytest.mark.parametrize("register", ["pynchon", "rome", "tolkien", "lecarre"])
def test_vibe_stories_have_no_verb_nouns(register):
    from xenoform.analyze import read_features
    from xenoform.director import register_by_id
    from xenoform.storyboard import parse_brief, plan_with_hook

    features = read_features(ROOT / "examples" / "demo_features.json")
    for line in VIBE_LINES:
        base = parse_brief(line)["base"]
        scenes, _ = plan_with_hook(features, register_by_id(register), line)
        for scene in scenes:
            action = scene["action"]
            assert not re.search(rf"\bthe {re.escape(base)}\b", action), (register, line, action)
            assert not re.search(r"\bthe one\b", action), (register, line, action)


def test_making_screen_joins_story_lines_as_sentences_and_has_no_static_minute():
    app = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "storySentence(scene.action)" in app
    assert "About a minute" not in app and "About 1 minute" not in app and "about a minute" not in app
    assert "easyProgressText(job)" in app
    turbo = (ROOT / "src" / "xenoform" / "turbo.py").read_text(encoding="utf-8")
    assert "about a minute" not in turbo.lower()


# --- 3b. Tutorial card never covers the control it asks for -----------------------------

def test_tutorial_card_avoids_the_hit_target():
    js = (STATIC / "tutorial.js").read_text(encoding="utf-8")
    assert "function keepNode" in js and "overlap(box, keep) * 1000" in js and "function revealKeep" in js


def test_queued_jobs_are_cancelled_before_the_running_one_and_a_slipped_job_is_caught():
    order = []

    class Job(FakeJob):
        def cancel(self):
            order.append(self.id)
            if self.id == "run":
                # Interrupting the running job lets ComfyUI start "next"; its first cancel is lost.
                nxt.status = "running"
            elif self.id == "next" and order.count("next") == 1 and nxt.status == "running":
                return self
            return super().cancel()

    run, nxt, last = Job("run", "running"), Job("next", "pending"), Job("last", "pending")
    n = mp.cancel_jobs([run, nxt, last], settle_s=2.0)
    assert order[:3] == ["next", "last", "run"]
    assert n == 3 and all(j.status == "canceled" for j in (run, nxt, last))
