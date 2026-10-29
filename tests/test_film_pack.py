"""The free film pack (Tys, 29 Oct: "lets include a bunch of those free domain clips in the app as an optional download"):
the manifest is sound, the pack is made from archive.org windows into one folder with its credits beside it, a clip that
fails is named while the rest come, a second run skips what is there, Setup carries the row and dispatches its Download,
the desk has the row and the Your clips button, and a clips cut takes up to 24 clips, each called by its label."""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from xenoform import clip_cut, film_pack, own_media
from xenoform.errors import PlainError

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
                                reason="ffmpeg and ffprobe make and read the tiny clips")

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src" / "xenoform" / "ui_static" / "app.js").read_text(encoding="utf-8")
ARCHIVE = "https://archive.org/download/"
ID_RE = re.compile(r"^[a-z0-9]+(?:[_-][a-z0-9]+)*$")

SOURCES = {
    "general": {"title": "The General", "year": 1926, "maker": "Buster Keaton and Clyde Bruckman", "item": "TheGeneral720p1926",
                "url": f"{ARCHIVE}TheGeneral720p1926/TheGeneral720p.mp4", "seconds": 6405.5, "licence": "Public domain (1926)."},
    "haxan": {"title": "Häxan", "year": 1922, "maker": "Benjamin Christensen", "item": "haxan-1922_202312",
              "url": f"{ARCHIVE}haxan-1922_202312/H%C3%A4xan%20%281922%29.mp4", "seconds": 6345.1, "licence": "Public domain (1922)."},
    "phantom": {"title": "The Phantom of the Opera", "year": 1925, "maker": "Rupert Julian, with Lon Chaney", "item": "CEP147",
                "url": f"{ARCHIVE}CEP147/CEP147.mpg", "seconds": 82.2, "bytes": 67800000, "whole": True, "licence": "Public domain (1925)."},
}


def _fn(start: str, end: str) -> str:
    return APP.split(start, 1)[1].split(end, 1)[0]


def _manifest(clips, sources=None, **extra) -> dict:
    data = {"version": 7, "name": "Free film pack", "folder": "film_pack", "sources": dict(sources or SOURCES), "clips": list(clips)}
    data.update(extra)
    return data


THREE = [{"id": "a_train", "source": "general", "start": 10.0, "seconds": 4.0, "title": "The General: the train", "label": "the train"},
         {"id": "b_witch", "source": "haxan", "start": 20.0, "seconds": 3.0, "title": "Häxan: the witch"},
         {"id": "c_mask", "source": "general", "start": 30.0, "seconds": 2.0, "title": "The General: the mask"}]


@pytest.fixture(scope="module")
def tiny(tmp_path_factory) -> Path:
    """One real 2 s mp4 (testsrc); the fakes copy it, so a run of twenty clips takes no time."""
    path = tmp_path_factory.mktemp("tiny") / "tiny.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=64x36:rate=24:duration=2",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)], check=True)
    return path


@pytest.fixture
def pack(tmp_path, monkeypatch):
    """An empty pack folder of its own, no waits between tries, the job reset before and after."""
    monkeypatch.setenv("XENO_FILM_PACK", str(tmp_path / "pack"))
    monkeypatch.delenv("XENO_OFFLINE", raising=False)
    monkeypatch.setattr(film_pack, "RETRY_WAIT_S", 0.0)
    film_pack._reset_for_tests()
    yield tmp_path / "pack"
    film_pack._reset_for_tests()


class Runner:
    """A fake ffmpeg: copies the tiny clip to the command's output, or fails the ids in ``fail``."""

    def __init__(self, tiny: Path, fail=()):
        self.tiny, self.fail, self.calls = tiny, tuple(fail), []

    def __call__(self, cmd, *, timeout):
        self.calls.append(list(cmd))
        dest = Path(cmd[-1])
        if any(f"_{fid}." in dest.name for fid in self.fail):
            raise subprocess.CalledProcessError(1, "ffmpeg", stderr=b"Server returned 404 Not Found")
        assert cmd[cmd.index("-ss") + 1] and cmd[cmd.index("-t") + 1] and "-an" in cmd and timeout > 60
        shutil.copyfile(self.tiny, dest)

    def inputs(self) -> list[str]:
        return [c[c.index("-i") + 1] for c in self.calls]


class Fetcher:
    """A fake whole-source download: writes a small file where the pack asked for it."""

    def __init__(self):
        self.calls = []

    def __call__(self, url, dest, *, expected_bytes, on_progress):
        self.calls.append(url)
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        on_progress(0.5, "half")
        dest.write_bytes(b"\0" * 1024)
        return dest


def _use(monkeypatch, manifest, runner, fetcher=None):
    monkeypatch.setattr(film_pack, "load_manifest", lambda: json.loads(json.dumps(manifest)))
    monkeypatch.setattr(film_pack, "RUNNER", runner)
    monkeypatch.setattr(film_pack, "FETCHER", fetcher or Fetcher())


# ---------------------------------------------------------------- the manifest
def test_the_manifest_is_valid():
    data = json.loads((ROOT / "configs" / "film_pack.json").read_text(encoding="utf-8"))
    sources, clips = data["sources"], data["clips"]
    assert data.get("folder") == "film_pack" and data.get("name") and clips
    for key, src in sources.items():
        assert ID_RE.match(key), key
        for field in ("title", "year", "maker", "licence", "url"):
            assert src.get(field), f"{key} needs {field}"
        assert str(src["url"]).startswith(ARCHIVE), key
        if src.get("whole"):
            assert int(src.get("bytes") or 0) > 0, f"{key} is whole and needs bytes"
    ids = [c["id"] for c in clips]
    assert len(ids) == len(set(ids)), "clip ids repeat"
    # a clips cut takes the first MAX_CLIPS of a folder: a longer list would be made and credited but not all played
    assert len(clips) <= own_media.MAX_CLIPS, f"{len(clips)} clips, and own_media.MAX_CLIPS is {own_media.MAX_CLIPS}"
    for clip in clips:
        assert ID_RE.match(clip["id"]), clip["id"]
        assert clip["source"] in sources, clip["id"]
        assert 2 <= float(clip["seconds"]) <= 30, clip["id"]
        assert float(clip["start"]) >= 0, clip["id"]
        length = float(sources[clip["source"]].get("seconds") or 0)
        if length:
            assert float(clip["start"]) + float(clip["seconds"]) <= length + 1e-6, f"{clip['id']} runs past its source"
    # the pack's own reading of it
    loaded = film_pack.load_manifest()
    assert loaded["clips"] == clips and film_pack.clip_name(clips[0], 0) == f"01_{clips[0]['id']}.mp4"


def test_status_on_an_empty_folder_says_not_present(pack):
    st = film_pack.status()
    real = film_pack.load_manifest()
    assert st["id"] == "film-pack" and st["present"] is False and st["count"] == 0 and st["total"] == len(real["clips"])
    assert st["badge"] == "Clips" and st["required"] is False and st["manual"] is False and st["stale"] == 0
    assert st["folder"] == str(pack) and not pack.exists()  # a check only looks; the download makes the folder
    assert st["files"][0] == f"01_{real['clips'][0]['id']}.mp4" and len(st["files"]) == st["total"]
    assert st["bytes"] == int(sum(c["seconds"] for c in real["clips"]) * film_pack.BYTES_PER_SECOND) and st["size_label"].endswith("MB")
    assert "archive.org" in st["detail"] and str(pack) in st["detail"] and f"{st['total']} clips" in st["detail"]
    assert film_pack.download_status() == {"status": "idle", "progress": 0, "detail": "", "error": None}


# ---------------------------------------------------------------- the download
def test_a_faked_runner_makes_the_whole_pack_with_its_credits(pack, monkeypatch, tiny):
    real = film_pack.load_manifest()
    runner, fetcher = Runner(tiny), Fetcher()
    monkeypatch.setattr(film_pack, "RUNNER", runner)
    monkeypatch.setattr(film_pack, "FETCHER", fetcher)
    first = film_pack.start()
    assert first["status"] == "running"
    st = film_pack.wait(120)
    assert st["status"] == "done" and st["progress"] == 1.0 and st["error"] is None, st
    assert str(pack) in st["detail"]
    after = film_pack.status()
    assert after["present"] is True and after["count"] == after["total"] == len(real["clips"])
    assert sorted(p.name for p in pack.glob("*.mp4")) == after["files"]
    # the url reaches ffmpeg as the manifest spells it, whole sources are cut from the fetched file
    whole = {k for k, s in real["sources"].items() if s.get("whole")}
    for clip, given in zip(real["clips"], runner.inputs()):
        url = real["sources"][clip["source"]]["url"]
        if clip["source"] in whole:
            assert given.startswith(str(pack / "_src")), given
        else:
            assert given == url, (given, url)
    assert sorted(fetcher.calls) == sorted({real["sources"][k]["url"] for k in whole if any(c["source"] == k for c in real["clips"])})
    # the sidecars
    credits = (pack / "CREDITS.md").read_text(encoding="utf-8")
    used = {c["source"] for c in real["clips"]}
    for key in used:
        src = real["sources"][key]
        assert src["title"] in credits and src["licence"] in credits and f"https://archive.org/details/{src['item']}" in credits
    for name in after["files"]:
        assert name in credits
    made = json.loads((pack / "pack.json").read_text(encoding="utf-8"))
    assert made["manifest_version"] == real.get("version", 1) and len(made["clips"]) == len(real["clips"]) and made["failed"] == []
    assert all(row["url"] and row["file"] and row["made_at"] for row in made["clips"])
    labels = json.loads((pack / "labels.json").read_text(encoding="utf-8"))
    assert set(labels) == set(after["files"]) and all(labels.values())


def test_a_clip_that_fails_is_named_and_the_rest_are_made(pack, monkeypatch, tiny):
    runner = Runner(tiny, fail=("b_witch",))
    _use(monkeypatch, _manifest(THREE), runner)
    film_pack.start()
    st = film_pack.wait(60)
    assert st["status"] == "error", st
    assert "Häxan: the witch" in st["detail"] and "2 of 3" in st["detail"] and "Häxan: the witch" in st["error"]
    assert abs(st["progress"] - 2 / 3) < 0.01
    assert (pack / "01_a_train.mp4").is_file() and (pack / "03_c_mask.mp4").is_file() and not (pack / "02_b_witch.mp4").exists()
    assert not list(pack.glob("*.part.mp4"))
    assert sum("_b_witch." in c[-1] for c in runner.calls) == film_pack.ATTEMPTS == 3
    made = json.loads((pack / "pack.json").read_text(encoding="utf-8"))
    assert [row["id"] for row in made["failed"]] == ["b_witch"] and [row["id"] for row in made["clips"]] == ["a_train", "c_mask"]
    assert "Not made on the last run: Häxan: the witch." in (pack / "CREDITS.md").read_text(encoding="utf-8")
    st2 = film_pack.status()
    assert st2["present"] is False and st2["count"] == 2 and "2 of 3" in st2["detail"]


def test_a_folder_of_your_own_keeps_your_files_through_a_download(pack, monkeypatch, tiny):
    # the stress pass, 29 Oct: with XENO_FILM_PACK on a folder of your own, a run emptied its _src, replaced your
    # labels.json and wrote over your CREDITS.md. Only the pack's own files are the pack's.
    pack.mkdir(parents=True)
    (pack / "_src").mkdir()
    (pack / "_src" / "my_master.mov").write_bytes(b"mine")
    (pack / "_src" / "edits").mkdir()
    (pack / "beach.mp4").write_bytes(b"mine")
    (pack / "labels.json").write_text(json.dumps({"beach.mp4": "the beach at dusk"}), encoding="utf-8")
    (pack / "CREDITS.md").write_text("# My credits\n", encoding="utf-8")
    clips = THREE + [{"id": "d_ghost", "source": "phantom", "start": 1.0, "seconds": 2.0, "title": "Phantom: the mask"}]
    _use(monkeypatch, _manifest(clips), Runner(tiny))
    film_pack.start()
    st = film_pack.wait(60)
    assert st["status"] == "done", st  # a folder in _src no longer ends the run on Access is denied
    assert (pack / "_src" / "my_master.mov").read_bytes() == b"mine" and (pack / "_src" / "edits").is_dir()
    assert not (pack / "_src" / "CEP147.mpg").exists()  # the whole film the pack fetched has served and goes
    labels = json.loads((pack / "labels.json").read_text(encoding="utf-8"))
    assert labels["beach.mp4"] == "the beach at dusk" and labels["01_a_train.mp4"] == "the train"
    assert (pack / "CREDITS.md").read_text(encoding="utf-8") == "# My credits\n" and (pack / "beach.mp4").is_file()


def test_a_second_run_skips_the_clips_already_there(pack, monkeypatch, tiny):
    _use(monkeypatch, _manifest(THREE), Runner(tiny))
    film_pack.start()
    assert film_pack.wait(60)["status"] == "done"
    film_pack._reset_for_tests()
    again = Runner(tiny)
    monkeypatch.setattr(film_pack, "RUNNER", again)
    film_pack.start()
    st = film_pack.wait(60)
    assert st["status"] == "done" and st["progress"] == 1.0 and again.calls == []
    made = json.loads((pack / "pack.json").read_text(encoding="utf-8"))
    assert all(row["kept"] for row in made["clips"]) and len(made["clips"]) == 3
    # a clip that is on disk but broken is made again
    (pack / "02_b_witch.mp4").write_bytes(b"not a video")
    film_pack._reset_for_tests()
    third = Runner(tiny)
    monkeypatch.setattr(film_pack, "RUNNER", third)
    film_pack.start()
    assert film_pack.wait(60)["status"] == "done" and [Path(c[-1]).name for c in third.calls] == ["02_b_witch.part.mp4"]
    assert film_pack.remove(pack) == 3 and not list(pack.glob("*.mp4")) and film_pack.status()["count"] == 0


def test_a_whole_source_is_fetched_once_cut_from_disk_and_removed_when_its_clips_are_in_place(pack, monkeypatch, tiny):
    clips = [{"id": "p_one", "source": "phantom", "start": 5.0, "seconds": 4.0, "title": "The Phantom: the mask"},
             {"id": "p_two", "source": "phantom", "start": 40.0, "seconds": 4.0, "title": "The Phantom: the chandelier"}]
    runner, fetcher = Runner(tiny, fail=("p_two",)), Fetcher()
    _use(monkeypatch, _manifest(clips), runner, fetcher)
    film_pack.start()
    st = film_pack.wait(60)
    assert st["status"] == "error" and "the chandelier" in st["detail"], st
    assert fetcher.calls == [SOURCES["phantom"]["url"]]
    local = pack / "_src" / "CEP147.mpg"
    assert local.is_file() and runner.inputs() and all(given == str(local) for given in runner.inputs())  # kept for the retry
    # the retry: the clip that was missing is cut from the film, and the film goes once every clip of it is in place
    film_pack._reset_for_tests()
    good = Runner(tiny)
    monkeypatch.setattr(film_pack, "RUNNER", good)
    film_pack.start()
    st = film_pack.wait(60)
    assert st["status"] == "done", st
    assert [Path(c[-1]).name for c in good.calls] == ["02_p_two.part.mp4"] and good.inputs() == [str(local)]
    assert not local.exists() and not (pack / "_src").exists() and film_pack.status()["present"] is True
    # a whole source that will not come fails both its clips and is asked for once
    film_pack.remove(pack)
    film_pack._reset_for_tests()

    class Dead(Fetcher):
        def __call__(self, url, dest, **kw):
            self.calls.append(url)
            raise PlainError("The download of CEP147.mpg did not start.")

    dead = Dead()
    monkeypatch.setattr(film_pack, "FETCHER", dead)
    film_pack.start()
    st = film_pack.wait(60)
    assert st["status"] == "error" and "the mask" in st["detail"] and "the chandelier" in st["detail"] and len(dead.calls) == 1


def test_a_whole_source_takes_the_servers_size_and_falls_back_to_the_lists(pack, monkeypatch, tmp_path):
    """_fetch_whole: the HEAD's Content-Length is the size download_file checks (the list's bytes is a round figure, and a
    wrong size deletes a finished 68 MB download), the list's bytes stands in when the HEAD fails, and no checksum is asked."""
    from xenoform import models_setup

    seen = []

    def fake_download(url, dest, *, sha256, expected_bytes, on_progress=None, opener=None):
        seen.append((url, Path(dest).name, sha256, expected_bytes))
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Path(dest).write_bytes(b"\0" * 8)
        return Path(dest)

    monkeypatch.setattr(models_setup, "download_file", fake_download)
    content_length = film_pack._content_length  # the real one, tested below after the fakes above it
    monkeypatch.setattr(film_pack, "_content_length", lambda url: 123456)
    url = SOURCES["phantom"]["url"]
    out = film_pack._fetch_whole(url, tmp_path / "_src" / "CEP147.mpg", expected_bytes=67800000, on_progress=lambda f, d: None)
    assert out.is_file() and seen[-1] == (url, "CEP147.mpg", "", 123456)
    monkeypatch.setattr(film_pack, "_content_length", lambda url: 0)
    film_pack._fetch_whole(url, tmp_path / "_src" / "CEP147.mpg", expected_bytes=67800000, on_progress=lambda f, d: None)
    assert seen[-1][3] == 67800000
    # _content_length itself: a HEAD that answers, one that does not
    asked = []

    class Head:
        headers = {"Content-Length": "4242"}

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def head(request, timeout):
        asked.append((request.full_url, request.get_method(), timeout))
        return Head()

    monkeypatch.setattr(film_pack, "urlopen", head)
    assert content_length(url) == 4242 and asked == [(url, "HEAD", 30)]

    def dead(request, timeout):
        raise OSError("no network")

    monkeypatch.setattr(film_pack, "urlopen", dead)
    assert content_length(url) == 0


def test_a_clip_whose_window_moved_in_the_list_is_made_again(pack, monkeypatch, tiny):
    """The list is curated after a pack is made (02_trip_moon_face went from 358 s for 16 s to 363 s for 11 s on 29 Oct):
    pack.json carries the window each file was cut from, status() counts the ones that differ, and Download again remakes
    only those. A remake that fails leaves the older cut on disk and on record, so the next run still knows."""
    _use(monkeypatch, _manifest(THREE), Runner(tiny))
    film_pack.start()
    assert film_pack.wait(60)["status"] == "done"
    moved = [THREE[0], {**THREE[1], "start": 25.0, "seconds": 5.0}, THREE[2]]
    again = Runner(tiny)
    _use(monkeypatch, _manifest(moved), again)
    st = film_pack.status()
    assert st["present"] is True and st["count"] == 3 and st["stale"] == 1 and "1 was cut with older times" in st["detail"], st
    film_pack._reset_for_tests()
    film_pack.start()
    assert film_pack.wait(60)["status"] == "done"
    assert [Path(c[-1]).name for c in again.calls] == ["02_b_witch.part.mp4"]
    assert again.calls[0][again.calls[0].index("-ss") + 1] == "25.000" and again.calls[0][again.calls[0].index("-t") + 1] == "5.000"
    made = {row["id"]: row for row in json.loads((pack / "pack.json").read_text(encoding="utf-8"))["clips"]}
    assert made["b_witch"]["start"] == 25.0 and made["b_witch"]["made_at"] and made["b_witch"]["kept"] is False
    assert made["a_train"]["kept"] is True and made["a_train"]["made_at"]  # a kept clip keeps the time it was made
    assert film_pack.status()["stale"] == 0
    # the remake fails: the older cut stays, and the record still says what it is
    third = Runner(tiny, fail=("b_witch",))
    _use(monkeypatch, _manifest([THREE[0], {**THREE[1], "start": 26.0, "seconds": 5.0}, THREE[2]]), third)
    film_pack._reset_for_tests()
    film_pack.start()
    st = film_pack.wait(60)
    assert st["status"] == "error" and "2 of 3" in st["detail"] and (pack / "02_b_witch.mp4").is_file(), st
    st2 = film_pack.status()
    assert st2["present"] is True and st2["count"] == 3 and st2["stale"] == 1
    rows = json.loads((pack / "pack.json").read_text(encoding="utf-8"))
    kept = next(r for r in rows["clips"] if r["id"] == "b_witch")
    assert kept["stale"] is True and kept["start"] == 25.0 and [f["id"] for f in rows["failed"]] == ["b_witch"]


def test_a_clip_that_leaves_the_list_is_removed_and_a_reorder_moves_the_files(pack, monkeypatch, tiny):
    """File names carry the list position, so an insert or a drop shifts every name after it: a shifted clip is moved to
    its new name rather than pulled again, a file the pack made for a clip that left the list goes, and a file of the
    user's beside the pack is never touched (remove() too)."""
    _use(monkeypatch, _manifest(THREE), Runner(tiny))
    film_pack.start()
    assert film_pack.wait(60)["status"] == "done"
    shutil.copyfile(tiny, pack / "my_holiday.mp4")
    new = [{"id": "z_new", "source": "general", "start": 50.0, "seconds": 3.0, "title": "The General: the new one"}, THREE[2], THREE[0]]
    again = Runner(tiny)
    _use(monkeypatch, _manifest(new), again)
    film_pack._reset_for_tests()
    film_pack.start()
    st = film_pack.wait(60)
    assert st["status"] == "done" and "1 that left the list was removed" in st["detail"], st
    assert [Path(c[-1]).name for c in again.calls] == ["01_z_new.part.mp4"]
    assert sorted(p.name for p in pack.glob("*.mp4")) == ["01_z_new.mp4", "02_c_mask.mp4", "03_a_train.mp4", "my_holiday.mp4"]
    made = json.loads((pack / "pack.json").read_text(encoding="utf-8"))
    assert made["removed"] == ["02_b_witch.mp4"]
    assert {r["id"]: r.get("was") for r in made["clips"]} == {"z_new": None, "c_mask": "03_c_mask.mp4", "a_train": "01_a_train.mp4"}
    after = film_pack.status()
    assert after["present"] is True and after["count"] == 3 and after["stale"] == 0
    labels = json.loads((pack / "labels.json").read_text(encoding="utf-8"))
    assert labels == {"01_z_new.mp4": "The General: the new one", "02_c_mask.mp4": "The General: the mask", "03_a_train.mp4": "the train"}
    assert clip_cut.clip_names(own_media.scan(pack)["clips"])[:3] == ["The General: the new one", "The General: the mask", "the train"]
    assert film_pack.remove(pack) == 3 and [p.name for p in pack.glob("*.mp4")] == ["my_holiday.mp4"]


def test_without_ffmpeg_or_ffprobe_the_download_says_so_once(pack, monkeypatch, tiny):
    """No three tries a clip for a tool that is not there: one sentence before any clip, nothing touched. Without ffprobe
    the check counts the files that are there and says the clips cannot be checked."""
    _use(monkeypatch, _manifest(THREE), Runner(tiny))
    film_pack.start()
    assert film_pack.wait(60)["status"] == "done"
    real_which = shutil.which
    for gone in ("ffmpeg", "ffprobe"):
        monkeypatch.setattr(shutil, "which", lambda name, *a, _gone=gone, **k: None if name == _gone else real_which(name, *a, **k))
        st = film_pack.status()
        assert st["present"] is True and st["count"] == 3 and f"{gone} is not on PATH" in st["detail"], st
        runner = Runner(tiny)
        monkeypatch.setattr(film_pack, "RUNNER", runner)
        film_pack._reset_for_tests()
        film_pack.start()
        st = film_pack.wait(30)
        assert st["status"] == "error" and f"{gone} is not on PATH" in st["detail"] and runner.calls == [], st
    monkeypatch.setattr(shutil, "which", real_which)
    assert film_pack.status()["present"] is True


def test_status_and_the_route_survive_a_bad_list_an_empty_one_and_a_folder_that_cannot_be_made(pack, monkeypatch, tiny):
    from fastapi.testclient import TestClient

    from xenoform.ui import create_app

    client = TestClient(create_app())
    real_path = film_pack.manifest_path
    bad = pack.parent / "bad.json"
    cases = (('{"clips": [{"source": "general", "start": 1, "seconds": 3}]}', "Clip 1 in configs/film_pack.json has no id"),
             ('{"clips": [{"id": "x", "source": "general", "start": 1, "seconds": "five"}]}', "Clip 1 (x) in configs/film_pack.json has a start or seconds that is not a number"),
             ('{"clips": {"a": 1}}', "clips as a list"),
             ('{"clips": ["x"]}', "Clip 1 in configs/film_pack.json has no id"),
             ("not json", "could not be read"))
    for k, (text, words) in enumerate(cases):
        bad.write_text(text, encoding="utf-8")
        monkeypatch.setattr(film_pack, "manifest_path", lambda: bad)
        st = film_pack.status()
        assert st["present"] is False and st["total"] == 0 and "could not be read" in st["detail"] and words in st["detail"], st
        assert client.get("/api/film_pack").status_code == 200
        if k == 0:
            assert client.get("/api/setup").json()["film_pack"]["detail"] == st["detail"]
        film_pack._reset_for_tests()
        film_pack.start()
        st2 = film_pack.wait(30)
        assert st2["status"] == "error" and st2["detail"] and not (pack / "pack.json").exists(), st2
    monkeypatch.setattr(film_pack, "manifest_path", real_path)
    # an empty list: nothing to download, no sidecars written for it
    _use(monkeypatch, _manifest([]), Runner(tiny))
    st = film_pack.status()
    assert st["total"] == 0 and st["present"] is False and "empty" in st["detail"]
    film_pack._reset_for_tests()
    film_pack.start()
    st2 = film_pack.wait(30)
    assert st2["status"] == "error" and "empty" in st2["detail"] and not list(pack.glob("*"))
    # a folder that cannot be made (XENO_FILM_PACK under a file): the check says not present, the route answers, the download says why
    _use(monkeypatch, _manifest(THREE), Runner(tiny))
    blocker = pack.parent / "blocker"
    blocker.write_text("a file, not a folder", encoding="utf-8")
    monkeypatch.setenv("XENO_FILM_PACK", str(blocker / "pack"))
    st = film_pack.status()
    assert st["present"] is False and st["count"] == 0 and st["total"] == 3 and st["folder"] == str(blocker / "pack"), st
    assert client.get("/api/film_pack").status_code == 200
    film_pack._reset_for_tests()
    film_pack.start()
    st2 = film_pack.wait(30)
    assert st2["status"] == "error" and "could not be made" in st2["detail"] and "XENO_FILM_PACK" in st2["detail"], st2


def test_the_url_is_passed_through_untouched(pack, monkeypatch, tiny):
    runner = Runner(tiny)
    _use(monkeypatch, _manifest([{"id": "haxan_sabbath", "source": "haxan", "start": 100.0, "seconds": 5.0, "title": "Häxan: the sabbath"}]), runner)
    film_pack.start()
    assert film_pack.wait(60)["status"] == "done"
    assert runner.inputs() == [f"{ARCHIVE}haxan-1922_202312/H%C3%A4xan%20%281922%29.mp4"]
    args = runner.calls[0]
    assert args[:4] == ["-y", "-v", "error", "-nostdin"] and args[args.index("-ss") + 1] == "100.000" and args[args.index("-t") + 1] == "5.000"
    assert "libx264" in args and "+faststart" in args and args[-1].endswith("01_haxan_sabbath.part.mp4")


def test_offline_refuses_with_a_plain_sentence(pack, monkeypatch):
    monkeypatch.setenv("XENO_OFFLINE", "1")
    with pytest.raises(PlainError) as caught:
        film_pack.start()
    assert "XENO_OFFLINE" in str(caught.value) and film_pack.download_status()["status"] == "idle"


def test_the_labels_and_the_credits_text():
    manifest = _manifest(THREE)
    assert [film_pack.clip_label(c) for c in THREE] == ["the train", "Häxan: the witch", "The General: the mask"]
    assert film_pack.clip_label({"id": "trip_moon_eye"}) == "trip moon eye"
    text = film_pack.credits_text(manifest, [])
    assert text.startswith("# Free film pack") and "configs/film_pack.json (version 7)" in text
    assert "- **The General** (1926), Buster Keaton and Clyde Bruckman. https://archive.org/details/TheGeneral720p1926. Public domain (1926)." in text
    assert "| 02_b_witch.mp4 | Häxan | 20.0 | 3.0 | Häxan: the witch |" in text
    assert "Phantom" not in text  # a source no clip uses is not credited
    assert film_pack.item_url({"url": f"{ARCHIVE}lost_world/lost_world.mp4"}) == "https://archive.org/details/lost_world"


# ---------------------------------------------------------------- Setup and the routes
def test_setup_carries_the_pack_and_dispatches_its_download(pack, monkeypatch, tmp_path, tiny):
    from xenoform.models_setup import download_status, inspect_setup, start_download

    _use(monkeypatch, _manifest(THREE), Runner(tiny))
    row = inspect_setup(tmp_path / "models")["film_pack"]
    assert row["id"] == "film-pack" and row["present"] is False and row["total"] == 3 and row["name"] == "Free film pack"
    assert set(row) >= {"name", "required", "badge", "manual", "present", "bytes", "size_label", "detail", "files", "count", "total", "folder"}
    assert download_status("film-pack")["status"] == "idle"
    started = start_download("film-pack")
    assert started["status"] in ("running", "done")
    assert film_pack.wait(60)["status"] == "done" and download_status("film-pack")["progress"] == 1.0
    assert inspect_setup(tmp_path / "models")["film_pack"]["present"] is True


def test_the_routes_answer(pack, monkeypatch, tiny):
    from fastapi.testclient import TestClient

    from xenoform.ui import create_app

    _use(monkeypatch, _manifest(THREE), Runner(tiny))
    client = TestClient(create_app())
    setup = client.get("/api/setup").json()
    assert setup["film_pack"]["id"] == "film-pack" and setup["film_pack"]["present"] is False
    row = client.get("/api/film_pack").json()
    assert row["id"] == "film-pack" and row["total"] == 3 and row["count"] == 0 and row["download"]["status"] == "idle"
    monkeypatch.setenv("XENO_OFFLINE", "1")
    refused = client.post("/api/setup/download", json={"id": "film-pack"})
    assert refused.status_code == 400 and "XENO_OFFLINE" in refused.json()["detail"]
    monkeypatch.delenv("XENO_OFFLINE")
    started = client.post("/api/setup/download", json={"id": "film-pack"}).json()
    assert started["status"] in ("running", "done")
    film_pack.wait(60)
    done = client.get("/api/setup/download/film-pack").json()
    assert done["status"] == "done" and done["progress"] == 1.0
    row = client.get("/api/film_pack").json()
    assert row["present"] is True and row["count"] == 3 and row["download"]["status"] == "done"


# ---------------------------------------------------------------- the desk
def test_the_desk_has_the_setup_row_and_the_clips_button():
    clips_row = _fn("function sourceRow(easy)", "\n}\n")
    assert 'data-act="easy-film-pack"' in clips_row and ">Free film pack</button>" in clips_row
    assert 'data-act="go" data-hash="setup"' in clips_row and "easy.ownNoteSetup" in clips_row
    assert 'act === "easy-film-pack"' in APP and "pickFilmPack();" in APP
    pick = _fn("async function pickFilmPack()", "\n}\n")
    assert '"/api/film_pack"' in pick and "state.setup.film_pack" in pick and "state.easy.ownFolder = pack.folder" in pick
    assert 'state.easy.ownId = ""' in pick and "Download the free film pack in Setup & models first" in pick and '"100 MB"' in pick
    setup = _fn("function renderSetup()", "\n}\n")
    assert "filmPackCard(setup.film_pack)" in setup
    assert 'id="dl-status-${esc(model.id)}"' in setup and 'id="dl-track-${esc(model.id)}"' in setup
    card = _fn("function filmPackCard(pack)", "\n}\n")
    assert 'data-act="download-model" data-id="${esc(pack.id)}"' in card and "Download again" in card and 'class="track"' in card
    assert 'id="dl-status-${esc(pack.id)}"' in card and 'id="dl-track-${esc(pack.id)}"' in card
    assert "pack.total" in card and "pack.stale" in card  # no button for an empty list; the stale count on the status line
    assert '`Download · ${esc(pack.size_label)}`' in card and '"Download again"' in card  # no size on Download again
    poll = _fn("async function pollDownload(id)", "\n}\n")
    assert 'if (id === "film-pack") state.filmPack = null;' in poll
    # a running download rewrites its own line and bar by id; the page is drawn again only when the job changes shape
    assert "getElementById(`dl-status-${id}`)" in poll and "getElementById(`dl-track-${id}`)" in poll
    assert 'before.status === "running" && line && bar' in poll and "bar.style.width" in poll and "line.textContent" in poll


# ---------------------------------------------------------------- the clips cap and the labels
def test_a_folder_gives_up_to_24_clips_and_the_cut_cycles_through_them_all(tmp_path, tiny):
    for k in range(26):
        shutil.copyfile(tiny, tmp_path / f"{k:02d}_reel.mp4")
    # only words are labels: a number, an object or blank space in the sidecar leaves the id-derived name
    (tmp_path / "labels.json").write_text(json.dumps({"00_reel.mp4": " the opening reel ", "01_reel.mp4": 7, "02_reel.mp4": {"a": 1}, "03_reel.mp4": "  "}), encoding="utf-8")
    found = own_media.scan(tmp_path)
    assert own_media.MAX_ITEMS == 12 and own_media.MAX_CLIPS == 24 and len(found["clips"]) == 24
    assert [Path(c["path"]).name for c in found["clips"]] == [f"{k:02d}_reel.mp4" for k in range(24)]
    assert found["clips"][0]["label"] == "the opening reel" and all("label" not in c for c in found["clips"][1:4])
    plan = clip_cut.slots(2 * 24 - 1, 24)
    assert {s["clip"] for s in plan if s["kind"] == "clip"} == set(range(24))
    assert clip_cut.clip_names(found["clips"][:3]) == ["the opening reel", "reel", "reel"]
    assert clip_cut.clip_names([{"path": "x/03_trip_moon_eye.mp4"}, {"path": "y/reel.mp4"}]) == ["trip moon eye", "reel"]


# ---------------------------------------------------------------- the docs
def test_the_docs_name_the_pack():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "free film pack" in readme.lower() and "configs/film_pack.json" in readme and "archive.org" in readme
    unreleased = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8").split("## 0.3.3")[1].split("## 0.3.2")[0]
    assert "The free film pack" in unreleased and "xenoform.film_pack" in unreleased and "MAX_CLIPS" in unreleased and "/api/film_pack" in unreleased
    credits = (ROOT / "CREDITS.md").read_text(encoding="utf-8")
    assert "## Free film pack" in credits and "configs/film_pack.json" in credits and "work/ui/film_pack/CREDITS.md" in credits
    licences = (ROOT / "docs" / "LICENCES.md").read_text(encoding="utf-8")
    assert "Free film pack" in licences and "configs/film_pack.json" in licences
    footage = (ROOT / "docs" / "footage.md").read_text(encoding="utf-8")
    assert "## The free film pack" in footage and "XENO_FILM_PACK" in footage


def test_the_real_runner_cuts_a_window_from_a_local_source(pack, monkeypatch):
    """No network: the shipped demo_base.mp4 stands in for the archive.org file, through the real ffmpeg call."""
    source = ROOT / "examples" / "demo_base.mp4"
    assert source.is_file() and film_pack.probe_seconds(source) > 4
    manifest = _manifest([{"id": "demo_window", "source": "demo", "start": 1.0, "seconds": 2.0, "title": "The demo: a window"}],
                         sources={"demo": {"title": "Demo base", "year": 2026, "maker": "xenoform", "url": str(source), "licence": "MIT (this repo)."}})
    monkeypatch.setattr(film_pack, "load_manifest", lambda: manifest)
    film_pack.start()
    st = film_pack.wait(120)
    assert st["status"] == "done", st
    out = pack / "01_demo_window.mp4"
    assert film_pack.clip_ready(out) and abs(film_pack.probe_seconds(out) - 2.0) < 0.15
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,r_frame_rate,pix_fmt",
                            "-of", "default=noprint_wrappers=1", str(out)], capture_output=True, text=True, check=True).stdout
    fields = dict(line.split("=", 1) for line in probe.strip().splitlines() if "=" in line)
    assert int(fields["width"]) <= 1280 and fields["r_frame_rate"] in ("24/1", "24") and fields["pix_fmt"] == "yuv420p"
    assert not list(pack.glob("*.part.mp4"))


def test_a_source_with_bars_baked_in_is_cropped_and_a_changed_crop_remakes_the_clip():
    """Two of the uploads (the Méliès and the Apollo files) are a 4:3 picture inside a 16:9 frame: the manifest's crop
    is cut off before the scale, it is recorded with the clip, and a clip cut before the crop was known is made again."""
    real = film_pack.load_manifest()
    cropped = {k: s["crop"] for k, s in real["sources"].items() if s.get("crop")}
    assert cropped and all(film_pack.CROP_RE.fullmatch(c) for c in cropped.values())
    args = film_pack.ffmpeg_args("https://x/y.mp4", 10.0, 4.0, Path("out.mp4"), "928:720:176:0")
    assert args[args.index("-vf") + 1] == "crop=928:720:176:0," + film_pack.SCALE
    assert film_pack.ffmpeg_args("a", 0, 1, Path("o.mp4"))[args.index("-vf") + 1] == film_pack.SCALE
    clip = {"start": 10.0, "seconds": 4.0}
    assert film_pack._same_window({"start": 10.0, "seconds": 4.0, "url": "u", "crop": "928:720:176:0"}, clip, "u", "928:720:176:0")
    assert not film_pack._same_window({"start": 10.0, "seconds": 4.0, "url": "u"}, clip, "u", "928:720:176:0")
    assert not film_pack._same_window({"start": 10.0, "seconds": 4.0, "url": "u", "crop": "1:1:1:1"}, clip, "u", "")


# ---------------------------------------------------------------- live
@pytest.mark.skipif(os.environ.get("XENO_LIVE_TESTS") != "1", reason="network: XENO_LIVE_TESTS=1 pulls one clip from archive.org")
def test_live_the_shortest_clip_comes_down(pack, monkeypatch):
    """One real pull from archive.org through ffmpeg's http seek: the shortest clip in the list whose source is read over
    http (a whole source would fetch a film), so the test follows the curated list and says which clip it took."""
    real = film_pack.load_manifest()
    over_http = [c for c in real["clips"] if not (real["sources"].get(c["source"]) or {}).get("whole")]
    clip = min(over_http, key=lambda c: float(c["seconds"]))
    print(f"live: {clip['id']} ({clip['seconds']} s of {real['sources'][clip['source']]['url']})")
    monkeypatch.setattr(film_pack, "load_manifest", lambda: {**real, "clips": [clip]})
    film_pack.start()
    st = film_pack.wait(300)
    assert st["status"] == "done", st
    path = film_pack.clip_path(clip, 0, pack)
    seconds = film_pack.probe_seconds(path)
    assert abs(seconds - float(clip["seconds"])) < 0.6, (seconds, clip)
    assert (pack / "CREDITS.md").is_file() and film_pack.status()["present"] is True
