from pathlib import Path
"""Unit tests for the MCP Simple-path tools, with the desk mocked."""

import json
import threading

import pytest

from xenoform import mcp_tools as mt


class FakeDesk:
    base = "http://127.0.0.1:9"

    def __init__(self):
        self.calls = []
        self.jobs = {}

    def json(self, method, path, body=None, timeout=None):
        self.calls.append((method, path, body))
        if path == "/api/demo":
            return {"blocks": [{"form": "rocket", "transition": "snap"}, {"form": "bulb", "transition": "snap"}], "scenes": [{"index": 0}], "title": "x"}
        if path == "/api/v1/health":
            return {"ok": True, "auth": "none"}
        if path == "/api/comfy":
            return {"ok": True, "url": "http://127.0.0.1:8188", "api_key": "sk-nope"}
        if path == "/api/diagnostics":
            return {"diagnostics": "Xenoform 0.2.0\ntier: 12 GB\nmissing: none"}
        if path.startswith("/api/simple/options"):
            return {"final": {"ready": True}}
        if path == "/api/v1/transitions":
            return {"transitions": [{"id": "snap", "label": "Snap"}, {"id": "ribbon", "label": "Ribbon"}]}
        if path == "/api/catalog":
            return {"forms": [{"id": "sphere", "name": "Liquid sphere", "svg": "<svg/>", "pack": "GR", "blurb": "b", "kind": "preset"}]}
        if path == "/api/generate":
            jid = f"j{len(self.jobs) + 1}"
            self.jobs[jid] = {"id": jid, "status": "running", "stage": "analyze", "progress": 0.0}
            return {"id": jid}
        if path == "/api/cloud/estimate":
            return {"token": "tok123", "can_submit": True, "estimate": {"usd": 1.2, "secret_key": "x"}}
        if path.startswith("/api/jobs/") and path.endswith("/cancel"):
            jid = path.split("/")[3]
            self.jobs[jid].update(status="cancelled", detail="Cancelled.")
            return self.jobs[jid]
        if path.startswith("/api/jobs/"):
            jid = path.split("/")[3]
            if jid not in self.jobs:
                raise mt.XenoformError("Desk answered 404: No such cut")
            job = self.jobs[jid]
            job["progress"] = min(1.0, job["progress"] + 0.5)
            if job["progress"] >= 1.0 and job["status"] == "running":
                job.update(status="done", stage="done", video=f"/api/jobs/{jid}/video?v=1")
            return dict(job)
        if path.startswith("/api/videos"):
            return {"videos": [{"id": "abc", "url": "/api/videos/abc/video", "vibe": "black"}]}
        raise mt.XenoformError("Desk answered 404: " + path)

    def upload(self, path, file, timeout=None):
        self.calls.append(("UPLOAD", path, file.name))
        if path == "/api/analyze":
            return {"audio_id": "aud1", "duration": 12.0}
        return {"id": "hero1"}

    def download(self, path, dest, timeout=None):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"mp4")
        return 3


@pytest.fixture
def app(tmp_path):
    return mt.App(FakeDesk(), state_path=tmp_path / "state.json")


def test_defaults_are_native_vertical_black_preview(app):
    s = app.settings()
    assert (s["aspect"], s["vertical_mode"], s["vibe"], s["tier"], s["cloud"]) == ("9:16", "native", "black", "preview", False)


def test_status_has_gpu_and_no_secrets(app):
    s = app.status()
    assert s["desk_ok"] and s["gpu_tier"] == "12 GB"
    assert "api_key" not in json.dumps(s)


def test_status_when_desk_is_down(tmp_path):
    a = mt.App(mt.Desk("http://127.0.0.1:9", timeout=1), state_path=tmp_path / "s.json")
    s = a.status()
    assert s["desk_ok"] is False and "Cannot reach" in s["detail"]


def test_lists(app):
    assert {v["id"] for v in app.vibes()["vibes"]} == set(mt.VIBES)
    assert app.transitions()["transitions"][0]["id"] == "snap"
    shapes = app.shapes()["shapes"]
    assert shapes[0]["id"] == "sphere" and "svg" not in shapes[0]


def test_autotune(app):
    assert "vibes" in app.autotune()
    assert app.autotune("liquid-gold")["vibe"] == "liquid-gold"
    with pytest.raises(mt.XenoformError, match="Unknown vibe"):
        app.autotune("nope")


@pytest.mark.parametrize("field,value", [("vibe", "pink"), ("aspect", "4:3"), ("tier", "ultra"),
                                         ("energy", "wild"), ("vertical_mode", "x"), ("transitions", "snap"),
                                         ("transitions", ["warp-9"]), ("prompt", "x" * 2001)])
def test_update_rejects_bad_values(app, field, value):
    with pytest.raises(mt.XenoformError):
        app.update(**{field: value})


def test_update_and_persist(app, tmp_path):
    app.update(vibe="Neon-Night", transitions=["snap"], beat_fx=False)
    again = mt.App(FakeDesk(), state_path=tmp_path / "state.json")
    assert again.settings()["vibe"] == "neon-night" and again.settings()["transitions"] == ["snap"]


def test_create_needs_prompt_or_image(app):
    with pytest.raises(mt.XenoformError, match="prompt"):
        app.create("")


def test_create_with_audio_and_image(app, tmp_path):
    song = tmp_path / "song.wav"
    song.write_bytes(b"RIFF")
    pic = tmp_path / "hero.png"
    pic.write_bytes(b"png")
    out = app.create("chrome jellyfish", vibe="ocean", audio_path=str(song), image_paths=[str(pic)])
    assert out["project"]["audio_id"] == "aud1" and out["project"]["images"][0]["name"] == "hero.png"
    assert out["project"]["vibe"] == "ocean"


def test_bad_files(app, tmp_path):
    with pytest.raises(mt.XenoformError, match="No file"):
        app.load_audio(str(tmp_path / "missing.wav"))
    (tmp_path / "a.txt").write_text("x")
    with pytest.raises(mt.XenoformError, match="not a audio"):
        app.load_audio(str(tmp_path / "a.txt"))
    with pytest.raises(mt.XenoformError):
        app.attach_image("")


def test_render_body_preview_is_dry_run(app):
    b = app.body()
    assert b["live"] is False and b["mode"] == "simple" and b["aspect"] == "9:16" and b["paid_cloud"] is False
    app.update(tier="final")
    b = app.body()
    assert b["live"] is True and b["quality_tier"] == "final"


def test_render_wait_output(app, tmp_path):
    app.create("test")
    job = app.start()["job_id"]
    done = app.wait(job, timeout_s=5, poll_s=0.01)
    assert done["status"] == "done" and done["preview_url"].endswith("v=1")
    assert done["output"]["path"].endswith(".mp4")
    saved = app.output(job, save_to=str(tmp_path / "out"))
    assert saved["saved_bytes"] == 3


def test_cancel(app):
    app.create("test")
    job = app.start()["job_id"]
    assert app.cancel(job)["status"] == "cancelled"
    assert app.progress(job)["status"] == "cancelled"


def test_bad_job_ids(app):
    for bad in ("", "../etc", "a b"):
        with pytest.raises(mt.XenoformError, match="job_id"):
            app.progress(bad)
    with pytest.raises(mt.XenoformError, match="No such cut"):
        app.progress("zzz")


def test_cloud_needs_confirm_and_hides_token(app):
    app.create("test")
    with pytest.raises(mt.XenoformError, match="confirm_spend"):
        app.start(cloud=True)
    desk = app.desk
    assert not any(c[1] == "/api/generate" for c in desk.calls)
    out = app.start(cloud=True, confirm_spend=True)
    assert "tok123" not in json.dumps(out) and "secret_key" not in json.dumps(out)
    sent = [c[2] for c in desk.calls if c[1] == "/api/generate"][-1]
    assert sent["cloud_confirm"] == "tok123" and sent["paid_cloud"] is True


def test_list_videos(app):
    v = app.videos(5)
    assert v["videos"][0]["url"].startswith("http://127.0.0.1:9/")


def test_concurrent_updates_and_renders(app):
    errors = []

    def worker(i):
        try:
            app.update(vibe=mt.VIBES[i % len(mt.VIBES)])
            app.start()
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(16)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors and len(app.jobs) == 16
    json.loads(app.path.read_text())


def test_scrub_nested():
    assert mt.scrub({"a": [{"token": 1, "b": 2}], "API_KEY": 3}) == {"a": [{"b": 2}]}


def test_guide_is_shared_with_docs():
    assert mt.GUIDE_FILE.name == "AI_GUIDE.md" and "Xenoform" in mt.read_guide()

def test_render_sends_the_desk_board_and_transitions(app):
    app.create("test")
    app.update(transitions=["ribbon"])
    app.start()
    sent = [c[2] for c in app.desk.calls if c[1] == "/api/generate"][-1]
    assert [b["transition"] for b in sent["blocks"]] == ["ribbon", "ribbon"] and sent["scenes"]
    assert "title" not in sent


def test_uploaded_song_board_is_used(app, tmp_path):
    song = tmp_path / "s.wav"
    song.write_bytes(b"RIFF")
    app.desk.upload = lambda path, file, timeout=None: {"audio_id": "aud9", "blocks": [{"form": "bulb"}], "scenes": [1]}
    app.create("x", audio_path=str(song))
    app.start()
    sent = [c[2] for c in app.desk.calls if c[1] == "/api/generate"][-1]
    assert sent["audio_id"] == "aud9" and sent["blocks"] == [{"form": "bulb"}]
    app.boards.clear()
    with pytest.raises(mt.XenoformError, match="load_audio"):
        app.start()

def _recipe_desk(app):
    real = app.desk.json

    def fake(method, path, body=None, timeout=None):
        if path == "/api/simple/recipe/encode":
            return {"recipe": "xf1.CODE"}
        if path == "/api/simple/recipe/decode":
            if body["recipe"] != "xf1.CODE":
                raise mt.XenoformError("Desk answered 400: bad recipe")
            return {"vibe": "ocean", "idea": "glass koi", "aspect": "16:9", "energy_preset": "dense", "seed": 7, "token": "x"}
        return real(method, path, body, timeout)

    app.desk.json = fake


def test_recipe_encode_decode_remix(app):
    _recipe_desk(app)
    app.create("x")
    assert app.encode_recipe()["recipe"] == "xf1.CODE"
    assert app.start()["recipe"] == "xf1.CODE"
    assert "token" not in app.decode_recipe("xf1.CODE")
    out = app.remix("xf1.CODE", tier="preview", vibe="cosmic")
    p = out["project"]
    assert (p["vibe"], p["prompt"], p["aspect"], p["energy"]) == ("cosmic", "glass koi", "16:9", "dense")
    with pytest.raises(mt.XenoformError):
        app.decode_recipe("")
    with pytest.raises(mt.XenoformError, match="bad recipe"):
        app.decode_recipe("xf1.WRONG")


def test_director_timeline_and_edits(app):
    app.desk.json("GET", "/api/demo")
    app.create("x")
    app.boards = {"demo": {"blocks": [{"form": "sphere", "hold": 2.0, "transition": "snap"},
                                      {"form": "sphere", "hold": 2.0, "transition": "snap"}],
                           "beats": [0.0, 0.5, 2.1], "tempo": 120, "duration": 4.0}}
    t = app.timeline()
    assert [s["start"] for s in t["shots"]] == [0.0, 2.0] and t["shots"][1]["off_beat_s"] == 0.1
    assert app.analysis()["beat_count"] == 3
    t = app.apply_edits([{"index": 0, "hold": 1.0, "transition": "ribbon"}, {"op": "append"}, {"op": "delete", "index": 1}])
    assert [s["hold"] for s in t["shots"]] == [1.0, 2.0] and t["shots"][0]["transition"] == "ribbon"
    for bad in ([], [{"index": 9}], [{"index": 0, "hold": 99}], [{"index": 0, "transition": "warp"}],
                [{"index": 0, "form": "dragon"}], [{"op": "explode", "index": 0}], ["x"]):
        with pytest.raises(mt.XenoformError):
            app.apply_edits(bad)
    app.start()
    sent = [c[2] for c in app.desk.calls if c[1] == "/api/generate"][-1]
    assert [b["hold"] for b in sent["blocks"]] == [1.0, 2.0]


def test_images_as_morph_targets_and_first_frame(app, tmp_path):
    a, b = tmp_path / "koi.png", tmp_path / "rose.jpg"
    a.write_bytes(b"x")
    b.write_bytes(b"x")
    app.create("x")
    app.attach_image(str(a))
    app.attach_image(str(b))
    app.attach_image(str(a))  # re-adding moves it last, no duplicate
    assert app.body()["morph_targets"] == [str(b.resolve()), str(a.resolve())]
    assert app.attach_image(str(a), role="first_frame")["image_id"] == "hero1"
    assert app.body()["hero_id"] == "hero1"
    with pytest.raises(mt.XenoformError, match="role"):
        app.attach_image(str(a), role="background")


def test_pick_stills_leads_with_user_targets(tmp_path):
    from xenoform import morph_pass

    a = tmp_path / "my_koi.png"
    a.write_bytes(b"x")
    vibe, stills = morph_pass.pick_stills({"vibe": "black", "morph_targets": [str(a), str(tmp_path / "gone.png"), "C:/x.txt"]}, 3)
    assert stills[0]["path"] == str(a.resolve()) and stills[0]["noun"] == "my koi"
    assert not stills[1].get("user") and Path(stills[1]["path"]).is_file()
    _, plain = morph_pass.pick_stills({"vibe": "black"}, 2)
    assert not any(s.get("user") for s in plain)


def test_recipe_v2_roundtrip_and_back_compat(app):
    _recipe_desk(app)
    app.create("x")
    assert app.encode_recipe()["recipe"] == "xf1.CODE"  # nothing extra: plain v1 code
    app.update(transitions=["ribbon"])
    app.boards = {"demo": {"blocks": [{"form": "sphere", "hold": 2.0, "transition": "snap"}]}}
    app.apply_edits([{"index": 0, "hold": 1.5}])
    code = app.encode_recipe()["recipe"]
    assert code.startswith("xf2.")
    dec = app.decode_recipe(code)
    assert dec["vibe"] == "ocean" and dec["transitions"] == ["ribbon"] and dec["blocks"][0]["hold"] == 1.5
    app.create("fresh")
    assert app.settings()["shot_edits"] == []
    p = app.remix(code)["project"]
    assert p["transitions"] == ["ribbon"] and p["shot_edits"][0]["hold"] == 1.5
    app.start()
    sent = [c[2] for c in app.desk.calls if c[1] == "/api/generate"][-1]
    assert sent["blocks"][0]["hold"] == 1.5 and "shot_edits_blocks" not in sent
    assert app.remix("xf1.CODE")["project"]["shot_edits"] == []  # v1 still remixes


def test_recipe_v2_rejects_damage_and_newer():
    import base64
    import zlib

    with pytest.raises(mt.XenoformError, match="damaged"):
        mt.decode_v2("xf2.!!!!")
    newer = "xf2." + base64.urlsafe_b64encode(zlib.compress(json.dumps({"v": 9, "base": "xf1.A"}).encode())).decode()
    with pytest.raises(mt.XenoformError, match="newer"):
        mt.decode_v2(newer)
    assert mt.decode_v2(mt.encode_v2("xf1.A", ["snap"], [{"form": "x", "hold": 1, "junk": 2}]))["blocks"] == [{"form": "x", "hold": 1}]


def test_desk_url_order(monkeypatch):
    from xenoform import mcp_server

    monkeypatch.setenv("XENO_DESK", "http://127.0.0.1:5/")
    assert mcp_server.desk_url() == "http://127.0.0.1:5"
    assert mcp_server.desk_url("http://h:1") == "http://h:1"
    monkeypatch.delenv("XENO_DESK")
    monkeypatch.delenv("XENO_PORT", raising=False)
    seen = []
    monkeypatch.setattr(mcp_server, "_answers", lambda url: seen.append(url) or url.endswith(":47317"))
    assert mcp_server.desk_url() == "http://127.0.0.1:47317" and seen[0].endswith(":47330")
    monkeypatch.setattr(mcp_server, "_answers", lambda url: False)
    assert mcp_server.desk_url() == "http://127.0.0.1:47330"
    monkeypatch.setenv("XENO_PORT", "47322")
    assert mcp_server.desk_url() == "http://127.0.0.1:47322"


def test_animatic_follows_aspect_only_when_not_live():
    from xenoform import turbo

    assert turbo.animatic_size({"aspect": "9:16"}) == (216, 384)
    assert turbo.animatic_size({"aspect": "1:1"}) == (288, 288)
    assert turbo.animatic_size({"aspect": "16:9"}) == (384, 216)
    assert turbo.animatic_size({"aspect": "9:16", "live": True}) == (384, 216)
    assert turbo.animatic_size(None) == (384, 216)


def test_draft_and_final_use_the_simple_turbo_path_not_legacy_restyle(app):
    """Regression for job 2e4717fe: quality 'draft' picked the Advanced restyle graph (LTX-2.3 ckpt + T5) and ComfyUI failed 4096 vs 2048."""
    app.create("x")
    for tier, live, qt in (("preview", False, "draft"), ("draft", True, "draft"), ("final", True, "final")):
        app.update(tier=tier)
        b = app.body()
        assert (b["quality"], b["live"], b["quality_tier"], b["aspect"], b["vertical_mode"]) == ("turbo", live, qt, "9:16", "native")


def test_get_output_reports_the_failure(app):
    app.create("x")
    job = app.start()["job_id"]
    app.desk.jobs[job].update(status="error", error="Sizes of tensors must match. Expected size 4096 but got size 2048")
    with pytest.raises(mt.XenoformError, match="failed: Sizes of tensors"):
        app.output(job)
    job2 = app.start()["job_id"]
    app.desk.jobs[job2]["progress"] = -5  # stays running on this poll
    with pytest.raises(mt.XenoformError, match="wait_for_render"):
        app.output(job2)
    app.cancel(job2)
    with pytest.raises(mt.XenoformError, match="cancelled"):
        app.output(job2)
