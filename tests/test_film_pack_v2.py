"""The curated film pack, version 2 (Tys, 1 Nov: "Build a bigger curated clip pack, about 40 clips, colour and action
first, so every cut the plan wants shows a clip once"): the shipped list is about forty clips from archive.org and NASA,
each source with its URL, its file and size and a licence line, each clip 6 to 20 s with its crop and four fields
(colour, motion, living, mood); the loader checks the fields and still reads a version 1 list; a clip's own crop wins
over its source's; the made clips come out in square pixels; CREDITS.md names each file taken and its size."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from xenoform import film_pack, own_media

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
                                reason="ffmpeg and ffprobe make and read the tiny clips")

ROOT = Path(__file__).resolve().parents[1]
REAL = json.loads((ROOT / "configs" / "film_pack.json").read_text(encoding="utf-8"))
HOSTS = (film_pack.ARCHIVE, film_pack.NASA)
GONE = {"general_bridge", "general_cannon", "potemkin_steps"}  # Tys, 1 Nov: The General and Battleship Potemkin are out


def _write(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "film_pack.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _load(monkeypatch, tmp_path, data):
    monkeypatch.setattr(film_pack, "manifest_path", lambda: _write(tmp_path, data))
    return film_pack.load_manifest()


# ---------------------------------------------------------------- the shipped list
def test_the_list_is_version_2_colour_and_action_first():
    clips, sources = REAL["clips"], REAL["sources"]
    assert REAL["version"] == 2 and 36 <= len(clips) <= 44 and len(clips) <= own_media.MAX_CLIPS
    colour = [c for c in clips if c["colour"]]
    calm = [c for c in colour if c["mood"] == "calm"]
    assert len(colour) >= 28 and 6 <= len(calm) <= 8, (len(colour), len(calm))
    bw = [c for c in clips if not c["colour"]]
    assert {"machine_man", "moon_landing"} <= {c["id"] for c in bw} and all(c["mood"] == "drop" for c in bw)
    assert not GONE & {c["id"] for c in clips}  # out of the list, and on the taste file's banned_clips
    assert not {"general", "potemkin"} & set(sources)
    for c in clips:
        assert 6.0 <= float(c["seconds"]) <= 20.0, c["id"]
        assert c["source"] in sources and c["label"] and c["title"], c["id"]
        assert isinstance(c["colour"], bool) and isinstance(c["living"], bool) and c["mood"] in film_pack.MOODS, c["id"]
        assert 0.0 <= float(c["motion"]) <= 1.0, c["id"]
        if c.get("crop"):
            assert film_pack.CROP_RE.fullmatch(c["crop"]), c["id"]
        assert float(c["start"]) + float(c["seconds"]) <= float(sources[c["source"]]["seconds"]) + 1e-6, c["id"]
    # the order a cut draws on: colour opens, and the first dozen hold every mood
    assert clips[0]["colour"] and {c["mood"] for c in clips[:12]} == set(film_pack.MOODS)


def test_every_source_carries_its_url_its_file_its_size_and_its_licence():
    for key, s in REAL["sources"].items():
        assert str(s["url"]).startswith(HOSTS), key  # archive.org or NASA's own library, nothing else
        assert s["title"] and s["maker"] and s["licence"] and s["file"], key
        assert int(s["bytes"]) > 100_000 and float(s["seconds"]) > 5, key
        assert re.search(r"\(\S.*, \d{3,4}x\d{3,4}\)$", s["file"]), (key, s["file"])  # the derivative: format, width x height
        h = int(re.search(r"x(\d{3,4})\)$", s["file"]).group(1))
        assert h >= 478, (key, s["file"])  # the smallest derivative with 480 lines or more
        lic = s["licence"].lower()
        assert "public domain" in lic or "not protected by copyright" in lic or "united states government" in lic, key
        if s["url"].startswith(film_pack.NASA):
            assert s.get("page", "").startswith("https://images.nasa.gov/details/"), key
        else:
            assert s.get("item"), key
        if s.get("whole"):
            assert int(s["bytes"]) < 60_000_000, key  # only small files are fetched whole
    films = {k for k, s in REAL["sources"].items() if not s["url"].startswith(film_pack.NASA)}
    assert len(REAL["sources"]) - len(films) >= 4  # NASA's library is a source of its own


def test_the_loader_reads_the_shipped_list_as_it_is():
    assert film_pack.load_manifest()["clips"] == REAL["clips"]


# ---------------------------------------------------------------- the loader
def test_a_version_1_list_still_reads_and_its_source_crop_still_applies(monkeypatch, tmp_path):
    old = {"version": 1, "sources": {"moon": {"title": "A Trip to the Moon", "url": film_pack.ARCHIVE + "x/y.mp4",
                                              "crop": "928:720:176:0", "licence": "Public domain (1902)."}},
           "clips": [{"id": "trip_moon_face", "source": "moon", "start": 363.0, "seconds": 11.0, "title": "The Moon"}]}
    got = _load(monkeypatch, tmp_path, old)
    clip = got["clips"][0]
    assert got["version"] == 1 and not film_pack.fields_of(clip) and film_pack.label_entry(clip) == "The Moon"
    assert film_pack._crop(got["sources"], clip) == "928:720:176:0"
    # a clip's own crop wins over its source's, and none at all is none
    assert film_pack._crop(got["sources"], {**clip, "crop": "640:480:106:0"}) == "640:480:106:0"
    assert film_pack._crop({"s": {}}, {"source": "s"}) == ""


@pytest.mark.parametrize("field,value,words", [
    ("colour", "yes", "a colour that is not true or false"),
    ("living", 1, "a living that is not true or false"),
    ("motion", 1.5, "a motion that is not a number from 0 to 1"),
    ("motion", True, "a motion that is not a number from 0 to 1"),
    ("mood", "wild", "a mood that is not one of calm, build, drop"),
    ("crop", "left", "a crop that is not w:h:x:y"),
])
def test_a_field_of_the_wrong_kind_is_named(monkeypatch, tmp_path, field, value, words):
    bad = {"version": 2, "sources": {"s": {"url": film_pack.ARCHIVE + "a/b.mp4"}},
           "clips": [{"id": "one", "source": "s", "start": 0, "seconds": 8, field: value}]}
    with pytest.raises(ValueError, match=re.escape(words)) as caught:
        _load(monkeypatch, tmp_path, bad)
    assert "Clip 1 (one)" in str(caught.value)
    ok = {**bad, "clips": [{"id": "one", "source": "s", "start": 0, "seconds": 8, "colour": False, "motion": 0.4,
                            "living": True, "mood": "drop", "crop": "640:480:106:0"}]}
    clip = _load(monkeypatch, tmp_path, ok)["clips"][0]
    assert film_pack.fields_of(clip) == {"colour": False, "motion": 0.4, "living": True, "mood": "drop"}
    assert film_pack.label_entry({**clip, "label": "the moon"}) == {"label": "the moon", "colour": False, "motion": 0.4,
                                                                    "living": True, "mood": "drop"}


def test_the_status_says_where_the_clips_come_from(monkeypatch, tmp_path):
    monkeypatch.setenv("XENO_FILM_PACK", str(tmp_path / "pack"))
    data = {"version": 2, "sources": {"a": {"url": film_pack.ARCHIVE + "a/b.mp4"}, "n": {"url": film_pack.NASA + "video/x/x~medium.mp4"}},
            "clips": [{"id": "one", "source": "a", "start": 0, "seconds": 8}, {"id": "two", "source": "n", "start": 0, "seconds": 8}]}
    monkeypatch.setattr(film_pack, "manifest_path", lambda: _write(tmp_path, data))
    st = film_pack.status()
    assert "archive.org and NASA's video library" in st["detail"] and st["total"] == 2
    data["sources"].pop("n")
    data["clips"] = data["clips"][:1]
    assert "NASA" not in film_pack.status()["detail"]


# ---------------------------------------------------------------- the cut and the credits
def test_an_mpeg2_window_of_narrow_pixels_comes_out_square(tmp_path):
    """The FedFlix uploads store 720x480 at a pixel shape of 8:9 (a 4:3 picture): the pack's scale makes 640x480 of it,
    so a cut that crops by pixels (own_media.render_clip) frames it as it plays. A square-pixel file is untouched."""
    src = tmp_path / "narrow.mpg"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=720x480:rate=25:duration=3",
                    "-vf", "setsar=8/9", "-c:v", "mpeg2video", "-q:v", "4", str(src)], check=True)
    for name, source, crop, want in (("square.mp4", src, "", (640, 480)), ("cropped.mp4", src, "704:480:8:0", (624, 478))):
        out = tmp_path / name
        args = film_pack.ffmpeg_args(str(source), 0.5, 1.5, out, crop)
        subprocess.run(["ffmpeg"] + args, check=True, capture_output=True)
        probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,sample_aspect_ratio",
                                "-of", "csv=p=0", str(out)], capture_output=True, text=True, check=True).stdout.strip().split(",")
        w, h = int(probe[0]), int(probe[1])
        assert abs(w - want[0]) <= 2 and abs(h - want[1]) <= 2 and probe[2] in ("1:1", "N/A"), (name, probe)
    plain = tmp_path / "plain.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=24:duration=2",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(plain)], check=True)
    again = tmp_path / "again.mp4"
    subprocess.run(["ffmpeg"] + film_pack.ffmpeg_args(str(plain), 0.0, 1.0, again), check=True, capture_output=True)
    size = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                           "-of", "csv=p=0", str(again)], capture_output=True, text=True, check=True).stdout.strip()
    assert size == "1280,720"


def test_the_credits_name_the_file_taken_its_size_and_each_clips_colour_and_mood():
    text = film_pack.credits_text(REAL, [])
    for key, s in REAL["sources"].items():
        assert f"File taken: {s['file']}" in text, key
        assert f"{int(s['bytes']):,} bytes" in text and film_pack.item_url(s) in text and s["licence"] in text, key
    assert "| File | Film | Start (s) | Seconds | Clip | Colour | Mood |" in text
    first = REAL["clips"][0]
    row = next(line for line in text.splitlines() if line.startswith(f"| 01_{first['id']}.mp4 |"))
    assert row.endswith(f"| colour | {first['mood']} |")
    assert film_pack.item_url({"page": "https://images.nasa.gov/details/x", "url": film_pack.NASA + "video/x/x~medium.mp4"}) \
        == "https://images.nasa.gov/details/x"
    # a version 1 list's credits are as they were: no sizes, no colour column
    old = film_pack.credits_text({"sources": {"g": {"title": "The General", "year": 1926, "url": film_pack.ARCHIVE + "TheGeneral720p1926/x.mp4",
                                                    "licence": "Public domain (1926)."}},
                                  "clips": [{"id": "g_train", "source": "g", "start": 1.0, "seconds": 4.0}]}, [])
    assert "File taken" not in old and "| Colour |" not in old and "| 01_g_train.mp4 | The General | 1.0 | 4.0 | g train |" in old


# ---------------------------------------------------------------- the licences and the credits in the repo
def test_the_licences_and_the_credits_name_every_source_with_its_basis():
    """docs/LICENCES.md carries a row a source (its page, its licence basis, the file taken and its size) and CREDITS.md a
    line a source; the kinds of basis are the three the pack draws on, and nothing comes from a stock site."""
    licences = (ROOT / "docs" / "LICENCES.md").read_text(encoding="utf-8")
    credits = (ROOT / "CREDITS.md").read_text(encoding="utf-8")
    section = licences.split("## The free film pack's sources", 1)[1]
    for key, s in REAL["sources"].items():
        page = film_pack.item_url(s)
        row = next((line for line in section.splitlines() if line.startswith(f"| {s['title']} |") and page in line), "")
        assert row and s["licence"] in row and s["file"] in row, key
        assert f"{int(s['bytes']) / 1e6:.1f} MB" in row, key
        assert f"- {s['title']}" in credits and page in credits, key
    for words in ("Creative Commons Public Domain Dedication", "Works of the United States government", "Films published before 1929"):
        assert words in section, words
    assert "Nothing is taken from YouTube, Pexels, Pixabay" in section
    assert "40 clips from 29 sources" in licences and "40 short clips from 29 sources" in credits
