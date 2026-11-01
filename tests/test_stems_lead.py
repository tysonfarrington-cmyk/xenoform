"""Lead in Stems mode is the lead instrument, like a lead synth (Tys, 1 Nov; docs/STEMS_MODE.md): the Lead layer sits on
top of the stack with the highest prominence (0.9 unless set), takes the drop events and the style events where its
stem plays, and its rests of two bars or more are releases for every layer as built; the desk makes the melodic stem
the Lead (vocals when the song has them, else other). The split here is stems.fake_split: Demucs never runs."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from xenoform import dense, guardrails, stems_mode
from xenoform import stems_composite as SC

from test_stems_mode import SECTIONS, _plan_shots, _stems_make, fake_render, stems_dir  # noqa: F401  (fixtures)

STATIC = Path(__file__).resolve().parents[1] / "src" / "xenoform" / "ui_static"


def test_the_lead_is_the_most_prominent_unless_set_and_one_a_cut():
    layers, notes = stems_mode.layers_of([{"stem": "drums"}, {"stem": "other", "lead": True}, {"stem": "bass", "lead": True}])
    by = {l["stem"]: l for l in layers}
    assert by["other"]["lead"] and by["other"]["prominence"] == stems_mode.LEAD_PROMINENCE == 0.9
    assert by["drums"]["prominence"] == stems_mode.PROMINENCE_DEFAULT and not by["bass"]["lead"]
    assert by["bass"]["prominence"] == stems_mode.PROMINENCE_DEFAULT and any("one lead a cut" in n for n in notes)
    set_by_hand, _ = stems_mode.layers_of([{"stem": "other", "lead": True, "prominence": 0.4}])
    assert set_by_hand[0]["prominence"] == 0.4  # unless set


def test_the_lead_sits_on_top_of_the_stack_whatever_its_prominence():
    layers = [{"stem": "drums", "prominence": 0.8}, {"stem": "vocals", "prominence": 0.3, "lead": True}, {"stem": "bass", "prominence": 0.5}]
    assert SC.order_of(layers) == ["bass", "drums", "vocals"]
    assert SC.order_of([dict(l, lead=False) for l in layers]) == ["vocals", "bass", "drums"]  # by prominence alone
    assert SC.section(layers, fps=24, size=(32, 32), frames=10, audio=None)["order"][-1] == "vocals"


def _drop_plan():
    """A calm passage, a drop run at 8 s with its event, a style event at 12 s, and a calm passage after."""
    edges = [0, 4, 8, 10, 12, 14, 16, 20]
    sections = ["calm", "calm", "drop", "drop", "drop", "drop", "calm"]
    passages = [0, 0, 1, 1, 1, 1, 2]
    extra = {2: {"event": "drop", "boundary": "drop", "heat": 1.0, "drop_run": 0,
                 "effects": [{"type": "punch", "t": 8.0, "strength": 1.0}, {"type": "stutter", "t": 8.0, "frames": 2, "repeat": 4}]},
             3: {"heat": 1.0, "drop_run": 0}, 4: {"heat": 1.0, "drop_run": 0, "event": "style"}, 5: {"heat": 1.0, "drop_run": 0}}
    return _plan_shots(edges, sections, passages, extra)


def _drive(stem: str, act: list[float], lead: tuple[str, list[float]] | None):
    d = {"stem": stem, "fps": 24, "period": 0.5, "activity": act, "onsets": []}
    if lead:
        d["lead"] = {"stem": lead[0], "activity": lead[1]}
    return stems_mode.drive((_drop_plan(), {"name": "story"}), {"stem_drive": d})


def test_the_lead_takes_the_drop_and_style_events_where_its_stem_plays():
    drums = [0.9] * (20 * 24)
    synth = [0.9] * (20 * 24)
    plain, _ = _drive("drums", drums, None)  # no lead: the drums carry the drop and its style event, as before
    assert next(s for s in plain if s["start"] == 8.0)["event"] == "drop"
    assert next(s for s in plain if s["start"] == 12.0)["event"] == "style"
    led, plan = _drive("drums", drums, ("other", synth))  # the lead synth plays both: it takes them
    drop = next(s for s in led if s["start"] == 8.0)
    assert "event" not in drop and drop["boundary"] == "switch"
    assert not [fx for fx in drop["effects"] if fx["type"] in ("punch", "stutter") and fx["t"] == 8.0]
    assert "event" not in next(s for s in led if s["start"] == 12.0)
    assert plan["stem_drive"]["lead"] == "other" and plan["stem_drive"]["to_lead"] == 2 and not plan["stem_drive"]["is_lead"]
    lead, lplan = _drive("other", synth, ("other", synth))  # the lead keeps them
    assert next(s for s in lead if s["start"] == 8.0)["event"] == "drop" and lplan["stem_drive"]["is_lead"]
    assert next(s for s in lead if s["start"] == 12.0)["event"] == "style"


def test_where_the_lead_rests_the_events_stay_with_the_stems_that_carry_them():
    drums = [0.9] * (20 * 24)
    out_at_drop = [0.9] * (7 * 24) + [0.0] * (6 * 24) + [0.9] * (7 * 24)  # the synth out from 7 s to 13 s
    led, plan = _drive("drums", drums, ("other", out_at_drop))
    assert next(s for s in led if s["start"] == 8.0)["event"] == "drop"  # the drums carry it: the lead is out
    assert next(s for s in led if s["start"] == 12.0)["event"] == "style"
    assert plan["stem_drive"]["to_lead"] == 0
    quiet_synth = [0.36] * (20 * 24)  # plays the style event's first beat, quietly all shot long: the lead keeps it
    lead, _ = _drive("other", quiet_synth, ("other", quiet_synth))
    assert next(s for s in lead if s["start"] == 12.0)["event"] == "style"
    quiet, _ = _drive("other", quiet_synth, None)  # without the lead rule a quiet shot gives its style event up
    assert "event" not in next(s for s in quiet if s["start"] == 12.0)


def test_a_stems_make_with_the_other_stem_as_lead(tmp_path, fake_render):
    """The fake split's "other" plays 30 to 70 % of the song (7.2 to 16.8 s of 24): the lead synth. It sits on top at 0.9
    and it takes the drop at 8 s from the drums. It is out only before the song's first passage ends and after its last
    begins, which stay the intro and the outro (a lead's rest inside the song is a release for every layer:
    test_stems_mode's lead test, the drums out from 16 to 24 s of 40)."""
    job = tmp_path / "job"
    layers = [{"stem": "drums", "kind": "objects", "prominence": 0.8}, {"stem": "other", "kind": "objects", "lead": True}]
    rec, rep, seen, song = _stems_make(tmp_path, job, layers)
    by = {l["stem"]: l for l in rec["layers"]}
    assert by["other"]["prominence"] == 0.9 and by["other"]["lead"] and rec["lead"] == "other"
    assert rec["composite"]["order"] == ["drums", "other"]  # the lead on top
    assert any("the other leads (the lead instrument" in m for m in rep["messages"])
    drums = json.loads((job / "layers" / "drums" / "simple" / "simple.json").read_text(encoding="utf-8"))
    other = json.loads((job / "layers" / "other" / "simple" / "simple.json").read_text(encoding="utf-8"))
    entry = lambda shots: next((s for s in shots if abs(float(s["start"]) - 8.0) < 0.3 and s.get("section") == "drop"), None)  # noqa: E731
    assert entry(other["shots"]) is not None and entry(other["shots"]).get("event") == "drop"
    assert entry(drums["shots"]) is None or entry(drums["shots"]).get("event") != "drop"  # the lead took it
    assert rec["sections"] and rec["sections"][0]["role"] != "release" and rec["sections"][-1]["role"] != "release"
    assert drums["shots"] and other["shots"]


def test_the_desk_makes_the_melodic_stem_the_lead_and_says_what_lead_is():
    app = (STATIC / "app.js").read_text(encoding="utf-8")
    assert 'const STEM_LEAD_HELP = "The lead instrument, like a lead synth' in app and "const STEM_LEAD_PRO = 0.9;" in app
    pick = app.split("function stemDefaultLead(stems) {", 1)[1].split("\n}\n", 1)[0]
    assert '=== "vocals" && Number(r.active || 0) >= 0.1' in pick and '=== "other"' in pick
    row = app.split("function stemRowHtml(easy, r) {", 1)[1].split("function stemsStep(easy) {", 1)[0]
    assert 'title="${esc(STEM_LEAD_HELP)}">Lead</button>' in row and "the lead instrument, like a lead synth" in row
    assert "stemDefaults(easy, st.stems);" in app.split("function stemsStep(easy) {", 1)[1].split("async function loadStemsMode(", 1)[0]
    lead = app.split('} else if (act === "easy-stem-lead") {', 1)[1].split("} else if", 1)[0]
    assert "stemSetLead(state.easy, row, !row.lead);" in lead and "state.easy.stemLeadAuto = false;" in lead
    assert '"stemLeadAuto"' in app.split("const EASY_SAVED_KEYS = [", 1)[1].split("];", 1)[0]
    setlead = app.split("function stemSetLead(easy, row, on) {", 1)[1].split("\n}\n", 1)[0]
    assert "if (!row.proSet) row.prominence = on ? STEM_LEAD_PRO : stemProDefault(name);" in setlead


def test_a_passage_under_two_bars_between_the_leads_rests_folds_into_its_neighbour():
    """ZedsDead v1 with the other stem as Lead had a 1 s drop passage at 1:53 between two of its rests (1 Nov): a
    passage under two bars the lead's rests leave folds into its neighbour, as a role clipped at a window's edge does,
    so the two rests and the second between them are one release; a passage of exactly two bars stays."""
    directed = {"duration": 40.0, "beats": [i * 0.5 for i in range(80)],
                "sections": [{"label": "calm", "start": 0.0, "end": 16.0, "level": 0.5, "role": "calm"},
                             {"label": "drop", "start": 16.0, "end": 40.0, "level": 0.9, "role": "drop"}]}
    # the lead plays 0 to 8 s, rests 8 to 17, plays one second, rests 18 to 26, plays to the end (two bars: 4 s)
    curve = [1.0] * (8 * 24) + [0.0] * (9 * 24) + [1.0] * 24 + [0.0] * (8 * 24) + [1.0] * (14 * 24)
    rows = stems_mode.lead_sections(directed, curve, 24)
    assert [(r["role"], r["start"], r["end"]) for r in rows] == [("calm", 0.0, 8.0), ("release", 8.0, 26.0), ("drop", 26.0, 40.0)]
    assert rows[1]["lead_out"] is True and all(r["end"] - r["start"] >= 4.0 for r in rows)
    first = [1.0] * 24 + [0.0] * (10 * 24) + [1.0] * (29 * 24)  # a second of the lead at the very start joins the passage after it
    assert [(r["role"], r["start"], r["end"]) for r in stems_mode.lead_sections(directed, first, 24)][:2] == \
        [("release", 0.0, 11.0), ("calm", 11.0, 16.0)]
    two = [1.0] * (6 * 24) + [0.0] * (6 * 24) + [1.0] * (4 * 24) + [0.0] * (6 * 24) + [1.0] * (18 * 24)
    assert ("calm", 12.0, 16.0) in [(r["role"], r["start"], r["end"]) for r in stems_mode.lead_sections(directed, two, 24)]
