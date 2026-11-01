"""The film pack's version 2 fields in a clips cut (1 Nov): the sidecars carry colour, motion, living and mood beside each
file; own_media.scan hands them on; the cutter prefers calm clips for the calm passages and drop clips for the drop runs
when the pack says so (a folder without the fields is cut as before); the kaleido rule reads living from the pack rather
than from the clip's name; black-and-white is the pack's colour field before it is measured; motion is the pack's."""
from __future__ import annotations

import copy
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from xenoform import clip_cut, dense, film_pack, guardrails, own_media, taste

ROOT = Path(__file__).resolve().parents[1]
SONGS = ROOT / "tests" / "fixtures" / "analyses"  # frozen, so a rebuilt song moves no plan here
SHIPPED = ROOT / "configs" / "taste.json"
MOODS = ["calm", "build", "drop"]


@pytest.fixture()
def shipped(monkeypatch):
    monkeypatch.setenv("XENO_TASTE", str(SHIPPED))
    return taste.load()


def _whole(song: str) -> dict:
    f = json.loads((SONGS / f"{song}.features.json").read_text(encoding="utf-8"))
    return {"duration": float(f["duration"]), "beats": [float(b) for b in f["beats"]], "sections": list(f["sections"])}


SHARE = {"calm": 8, "build": 13, "drop": 19}  # the curated pack's share of the moods (40 clips)


def _pack(n: int, *, moods: bool = True, seconds: float = 14.0) -> list[dict]:
    """n clips from n // 2 films, two of each film, the moods taking turns in the curated pack's share, every clip said
    to move."""
    turns = [m for k in range(max(SHARE.values())) for m in MOODS if k < SHARE[m]]
    out = []
    for k in range(n):
        c = {"path": f"C:/pack/{k + 1:02d}_film{k // 2}_{k}.mp4", "seconds": seconds, "label": f"film {k}",
             "family": f"film{k // 2}", "motion": 0.5}
        if moods:
            c["mood"] = turns[k % len(turns)]
        out.append(c)
    return out


def _lay(directed: dict, clips: list[dict], drop: float, **shape) -> dict:
    state = {"energy_preset": "dense", "morph_source": "clips", "own_clips": clips, **shape}
    state, _ = guardrails.apply(state, duration=directed["duration"], beats=directed["beats"])
    shots, plan = dense.shots_for(state, directed, None, drop=drop)
    return clip_cut.fit(shots, plan, clips, state, beats=directed["beats"], duration=directed["duration"])


def _misses(lay: dict, clips: list[dict]) -> tuple[int, int]:
    """(clip shots whose clip is not of the mood their passage wants, clip shots that want a mood)."""
    miss = wanting = 0
    for s, sl in zip(lay["shots"], lay["slots"]):
        if sl["kind"] != "clip" or sl.get("cont"):
            continue
        want = clip_cut.wanted_mood(s)
        if want:
            wanting += 1
            miss += int(clips[sl["clip"]]["mood"] != want)
    return miss, wanting


# ---------------------------------------------------------------- the moods
def test_the_mood_a_passage_wants_and_how_far_a_clip_is_from_it():
    assert clip_cut.wanted_mood({"section": "calm"}) == "calm" and clip_cut.wanted_mood({"section": "intro"}) == "calm"
    assert clip_cut.wanted_mood({"section": "build"}) == "build" and clip_cut.wanted_mood({"section": "drop"}) == "drop"
    assert clip_cut.wanted_mood({"section": "release", "drop_run": 0}) == "drop" and clip_cut.wanted_mood({}) == ""
    assert clip_cut.mood_miss({"mood": "calm"}, "calm") == 0 and clip_cut.mood_miss({"mood": "build"}, "drop") == 1
    assert clip_cut.mood_miss({"mood": "calm"}, "drop") == 2 and clip_cut.mood_miss({}, "drop") == 0
    assert clip_cut.mood_miss({"mood": "drop"}, "") == 0 and clip_cut.mood_miss({"mood": "loud"}, "calm") == 0


@pytest.mark.parametrize("breathe", [True, False])
def test_calm_clips_go_to_the_calm_passages_and_drop_clips_to_the_drops(shipped, breathe):
    """Glitch Out wants about 7 calm, 9 build and 21 drop clip shots of 40 clips: past the 19 drop clips a drop run takes a
    build clip (a step away), never a calm one. Under Breathe a calm scene holds one film first, its mood second."""
    song = _whole("glitch-out")
    clips = _pack(40)
    lay = _lay(song, clips, 139.71, breathe=breathe, drop_mode="auto")
    miss, wanting = _misses(lay, clips)
    assert wanting > 30 and miss <= 0.15 * wanting, (miss, wanting)
    for s, sl in zip(lay["shots"], lay["slots"]):
        if sl["kind"] == "clip" and not sl.get("cont") and clip_cut.wanted_mood(s) == "drop":
            assert clips[sl["clip"]]["mood"] != "calm", s["start"]
    # the same folder in the order it has, without the field: the moods fall where the order puts them
    plain = _lay(song, _pack(40, moods=False), 139.71, breathe=breathe, drop_mode="auto")
    blind = sum(1 for s, sl in zip(plain["shots"], plain["slots"]) if sl["kind"] == "clip" and not sl.get("cont")
                and clip_cut.wanted_mood(s) and clips[sl["clip"]]["mood"] != clip_cut.wanted_mood(s))
    assert miss < blind
    used = [sl["clip"] for sl in lay["slots"] if sl["kind"] == "clip" and not sl.get("cont")]
    assert len(used) == len(set(used))  # still no clip twice
    # every drop run still opens on a cut to a fresh film (none of the last three shown)
    shown: list[str] = []
    for s, sl in zip(lay["shots"], lay["slots"]):
        if sl["kind"] != "clip" or sl.get("cont"):
            continue
        if s.get("event") == "drop":
            assert sl["family"] not in shown[-clip_cut.FRESH_BACK:], (s["start"], sl["family"], shown[-3:])
        shown.append(sl["family"])


def test_a_folder_without_moods_is_cut_as_before():
    """mood_miss is 0 for every clip of a folder without the field (tests/test_clip_pacing.py holds those cuts), and a
    folder with them draws its calm passage from its calm clips before its drop clips."""
    shots = [{"start": float(i * 4), "end": float(i * 4 + 4), "section": "calm", "passage": 0} for i in range(3)]
    kind = ["clip", "morph", "clip"]
    two = [{"path": "a/01_x.mp4", "seconds": 8.0, "family": "x"}, {"path": "a/02_y.mp4", "seconds": 8.0, "family": "y"}]
    assert [s.get("clip") for s in clip_cut.assign(shots, kind, two)] == [0, None, 1]
    moods = [{**two[0], "mood": "drop"}, {**two[1], "mood": "calm"}, {"path": "a/03_z.mp4", "seconds": 8.0, "family": "z", "mood": "calm"}]
    got = clip_cut.assign(shots, kind, moods)
    assert got[0]["clip"] == 1 and got[2]["clip"] == 2  # the calm passage takes the calm clips before the drop clip


def test_the_motion_field_stands_in_for_the_measure(monkeypatch):
    monkeypatch.setattr(clip_cut, "motion", lambda path: pytest.fail("measured a clip the pack had measured"))
    assert clip_cut.clip_motion({"path": "x.mp4", "motion": 0.4}) == pytest.approx(0.4 * clip_cut.MOTION_FULL)
    assert clip_cut.clip_motion({"path": "x.mp4", "motion": 0.1}) < clip_cut.STILL_MOTION  # a still film by the pack's word
    monkeypatch.setattr(clip_cut, "motion", lambda path: 7.5)
    assert clip_cut.clip_motion({"path": "x.mp4"}) == 7.5 and clip_cut.clip_motion({"path": "x.mp4", "motion": True}) == 7.5


# ---------------------------------------------------------------- living and colour
def test_the_kaleido_reads_living_from_the_pack_not_from_the_name(shipped):
    song = _whole("glitch-out")
    # names that say nothing of life, fields that say it; and a name that says life over a field that says none
    clips = []
    for k in range(24):
        c = {"path": f"C:/pack/{k + 1:02d}_reel_{k}.mp4", "seconds": 14.0, "family": f"f{k}", "motion": 0.5}
        c["label"] = "Phantom unmasked" if k % 3 == 2 else f"reel {k}"
        c["living"] = k % 3 == 0
        clips.append(c)
    state = {"energy_preset": "dense", "morph_source": "clips", "own_clips": clips, "breathe": False, "drop_mode": "auto",
             "effects": ["kaleido", "dither"]}
    lay = _lay(song, clips, 139.71, breathe=False, drop_mode="auto")
    shots = copy.deepcopy(lay["shots"])
    for s, sl in zip(shots, lay["slots"]):  # as run() marks them before the cut is shaped
        if sl["kind"] == "clip":
            s.update({"own": True, "label": clips[sl["clip"]]["label"], "living": clips[sl["clip"]]["living"]})
        else:
            s["clip_morph"] = {"from": clips[sl["a"]]["label"], "to": clips[sl["b"]]["label"],
                               "from_living": clips[sl["a"]]["living"], "to_living": clips[sl["b"]]["living"]}
    nouns = clip_cut.nouns(shots)
    assert all(isinstance(n.get("living"), bool) for n in nouns)
    with taste.collecting() as lines:
        dense.shape_shots(shots, state, {"chaos": 0.3, "intensity": 0.5}, None, look="", beats=song["beats"],
                          stills=nouns, drop=139.71)
    kaleido_on_alive = kaleido_on_named = 0
    for i, s in enumerate(shots):
        alive = nouns[i]["living"] or nouns[i + 1]["living"]
        named = taste.living(nouns[i]["noun"]) or taste.living(nouns[i + 1]["noun"])
        if "kaleido" in (s.get("fx_names") or []):
            kaleido_on_alive += int(alive)
            kaleido_on_named += int(named and not alive)
    assert kaleido_on_alive == 0  # the pack said a living thing: no kaleido
    assert kaleido_on_named > 0  # the name said one, the pack said not: the pack wins
    assert any("no-kaleido-on-living" in x["ids"] for x in lines)
    # a row without the field is still read by its words
    assert taste.shot_living([{"start": 0, "end": 1}], [{"noun": "a fish"}, {"noun": "a rock"}]) == [(None, None)]


def _film(path: Path, colour: bool) -> Path:
    from xenoform.video import write_mp4

    rng = np.random.default_rng(3)
    frames = []
    for _ in range(48):
        g = rng.integers(20, 230, size=(36, 64)).astype(np.uint8)
        f = np.stack([g, g, g], axis=2)
        if colour:
            f[:, :32, 0] = 230
        frames.append(f)
    write_mp4(path, frames, 24)
    return path


def test_black_and_white_is_the_packs_word_before_it_is_measured(tmp_path, shipped, monkeypatch):
    grey = _film(tmp_path / "01_grey.mp4", False)
    assert clip_cut.black_and_white({"path": str(grey)}) is True
    # the pack measured it as colour when it was curated: its field stands
    assert clip_cut.black_and_white({"path": str(grey), "colour": True}) is False
    monkeypatch.setattr(clip_cut, "mono", lambda path: pytest.fail("measured a clip the pack had measured"))
    with taste.collecting() as lines:
        assert clip_cut.film_note([{"path": "a.mp4", "colour": False}, {"path": "b.mp4", "colour": True}]) == 1
    assert "1 of the 2 clips" in lines[0]["line"]


def test_the_guardrail_counts_only_the_packs_black_and_white_clips(shipped, tmp_path):
    pack = tmp_path / "work" / "ui" / "film_pack"
    rows = [{"path": str(pack / "01_saturn.mp4"), "colour": True}, {"path": str(pack / "02_moon.mp4"), "colour": False},
            {"path": str(pack / "03_old.mp4")}]
    body = {"morph_source": "clips", "own_clips": rows, "vibe": "none"}
    _, rep = guardrails.apply(dict(body), duration=30.0)
    said = " ".join(rep["messages"])
    assert "2 of your clips are black-and-white film" in said and "(no-film-clips)" in said, said


# ---------------------------------------------------------------- the sidecars
@pytest.fixture(scope="module")
def tiny(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("tiny") / "tiny.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=64x36:rate=24:duration=3",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)], check=True)
    return path


@pytest.mark.skipif(shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None, reason="ffmpeg makes the tiny clips")
def test_pack_json_and_labels_json_carry_the_fields_and_scan_hands_them_on(tmp_path, monkeypatch, tiny):
    monkeypatch.setenv("XENO_FILM_PACK", str(tmp_path / "pack"))
    monkeypatch.setattr(film_pack, "RETRY_WAIT_S", 0.0)
    film_pack._reset_for_tests()
    manifest = {"version": 2, "name": "Free film pack", "folder": "film_pack",
                "sources": {"s": {"title": "A film", "url": film_pack.ARCHIVE + "item/a.mp4", "licence": "Public domain.",
                                  "file": "a.mp4 (h.264, 640x480)", "bytes": 1234567}},
                "clips": [{"id": "lift_off", "label": "Lift-off", "source": "s", "start": 1.0, "seconds": 2.0, "title": "Lift-off",
                           "colour": True, "motion": 0.6, "living": False, "mood": "drop", "crop": "620:480:10:0"},
                          {"id": "old_reel", "source": "s", "start": 5.0, "seconds": 2.0, "title": "The old reel"}]}
    calls = []

    def runner(cmd, *, timeout):
        calls.append(cmd)
        shutil.copyfile(tiny, Path(cmd[-1]))

    monkeypatch.setattr(film_pack, "load_manifest", lambda: json.loads(json.dumps(manifest)))
    monkeypatch.setattr(film_pack, "RUNNER", runner)
    film_pack.start()
    assert film_pack.wait(60)["status"] == "done"
    pack = tmp_path / "pack"
    assert "crop=620:480:10:0," in calls[0][calls[0].index("-vf") + 1]  # the clip's own crop reached ffmpeg
    rows = {r["id"]: r for r in json.loads((pack / "pack.json").read_text(encoding="utf-8"))["clips"]}
    assert rows["lift_off"]["mood"] == "drop" and rows["lift_off"]["colour"] is True and rows["lift_off"]["motion"] == 0.6
    assert rows["lift_off"]["crop"] == "620:480:10:0" and "mood" not in rows["old_reel"]
    labels = json.loads((pack / "labels.json").read_text(encoding="utf-8"))
    assert labels["01_lift_off.mp4"] == {"label": "Lift-off", "colour": True, "motion": 0.6, "living": False, "mood": "drop"}
    assert labels["02_old_reel.mp4"] == "The old reel"  # a clip without fields keeps the old shape
    credits = (pack / "CREDITS.md").read_text(encoding="utf-8")
    assert "File taken: a.mp4 (h.264, 640x480), 1.2 MB (1,234,567 bytes)." in credits and "| colour | drop |" in credits
    # the scan hands the fields to the cut; labels.json, which you may edit, wins over pack.json
    labels["02_old_reel.mp4"] = {"label": "The old reel", "mood": "calm", "living": True, "colour": "maybe"}
    (pack / "labels.json").write_text(json.dumps(labels), encoding="utf-8")
    found = {Path(c["path"]).name: c for c in own_media.scan(pack)["clips"]}
    one, two = found["01_lift_off.mp4"], found["02_old_reel.mp4"]
    assert (one["label"], one["family"], one["mood"], one["colour"], one["motion"], one["living"]) == ("Lift-off", "s", "drop", True, 0.6, False)
    assert two["label"] == "The old reel" and two["mood"] == "calm" and two["living"] is True and "colour" not in two
    assert clip_cut.clip_names([one, two]) == ["Lift-off", "The old reel"]
    film_pack._reset_for_tests()
