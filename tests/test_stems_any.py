import json, numpy as np, pytest, soundfile as sf
from xenoform import stem_react as S
from xenoform.dense import macros


def _wav(p, f, sr=22050, sec=1.0):
    t = np.arange(int(sr * sec)) / sr
    sf.write(str(p), (0.3 * np.sin(2 * np.pi * f * t) * (np.sin(2 * np.pi * 2 * t) > 0)).astype(np.float32), sr)
    return str(p)


def test_roles():
    assert S.role("Kick") == "drums" and S.role("Sub Bass") == "bass" and S.role("Lead Vox") == "vocals"
    assert S.role("Pad") == "other" and S.role("Brass") == "other"


@pytest.mark.parametrize("n", [1, 4, 11, 16, 32])
def test_any_number_of_stems(tmp_path, n):
    names = [f"stem{i:02d}" for i in range(n - 1)] + ["Kick"]
    st = S.from_files({k: _wav(tmp_path / f"{k}.wav", 110 + 40 * i) for i, k in enumerate(names)})
    env = S.envelopes(st, fps=24)
    assert env["stems"] == names and all(len(env[k]) == env["frames"] for k in names)
    assert "drums" in env and env["roles"]["Kick"] == "drums"
    json.dumps(env)  # serialisable for the VJ page


def test_cap_is_32(tmp_path):
    with pytest.raises(ValueError):
        S.from_files({f"s{i}": str(tmp_path / f"s{i}.wav") for i in range(33)})


def test_per_stem_gains_route_through_roles():
    env = {"fps": 24, "frames": 2, "stems": ["Kick", "Snare", "Pad"], "roles": {"Kick": "drums", "Snare": "drums", "Pad": "other"},
           "Kick": [1.0, 1.0], "Snare": [0.5, 0.5], "Pad": [0.8, 0.8], "drums": [1.0, 1.0], "other": [0.8, 0.8]}
    assert S.role_levels(env, 0, None)["drums"] == 1.0
    lv = S.role_levels(env, 0, {"Kick": 0.0, "Snare": 1.0, "Pad": 0.5})
    assert lv["drums"] == 0.5 and abs(lv["other"] - 0.4) < 1e-6
    assert S.drive(env, 0, {"Kick": 0.0})["chroma"] == 0.5


def test_macros_carry_stem_gains_up_to_32():
    st = {f"s{i}": 2.0 if i == 0 else 0.5 for i in range(40)}
    m = macros({"macros": {"stems": st}})
    assert len(m["stems"]) == 32 and m["stems"]["s0"] == 1.0 and m["stems"]["s1"] == 0.5
    assert "stems" not in macros({})


def test_ui_lanes_are_dynamic():
    from pathlib import Path
    js = (Path(S.__file__).parent / "ui_static" / "ui_v6.js").read_text(encoding="utf-8")
    assert "XENO_SET_STEMS" in js and "MAX_STEMS=32" in js and "xf-many" in js
    vj = (Path(S.__file__).parent / "ui_static" / "vj.html").read_text(encoding="utf-8")
    assert "STEMS.stems" in vj


def test_role_curve_without_gains_equals_all_gains_at_one_with_six_demucs_stems():
    """Demucs 6-stem names: guitar and piano are 'other' members, so the precomputed 'other' curve (no gains)
    must equal role_levels with every gain at 1.0, and sit above the guitar curve."""
    names = ["drums", "bass", "other", "vocals", "guitar", "piano"]
    curves = {"drums": [0.2, 0.3], "bass": [0.1, 0.1], "other": [0.1, 0.2], "vocals": [0.0, 0.0],
              "guitar": [0.9, 0.4], "piano": [0.3, 0.8]}
    env = {"fps": 24, "frames": 2, "stems": names, "roles": {s: S.role(s) for s in names}, **curves}
    for r in S.STEMS:  # the envelopes() role loop
        mem = [np.asarray(curves[s]) for s in names if S.role(s) == r]
        env[r] = np.max(mem, axis=0).tolist()
    for t in (0.0, 1 / 24):
        assert S.role_levels(env, t, None) == S.role_levels(env, t, {s: 1.0 for s in names})
        assert S.role_levels(env, t, None)["other"] >= S.at(env, t, "guitar")
    assert env["other"] == [0.9, 0.8]


def test_stems_on_demand_api_and_state_key(tmp_path, monkeypatch):
    """The desk splits only when asked (POST /api/stems); stems_path_for() is what state["stems_path"] carries."""
    from xenoform import stems_api
    monkeypatch.setattr(stems_api, "stems_root", lambda: tmp_path / "stems")
    wav = _wav(tmp_path / "s.wav", 110, sec=1.5)
    assert stems_api.stems_path_for(wav) is None
    p = stems_api.stems_path_for(wav, build=True, engine="bands")
    env = json.loads(p.read_text(encoding="utf-8"))
    assert p.name == "stems.json" and env["stems"] == list(S.STEMS) and env["engine"] == "librosa" and S.stem_names(env)
    assert stems_api.stems_path_for(wav) == p  # cached by song hash
    from pathlib import Path
    js = (Path(S.__file__).parent / "ui_static" / "ui_v6.js").read_text(encoding="utf-8")
    assert "XENO_MACRO_SET" in js and "/api/stems" in js and "stems_id" in js
