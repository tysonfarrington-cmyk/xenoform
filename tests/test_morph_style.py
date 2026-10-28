"""How A becomes B (xenoform.morph_style, docs/MORPH_ENGINE_PLAN.md E1, 28 Oct): Melt, Shatter, Bloom, Spin and Fold. Auto
by the drop and the Chaos knob, a setting for the cut, a style a shot on the timeline (a re-render), each reaching the
morph prompt on Draft and Final, recorded, read back by the lane, carried by the recipe and by Render at Final."""
import json
from pathlib import Path

import pytest

from test_timeline import _cut, _rec  # the mock-engine cut over the shipped cosmic pool
from xenoform import dense, final_tier, lane, morph_pass as mp, morph_style as ms, simple_recipe

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src/xenoform/ui_static/app.js").read_text(encoding="utf-8")
CSS = (ROOT / "src/xenoform/ui_static/desk.css").read_text(encoding="utf-8")
LEGACY = ("One single sculptural object slowly melts and flows into another, one continuous liquid transformation, the "
          "object stays centred, gentle slow camera drift, {look}, one single object, every feature appears once, macro "
          "product photography, crisp, clean, high detail")


def _shots(times, drop=None, sections=None):
    out = []
    for k, (a, b) in enumerate(zip(times, times[1:])):
        s = {"start": a, "end": b}
        if sections:
            s["section"] = sections[k]
        out.append(s)
    return out


def test_auto_shatters_the_drop_and_follows_the_chaos_knob():
    shots = _shots([0, 2, 4, 6, 7, 8, 9, 10], drop=6)  # a bar a shot, then a half bar from the drop at 6 s
    assert ms.auto(shots, 6, 0.1) == ["melt"] * 7  # calm: every morph melts
    assert ms.auto(shots, 6, 0.3) == ["bloom", "melt", "melt", "shatter", "melt", "melt", "melt"]
    # wild: the bar into the drop folds, the drop shatters, every other shot after it spins
    assert ms.auto(shots, 6, 0.8) == ["melt", "melt", "fold", "shatter", "melt", "spin", "melt"]
    assert ms.auto(shots, None, 0.3)[0] == "bloom" and "shatter" not in ms.auto(shots, None, 0.3)
    story = _shots([0, 4, 8, 10, 12, 14], sections=["intro", "build", "drop", "drop", "drop_late"])
    assert ms.auto(story, 8, 0.7) == ["melt", "fold", "shatter", "melt", "spin"]
    assert ms.auto([], 1.0, 0.5) == [] and ms.drop_index(shots, 99) is None


def test_for_cut_takes_the_carried_list_then_the_setting_then_auto():
    shots = _shots([0, 2, 4, 6, 8], drop=4)
    assert ms.for_cut({"morph_style": "spin"}, shots, 4) == ["spin"] * 4
    assert ms.for_cut({"morph_style": "wild"}, shots, 4) == ["melt"] * 4  # an unknown setting is a Melt
    assert ms.for_cut({"macros": {"chaos": 0.3}}, shots, 4) == ["bloom", "melt", "shatter", "melt"]
    carried = ["fold", "melt", "spin", "bloom"]
    assert ms.for_cut({"morph_style": "melt", "morph_styles": carried}, shots, 4) == carried  # Render at Final keeps them
    assert ms.for_cut({"morph_style": "melt", "morph_styles": carried[:2]}, shots, 4) == ["melt"] * 4  # other shots: ignored
    assert ms.info(["melt", "shatter", "melt"]) == {"melt": 2, "shatter": 1}


def test_melt_is_the_old_prompt_word_for_word_and_a_style_changes_only_the_opening():
    look = mp.VIBE_LOOK["neon-noir"]
    assert mp.prompt_for("neon-noir") == LEGACY.format(look=look) == mp.prompt_for("neon-noir", style="melt")
    tail = LEGACY.split("transformation, ", 1)[1].format(look=look)
    for style in ms.STYLES:
        text = mp.prompt_for("neon-noir", style=style)
        assert text.startswith(ms.OPENINGS[style]) and text.endswith(tail)
    assert len({mp.prompt_for("neon-noir", style=s) for s in ms.STYLES}) == 5
    # a pair that touches a scene keeps the scene prompt whatever the style; Final carries its frame-anchor lead
    assert mp.prompt_for("neon-noir", kinds=("scene", "object"), style="shatter") == mp.prompt_for("neon-noir", kinds=("scene", "object"))
    assert mp.prompt_for("neon-noir", "ltx25", style="fold").startswith("Use the provided start image")
    assert ms.normal("SPIN") == "spin" and ms.normal("auto") == "auto" and ms.normal("auto", allow_auto=False) == "melt"


class _WF:
    def __init__(self):
        self.inputs = {}

    def set_input(self, node, key, value):
        self.inputs[(node, key)] = value


class _Out:
    type = "video"

    def to_file(self, path):
        Path(path).write_bytes(b"pair")


class _Job:
    def result(self):
        class R:
            outputs = [_Out()]

            def get_outputs(self, node):
                return [_Out()]

        return R()


def _client(wfs):
    class Client:
        class assets:
            @staticmethod
            def from_file(path):
                return path

        class workflows:
            @staticmethod
            def from_file(path):
                wf = _WF()
                wfs.append(wf)
                return wf

            @staticmethod
            def from_json(graph):
                wf = _WF()
                wf.graph = graph
                wfs.append(wf)
                return wf

        def submit(self, wf):
            return _Job()

    return Client()


def test_the_draft_and_final_renderers_give_each_shot_its_style(tmp_path, monkeypatch):
    from xenoform.cloud_morph import _local_clips

    stills = [{"path": str(tmp_path / f"s{i}.png")} for i in range(4)]
    shots = [{"seconds": 2.0}, {"seconds": 2.0}, {"seconds": 2.0}]
    wfs = []
    _local_clips(shots, stills, tmp_path, {}, 2727, "neon-noir", client=_client(wfs), styles=["melt", "shatter", "bloom"])
    texts = [wf.inputs[("3", "text")] for wf in wfs]
    assert "slowly melts" in texts[0] and "shatters into hundreds" in texts[1] and "unfolds like a blooming flower" in texts[2]
    wfs.clear()
    _local_clips(shots[:1], stills[:2], tmp_path, {}, 2727, "neon-noir", client=_client(wfs))
    assert "slowly melts" in wfs[0].inputs[("3", "text")]  # no styles: Melt, as before
    seen = []
    monkeypatch.setattr(final_tier, "graph", lambda prompt, **kw: seen.append((kw["seed"], prompt)) or {"prompt": prompt})
    wfs.clear()
    final_tier.final_clips(shots[:2], stills[:3], tmp_path, {}, 2727, "neon-noir", client=_client(wfs), styles=["spin", "fold"])
    seen.sort()  # the Final renders shots that share a prompt back to back; each keeps its seed (2727 + its index)
    assert "spins fast on its axis" in seen[0][1] and "folds and creases like paper" in seen[1][1]


def test_a_cut_records_its_styles_and_the_lane_reads_them(tmp_path, monkeypatch):
    seen = {}
    job = _cut(tmp_path, monkeypatch, seen)
    rec = _rec(job)
    shots = rec["plan_shots"]
    assert rec["morph_style"] == "auto" and len(rec["morph_styles"]) == len(shots)
    d = ms.drop_index(shots, rec["drop"])
    assert rec["morph_styles"][d] == "shatter" and rec["morph_styles"][0] == "bloom"  # the default Chaos is 0.3
    assert {"morph_styles": ms.info(rec["morph_styles"])} in rec["fallbacks"] and rec["recut_state"]["morph_style"] is None
    built = lane.build(rec, "cut")
    assert [r["style"] for r in built["shots"]] == rec["morph_styles"] and built["morph_style"] == "auto"
    assert [c["id"] for c in built["choices"]["morph_styles"]] == list(ms.STYLES)


def test_a_rerender_in_a_style_reaches_the_prompt_and_the_record(tmp_path, monkeypatch):
    seen = {}
    job = _cut(tmp_path, monkeypatch, seen)
    rec_path = job / "simple" / "simple.json"
    rec = _rec(job)
    rec["engine"] = "LTX 0.9.5 (Draft)"
    rec_path.write_text(json.dumps(rec), encoding="utf-8")
    wfs = []
    out = dense.rerender_morph(job, 2, style="spin", cfg={}, client=_client(wfs))
    assert "spins fast on its axis" in wfs[0].inputs[("3", "text")]
    assert out["morph_styles"][2] == "spin" and out["rerenders"][-1]["style"] == "spin"
    assert [s for i, s in enumerate(out["morph_styles"]) if i != 2] == [s for i, s in enumerate(rec["morph_styles"]) if i != 2]
    dense.rerender_morph(job, 2, cfg={}, client=_client(wfs))  # no style given: the shot keeps its own
    assert "spins fast on its axis" in wfs[1].inputs[("3", "text")] and _rec(job)["rerenders"][-1]["style"] == "spin"
    with pytest.raises(ValueError, match="morph style"):
        dense.rerender_morph(job, 2, style="smoke", cfg={}, client=_client(wfs))


def test_a_generated_run_takes_the_cuts_setting(tmp_path, monkeypatch):
    seen = {}
    job = _cut(tmp_path, monkeypatch, seen)
    rec_path = job / "simple" / "simple.json"
    rec = _rec(job)
    rec["recut_state"]["morph_style"] = "fold"
    rec_path.write_text(json.dumps(rec), encoding="utf-8")
    out = dense.insert_generated(job, 1, seconds=3.0)
    entry = out["inserts"][-1]
    assert entry["styles"] and set(entry["styles"]) == {"fold"}
    assert out["morph_styles"][entry["first"]:entry["last"] + 1] == entry["styles"] and len(out["morph_styles"]) == len(rec["morph_styles"])


def test_the_recipe_code_carries_the_style():
    code = simple_recipe.encode({"vibe": "cosmic", "morph_style": "shatter"})
    assert simple_recipe.decode(code)["morph_style"] == "shatter"
    assert "morph_style" not in simple_recipe.decode(simple_recipe.encode({"vibe": "cosmic"}))  # Auto stays out of the code


def test_the_desk_has_the_morph_row_and_the_timeline_chips():
    assert 'const MORPH_STYLES = ["melt", "shatter", "bloom", "spin", "fold"];' in APP and list(ms.STYLES) == ["melt", "shatter", "bloom", "spin", "fold"]
    notes = APP.split("const MORPH_STYLE_NOTES = {", 1)[1].split("};", 1)[0]
    for key, text in ms.NOTES.items():
        assert f'"{key}": {json.dumps(text)}' in notes, key  # the desk says what the engine does
    desk = APP.split("simple-knobs-panel", 1)[1].split("</section>", 1)[0]
    assert '${morphStyleRow(easy.morphStyle || "auto", "easy-morph-style")}' in desk
    body = APP.split("function payload() {", 1)[1].split("function vjUrl()", 1)[0]
    assert 'morph_style: (state.easy && state.easy.morphStyle) || "auto"' in body and "morph_styles: (state.easy && state.easy.carryStyles) || null" in body
    assert '"morphStyle"' in APP.split("const EASY_SAVED_KEYS = [", 1)[1].split("];", 1)[0]
    assert 'act === "easy-morph-style"' in APP and 'act === "easy-tl-style"' in APP
    drawer = APP.split("function timelineDrawer(easy, lane, tl, picked) {", 1)[1].split("// Dream this span", 1)[0]
    assert 'morphStyleRow(s.style || "melt", "easy-tl-style", s.index, false)' in drawer
    assert "if (style && MORPH_STYLES.includes(style)) body.style = style;" in APP
    final = APP.split('act === "easy-render-full" || act === "easy-render-final") {', 1)[1].split("} else if", 1)[0]
    assert "state.easy.carryStyles = lane.shots.map" in final and "state.easy.carryStyles = null" in final
    assert 'class="tl-style"' in APP and ".shots-lane .shot .tl-style" in CSS
    assert "easy.morphStyle = recipe.morph_style" in APP
