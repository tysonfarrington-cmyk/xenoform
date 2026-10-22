"""RC3 fixes: media_qa house rules at call time, fonts on every OS, orbit zoom, role curves, end-card URL,
packaging metadata, installers, MCP error signalling."""
import json
import os
import re
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------- 1. media_qa
def test_check_transitions_accepts_a_real_edit_and_bans_by_substring():
    from xenoform import media_qa as Q

    assert Q.check_transitions(["cut"] * 8 + ["scene-morph"] * 3) == []
    assert Q.check_transitions(["cut"] * 5 + ["flow-morph", "flow-morph", "black-hold"]) == []
    found = Q.check_transitions(["luma-wipe"])
    assert [f["check"] for f in found] == ["transition_banned"] and found[0]["severity"] == "fail"
    assert {f["check"] for f in Q.check_transitions(["stutter-cut", "iris"])} == {"transition_banned"}
    over = Q.check_transitions(["flow-morph"] * 3)
    assert [f["check"] for f in over] == ["transition_overuse"]
    assert Q.check_transitions(["match-cut"])[0]["check"] == "transition_unknown"


def test_house_is_read_at_call_time_not_import_time():
    from xenoform import media_qa as Q
    from xenoform.demo_house import DEMO_HOUSE

    assert Q.house()["transitions"] == DEMO_HOUSE["transitions"]
    strict = {"house": {**DEMO_HOUSE, "transitions": {**DEMO_HOUSE["transitions"], "allowed": ["flow-morph"]}}}
    assert Q.check_transitions(["echo-trail"], cfg=strict)[0]["check"] == "transition_unknown"
    assert Q.check_transitions(["echo-trail"]) == []
    assert Q.check_duration(130.0, cfg={"house": {**DEMO_HOUSE, "duration_cap_s": 200.0}}) == []
    assert Q.check_duration(130.0)[0]["check"] == "duration"
    sr = 8000; t = np.arange(sr * 2) / sr; x = 0.05 * np.sin(2 * np.pi * 440 * t)
    loud = {"house": {**DEMO_HOUSE, "audio": {**DEMO_HOUSE["audio"], "target_lufs": -60.0}}}
    assert any(f["check"] == "lufs" for f in Q.check_loudness(x, sr))
    assert any(f["check"] == "lufs" for f in Q.check_loudness(x, sr, cfg=loud))
    assert not any(f["check"] == "lufs" for f in Q.check_loudness(x, sr, target=Q.loudness(x, sr)["lufs"]))


def test_loudness_of_silence_has_no_nan_and_empty_mask_warns():
    from xenoform import media_qa as Q

    with np.errstate(all="raise"):
        m = Q.loudness(np.zeros(48000), 48000)
    assert m["lufs"] == -70.0 and np.isfinite(m["true_peak_dbtp"])
    img = np.full((20, 20, 3), 100, np.uint8)
    found = Q.check_text_legibility(img, np.zeros((20, 20), bool))
    assert len(found) == 1 and found[0]["severity"] == "warn" and "no text mask" in found[0]["msg"]


def test_probe_fps_falls_back_when_ffprobe_cannot_read(tmp_path):
    from xenoform import media_qa as Q

    assert Q.probe_fps(str(tmp_path / "missing.mp4")) == 24.0
    assert Q.probe_fps(str(tmp_path / "missing.mp4"), default=30.0) == 30.0


def test_run_file_cleans_its_tempdir_and_uses_the_file_fps(tmp_path, monkeypatch):
    from xenoform import media_qa as Q
    import tempfile

    made = []
    real = tempfile.TemporaryDirectory

    def spy(*a, **k):
        d = real(*a, **k); made.append(d.name); return d

    monkeypatch.setattr(tempfile, "TemporaryDirectory", spy)
    monkeypatch.setattr(Q, "probe_fps", lambda p, default=24.0: 30.0)
    cmds = []

    def fake_run(cmd, *a, **k):
        cmds.append(cmd)
        if "-vn" in cmd:  # the audio extract: write a short silent wav
            import soundfile as sf
            sf.write(cmd[-1], np.zeros(4800, np.float32), 48000)
            return subprocess.CompletedProcess(cmd, 0)
        return subprocess.CompletedProcess(cmd, 0, stdout=bytes(96 * 170 * 3))

    monkeypatch.setattr(Q.subprocess, "run", fake_run)
    out = Q.run_file(str(tmp_path / "x.mp4"))
    assert made and not Path(made[0]).exists()
    assert any("fps=30" in " ".join(c) for c in cmds)
    assert "findings" in out and "pass" in out


# ---------------------------------------------------------------- 2. fonts
def test_find_font_prefers_env_and_escapes_for_drawtext(tmp_path, monkeypatch):
    from xenoform import video

    ttf = tmp_path / "My Font.ttf"; ttf.write_bytes(b"\0" * 16)
    monkeypatch.setenv("XENO_FONT", str(ttf))
    got = video.find_font()
    assert got and Path(got) == ttf and "\\" not in got
    woff = tmp_path / "x.woff2"; woff.write_bytes(b"\0")
    monkeypatch.setenv("XENO_FONT", str(woff))
    assert video.find_font() != str(woff).replace("\\", "/")  # woff2 is never offered to ffmpeg
    monkeypatch.delenv("XENO_FONT")
    assert video.drawtext_fontfile("C:\\Windows\\Fonts\\georgia.ttf") == "C\\:/Windows/Fonts/georgia.ttf"
    assert video.drawtext_fontfile("/usr/share/fonts/a.ttf") == "/usr/share/fonts/a.ttf"
    assert "sand-box" not in str(video.FONT_CANDIDATES) and not any(c.endswith(".woff2") for c in video.FONT_CANDIDATES)


def test_overlay_text_uses_the_found_font(tmp_path, monkeypatch):
    from xenoform import video

    monkeypatch.setattr(video, "find_font", lambda prefer=None: "C:/Windows/Fonts/georgia.ttf")
    seen = {}

    def fake_call(cmd, *a, **k):
        seen["cmd"] = cmd
        Path(cmd[-1]).write_bytes(b"x")
        return 0

    monkeypatch.setattr(video.subprocess, "check_call", fake_call)
    monkeypatch.setattr(video.subprocess, "run", lambda cmd, *a, **k: fake_call(cmd) and subprocess.CompletedProcess(cmd, 0))
    monkeypatch.setattr(video, "ffmpeg_bin", lambda: "ffmpeg", raising=False)
    src = tmp_path / "cut.mp4"; src.write_bytes(b"mp4")
    video.overlay_text(src, [{"text": "Hello", "start": 0.0, "end": 1.0}])
    joined = " ".join(seen["cmd"])
    assert "fontfile='C\\:/Windows/Fonts/georgia.ttf'" in joined


def test_scene_edit_fonts_and_afade_clamp():
    from xenoform import scene_edit as SE

    assert not any("sand-box" in f for f in SE.FONTS)
    assert all(not f.endswith(".woff2") for f in SE.FONTS)
    assert SE._afade_out(10.0) == "afade=t=out:st=8.50:d=1.50"
    assert SE._afade_out(1.0) == "afade=t=out:st=0.00:d=1.00"
    assert SE._afade_out(0.0).startswith("afade=t=out:st=0.00:d=0.05")
    for total in (0.0, 0.3, 1.0, 1.49, 1.5, 7.0):
        st = float(re.search(r"st=([-\d.]+)", SE._afade_out(total)).group(1))
        assert st >= 0.0


# ---------------------------------------------------------------- 4. stem_react role curves
def test_role_curve_is_the_max_over_every_member_even_when_a_stem_is_named_other():
    from xenoform import stem_react as S

    curves = {"drums": [0.2, 0.3], "bass": [0.1, 0.1], "other": [0.1, 0.2], "vocals": [0.0, 0.0],
              "guitar": [0.9, 0.4], "piano": [0.3, 0.8]}
    names = list(curves)
    env = {"fps": 24, "frames": 2, "stems": names, "roles": {s: S.role(s) for s in names}, **curves}
    # the envelopes() role loop, applied to these curves
    for r in S.STEMS:
        mem = [np.asarray(curves[s]) for s in names if S.role(s) == r]
        env[r] = np.max(mem, axis=0).tolist()
    assert env["other"] == [0.9, 0.8]  # guitar / piano drive "other"
    for t in (0.0, 1 / 24):
        assert S.role_levels(env, t, None) == S.role_levels(env, t, {s: 1.0 for s in names})
        assert S.role_levels(env, t, None)["other"] >= S.at(env, t, "guitar")


def test_envelopes_role_curve_includes_guitar_and_piano(tmp_path):
    import soundfile as sf
    from xenoform import stem_react as S

    sr = 22050; t = np.arange(sr) / sr

    def wav(name, amp):
        p = tmp_path / f"{name}.wav"
        sf.write(str(p), (amp * np.sin(2 * np.pi * 220 * t)).astype(np.float32), sr)
        return str(p)

    st = S.from_files({"drums": wav("drums", 0.2), "bass": wav("bass", 0.2), "other": wav("other", 0.05),
                       "vocals": wav("vocals", 0.1), "guitar": wav("guitar", 0.6), "piano": wav("piano", 0.3)})
    env = S.envelopes(st, fps=24)
    assert env["roles"]["guitar"] == "other" and env["roles"]["piano"] == "other"
    o, g = np.array(env["other"]), np.array(env["guitar"])
    assert np.all(o >= g - 1e-4)
    for k in (0.0, 0.5):
        assert S.role_levels(env, k, None) == pytest.approx(S.role_levels(env, k, {s: 1.0 for s in env["stems"]}))


# ---------------------------------------------------------------- 5. beatfx end card URL
def test_repo_url_env_override_and_placeholder_suppression(monkeypatch):
    from xenoform import beatfx

    monkeypatch.setenv("XENO_REPO_URL", "https://github.com/someone/xenoform/")
    assert beatfx.repo_url() == "github.com/someone/xenoform"
    monkeypatch.delenv("XENO_REPO_URL")
    monkeypatch.setattr(beatfx, "_pyproject_repo_url", lambda: "https://github.com/PLACEHOLDER/xenoform")
    assert beatfx.repo_url() == ""
    monkeypatch.setattr(beatfx, "_pyproject_repo_url", lambda: "https://github.com/real/xenoform")
    assert beatfx.repo_url() == "github.com/real/xenoform"
    monkeypatch.setattr(beatfx, "_pyproject_repo_url", lambda: "")
    assert beatfx.repo_url() == ""


def test_end_card_omits_the_url_line_when_empty(tmp_path, monkeypatch):
    from xenoform import beatfx

    monkeypatch.delenv("XENO_REPO_URL", raising=False)
    monkeypatch.setattr(beatfx, "_font", lambda: "C:/Windows/Fonts/arial.ttf")
    monkeypatch.setattr(beatfx, "probe_duration", lambda p: 10.0)
    monkeypatch.setattr(beatfx, "_ffmpeg", lambda: "ffmpeg", raising=False)
    seen = {}

    def fake_run(cmd, *a, **k):
        seen["vf"] = cmd[cmd.index("-vf") + 1]
        Path(cmd[-1]).write_bytes(b"x")
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(beatfx.subprocess, "run", fake_run)
    cut = tmp_path / "cut.mp4"; cut.write_bytes(b"mp4")
    monkeypatch.setattr(beatfx, "repo_url", lambda: "")
    assert beatfx.end_card(cut, "xf1.abc") is True
    assert "text='Xenoform'" in seen["vf"] and "PLACEHOLDER" not in seen["vf"] and "·" not in seen["vf"]
    monkeypatch.setattr(beatfx, "repo_url", lambda: "github.com/real/xenoform")
    assert beatfx.end_card(cut, "xf1.abc") is True
    assert "Xenoform · github.com/real/xenoform" in seen["vf"]


# ---------------------------------------------------------------- 6/7. packaging and installers
def test_pyproject_metadata():
    import tomllib

    pp = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    proj = pp["project"]
    assert proj["version"] == "0.3.0" and proj["requires-python"] == ">=3.12"
    extras = proj["optional-dependencies"]
    assert any(d.startswith("mcp>=2.3") and "<3" in d for d in extras["agent"])
    assert any(d.startswith("mido") for d in extras["midi"]) and any(d.startswith("python-rtmidi") for d in extras["midi"])
    assert any(d.startswith("demucs") for d in extras["stems"])
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert 'python-version: "3.12"' in ci and '".[dev,agent]"' in ci


def test_install_sh_and_mcp_bat():
    sh = (ROOT / "install.sh").read_text(encoding="utf-8")
    assert re.search(r'pip["\s]+install --no-deps -e', sh)
    assert "comfy-api-proxy run --comfyui" in sh and "comfy-api-proxy --comfyui" not in sh
    bat = (ROOT / "Xenoform-MCP.bat").read_text(encoding="utf-8")
    assert "install.bat" in bat and "exit /b 1" in bat
    assert "set PY=python" not in bat


# ---------------------------------------------------------------- 8. MCP error signalling
class _Desk(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, raw: bytes, ctype="application/json"):
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)

    def do_GET(self):
        if self.path == "/ok":
            return self._send(200, b'{"ok": true}')
        if self.path == "/text":
            return self._send(200, b"<html>not json</html>", "text/html")
        if self.path == "/empty":
            return self._send(200, b"")
        return self._send(404, b'{"detail": "No such storyboard"}')


@pytest.fixture(scope="module")
def desk_url():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Desk)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def test_mcp_server_request_raises_tool_errors(desk_url):
    from xenoform import mcp_server as ms
    from xenoform.mcp_tools import XenoformError

    assert ms._request(desk_url, "GET", "/ok") == {"ok": True}
    assert ms._request(desk_url, "GET", "/empty") == {}
    with pytest.raises(XenoformError, match="404.*No such storyboard"):
        ms._request(desk_url, "GET", "/api/v1/storyboard")
    with pytest.raises(XenoformError, match="not JSON"):
        ms._request(desk_url, "GET", "/text")
    with pytest.raises(XenoformError, match="Cannot reach"):
        ms._request("http://127.0.0.1:9", "GET", "/ok", timeout=1.0)
    try:
        from mcp.server.mcpserver.exceptions import ToolError
    except ImportError:
        pytest.skip("mcp not installed")
    assert issubclass(XenoformError, ToolError)


# ---------------------------------------------------------------- 9. defaults_demo.json lives in configs/
def test_defaults_demo_json_matches_the_house_profile():
    from xenoform.config import load_config
    from xenoform.demo_house import DEMO_HOUSE

    assert not (ROOT / "config" / "defaults_demo.json").exists()
    data = json.loads((ROOT / "configs" / "defaults_demo.json").read_text(encoding="utf-8"))
    assert data["house"] == DEMO_HOUSE == load_config()["house"]
    assert load_config(ROOT / "configs" / "defaults_demo.json")["house"] == DEMO_HOUSE
