"""The morph cache (xenoform.morph_cache; docs/MUSIC_VIDEO_PLAN.md section 4): a clip kept by the request it was made
from (both guide stills' bytes, the final prompt and negative, the seed, the frames, the engine, the graph with its
img_compression, end_strength, steps and cfg), asked before a render and filled after one by the Draft, Final and
Cloud loops, and seeded from the jobs on disk by each clip's own embedded graph. A Cloud hit spends nothing; a Cloud miss
renders only behind the usual gate. Every engine here is a fake: no GPU, no ComfyUI, no Comfy Cloud."""
from __future__ import annotations

import copy
import hashlib
import json
import re
import shutil
import subprocess
import threading
from pathlib import Path

import pytest

from xenoform import cloud_backend, cloud_final, cloud_morph, dense, final_tier, morph_cache as mc, morph_pass as mp

ROOT = Path(__file__).resolve().parents[1]
HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _stills(folder: Path, n: int, tag: str = "") -> list[dict]:
    folder.mkdir(parents=True, exist_ok=True)
    out = []
    for i in range(n):
        p = folder / f"{i:02d}_thing{i}.png"
        p.write_bytes(f"png {i} {tag}".encode())
        out.append({"path": str(p), "noun": f"thing {i}", "file": p.name, "kind": "object"})
    return out


def _draft_graph() -> dict:
    return json.loads(mp.GRAPH.read_text(encoding="utf-8"))


def _sha(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ------------------------------------------------------------------------------------------------ the key


def test_the_key_covers_every_part_of_the_request(tmp_path):
    st = _stills(tmp_path, 3)
    g = _draft_graph()
    g["3"]["inputs"]["text"] = "a slow melt"
    g["13"]["inputs"]["noise_seed"] = 2727
    base, parts = mc.key_for(g, {"6": st[0]["path"], "7": st[1]["path"]}, "ltx095")
    assert re.fullmatch(r"[0-9a-f]{64}", base)
    assert parts["prompt"] == "a slow melt" and parts["seed"] == [2727] and parts["stills"][0] == "sha256:" + _sha(st[0]["path"])
    assert parts["negative"] == g["4"]["inputs"]["text"] and parts["frames"] == g["9"]["inputs"]["length"]
    for key_field in ("img_compression", "end_strength", "steps", "cfg", "width", "height", "graph", "engine"):
        assert key_field in parts

    def changed(edit, stills=None, engine="ltx095") -> str:
        g2 = copy.deepcopy(g)
        edit(g2)
        return mc.key_for(g2, stills or {"6": st[0]["path"], "7": st[1]["path"]}, engine)[0]

    variants = {
        "a still's bytes": changed(lambda x: None, {"6": st[2]["path"], "7": st[1]["path"]}),
        "the prompt": changed(lambda x: x["3"]["inputs"].update(text="a shatter")),
        "the negative": changed(lambda x: x["4"]["inputs"].update(text="text")),
        "the seed": changed(lambda x: x["13"]["inputs"].update(noise_seed=2728)),
        "the frames": changed(lambda x: x["9"]["inputs"].update(length=25)),
        "the size": changed(lambda x: x["9"]["inputs"].update(width=320)),
        "img_compression": changed(lambda x: x["8"]["inputs"].update(img_compression=7)),
        "end_strength": changed(lambda x: x["22"]["inputs"].update(strength=0.5)),
        "steps": changed(lambda x: x["11"]["inputs"].update(steps=9)),
        "cfg": changed(lambda x: x["14"]["inputs"].update(cfg=2.5)),
        "the graph": changed(lambda x: x["12"]["inputs"].update(sampler_name="dpmpp_2m")),
        "the engine": changed(lambda x: None, engine="ltx23"),
    }
    assert base not in variants.values() and len(set(variants.values())) == len(variants)
    # what is not the request: the output's file name, a node's title, ComfyUI's own notes, 24 written as 24.0
    same = changed(lambda x: (x["19"]["inputs"].update(filename_prefix="elsewhere"), x["6"].update(is_changed=["x"]),
                              x["3"].setdefault("_meta", {}).update(title="t"), x["18"]["inputs"].update(fps=int(x["18"]["inputs"]["fps"]))))
    assert same == base


def test_no_key_when_the_cache_is_off_or_a_still_is_unreadable(tmp_path, monkeypatch):
    st = _stills(tmp_path, 2)
    g = _draft_graph()
    assert mc.key_for(g, {"6": st[0]["path"], "7": str(tmp_path / "gone.png")}, "ltx095") is None
    monkeypatch.setenv("XENO_MORPH_CACHE", "off")
    assert mc.key_for(g, {"6": st[0]["path"], "7": st[1]["path"]}, "ltx095") is None and not mc.enabled()


def test_a_kept_clip_comes_back_only_when_it_is_whole(tmp_path):
    st = _stills(tmp_path, 2)
    kp = mc.key_for(_draft_graph(), {"6": st[0]["path"], "7": st[1]["path"]}, "ltx095")
    clip = tmp_path / "local00.mp4"
    clip.write_bytes(b"a morph")
    kept = mc.put("ltx095", kp, clip, verify=False)
    assert kept == mc.root() / "ltx095" / f"{kp[0]}.mp4" and kept.read_bytes() == b"a morph"
    side = json.loads(kept.with_suffix(".json").read_text(encoding="utf-8"))
    assert side["key"] == kp[0] and side["engine"] == "ltx095" and side["parts"]["stills"] and side["bytes"] == 7
    dest = tmp_path / "job" / "local00.mp4"
    assert mc.get("ltx095", kp, dest) and dest.read_bytes() == b"a morph"
    assert not mc.get("ltx23", kp, tmp_path / "other.mp4")  # one engine never answers for another
    kept.write_bytes(b"a morph cut sh")  # a kept clip changed under the cache: a miss, never a wrong picture
    assert not mc.get("ltx095", kp, tmp_path / "again.mp4") and not (tmp_path / "again.mp4").exists()


def _clip_with_graph(path: Path, graph: dict, stills: dict[str, str]) -> Path:
    """A tiny mp4 carrying the graph as ComfyUI writes it: the images by their uploaded names, each LoadImage's
    ``is_changed`` the sha256 of the picture, a SaveVideo prefix of its own."""
    g = copy.deepcopy(graph)
    for nid, p in stills.items():
        g[nid]["inputs"]["image"] = Path(p).name.replace(".png", " (1).png")
        g[nid]["is_changed"] = [_sha(p)]
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=gray:s=64x64:d=0.25", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", "-movflags", "use_metadata_tags", "-metadata", "prompt=" + json.dumps(g), str(path)],
                   check=True)
    return path


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg")
def test_a_clip_says_what_it_was_made_from(tmp_path):
    st = _stills(tmp_path, 2)
    g = _draft_graph()
    g["13"]["inputs"]["noise_seed"] = 31
    kp = mc.key_for(g, {"6": st[0]["path"], "7": st[1]["path"]}, "ltx095")
    clip = _clip_with_graph(tmp_path / "simple" / "local00.mp4", g, {"6": st[0]["path"], "7": st[1]["path"]})
    read = mc.key_from_clip(clip)
    assert read is not None and read[0] == kp[0] and read[1] == "ltx095"
    kept = mc.put("ltx095", kp, clip)
    assert json.loads(kept.with_suffix(".json").read_text(encoding="utf-8"))["verified"] is True
    assert mc.engine_of({"1": {"inputs": {"ckpt_name": "ltx-2.3-22b-distilled-fp8.safetensors"}}}, "final03.mp4") == "ltx23"
    assert mc.engine_of({"1": {"inputs": {"unet_name": "ltx-2.5-22b-x.safetensors"}}}, "cloud01.mp4") == "ltx25cloud"
    assert mc.engine_of({"1": {"inputs": {"unet_name": "ltx-2.5-22b-x.safetensors"}}}, "morph01.mp4") is None


# ------------------------------------------------------------------------------------------------ the Draft loop


class _Asset:
    def __init__(self, path):
        self.path = str(path)


class _Out:
    type = "video"

    def __init__(self, write):
        self.write = write

    def to_file(self, dest):
        self.write(Path(dest))


class _Job:
    status = "succeeded"

    def __init__(self, write):
        self.write = write
        self.id = "job"

    def result(self):
        write = self.write

        class R:
            outputs = []

            def get_outputs(self, nid):
                return [_Out(write)]

        return R()


class FakeComfy:
    """comfy-sdk as the loops use it, with the real Workflow class; a render writes a small mp4 that carries its graph
    (as ComfyUI does) when ffmpeg is here, else a few bytes; every submit is counted."""

    def __init__(self):
        from comfy_sdk.workflows import WorkflowFactory

        self.workflows = WorkflowFactory()
        self.assets = self
        self.jobs = self
        self.submitted: list[dict] = []
        self.uploaded: list[str] = []

    def from_file(self, path):
        self.uploaded.append(str(path))
        return _Asset(path)

    def submit(self, wf, api_key=None):
        graph = copy.deepcopy({k: v for k, v in wf.json.items()})
        images = {nid: n["inputs"]["image"].path for nid, n in graph.items()
                  if n.get("class_type") == "LoadImage" and isinstance(n["inputs"].get("image"), _Asset)}
        self.submitted.append(graph)
        k = len(self.submitted)

        def write(dest: Path):
            plain = {nid: {**n, "inputs": {**n["inputs"], **({"image": "x.png"} if nid in images else {})}} for nid, n in graph.items()}
            if HAS_FFMPEG:
                _clip_with_graph(dest, plain, images)
            else:
                dest.write_bytes(f"render {k}".encode())

        return _Job(write)


def _shots(n: int) -> list[dict]:
    return [{"index": i, "seconds": 2.0, "render_s": 2, "frames": 48} for i in range(n)]


def test_a_second_identical_draft_renders_nothing(tmp_path):
    st = _stills(tmp_path / "stills", 4)
    comfy = FakeComfy()
    first = cloud_morph._local_clips(_shots(3), st, tmp_path / "a", {}, 2727, "none", client=comfy, styles=["melt"] * 3)
    assert len(comfy.submitted) == 3 and len(comfy.uploaded) == 4  # the four stills, each sent once
    again = FakeComfy()
    seen = []
    second = cloud_morph._local_clips(_shots(3), st, tmp_path / "b", {}, 2727, "none", client=again, styles=["melt"] * 3,
                                      report=lambda stage, frac, detail: seen.append(detail))
    assert again.submitted == [] and again.uploaded == []  # nothing queued, nothing uploaded
    assert [p.read_bytes() for p in second] == [p.read_bytes() for p in first]
    assert all("kept from an earlier render" in d for d in seen)
    # a still that changes is a new request for the two morphs that touch it, the third still kept
    Path(st[1]["path"]).write_bytes(b"another picture")
    third = FakeComfy()
    cloud_morph._local_clips(_shots(3), st, tmp_path / "c", {}, 2727, "none", client=third, styles=["melt"] * 3)
    assert len(third.submitted) == 2
    # and another seed is another request
    fourth = FakeComfy()
    cloud_morph._local_clips(_shots(3), st, tmp_path / "d", {}, 99, "none", client=fourth, styles=["melt"] * 3)
    assert len(fourth.submitted) == 3


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg")
def test_a_draft_render_keeps_a_clip_its_own_graph_agrees_with(tmp_path):
    st = _stills(tmp_path / "stills", 2)
    cloud_morph._local_clips(_shots(1), st, tmp_path / "a", {}, 5, "cosmic", client=FakeComfy())
    sides = list((mc.root() / "ltx095").glob("*.json"))
    assert len(sides) == 1 and json.loads(sides[0].read_text(encoding="utf-8"))["verified"] is True


# ------------------------------------------------------------------------------------------------ the Final loop


def test_a_second_identical_final_renders_nothing(tmp_path):
    st = _stills(tmp_path / "stills", 3)
    comfy = FakeComfy()
    a, notes = final_tier.final_clips(_shots(2), st, tmp_path / "a", {}, 5, "black", client=comfy)
    assert len(comfy.submitted) == 2 and not notes
    again = FakeComfy()
    b, notes = final_tier.final_clips(_shots(2), st, tmp_path / "b", {}, 5, "black", client=again)
    assert again.submitted == [] and not notes
    assert [p.read_bytes() for p in b] == [p.read_bytes() for p in a]
    assert {p.parent.name for p in (mc.root()).glob("*/*.mp4")} == {final_tier.model()}


# ------------------------------------------------------------------------------------------------ the Cloud loop


class FakeCloud:
    """cloud_backend.CloudBackend's surface: counts what it would send, writes a small file a job."""

    max_parallel = 3

    def __init__(self):
        self.sent = 0
        self.prepared = 0
        self.lock = threading.Lock()

    def prepare(self, graph, open_weights=True):
        self.prepared += 1
        return graph

    def run(self, graph, out_dir, inputs=None, open_weights=True):
        with self.lock:
            self.sent += 1
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        save = next(n for n in graph.values() if n["class_type"] == "SaveVideo")
        out = Path(out_dir) / f"{save['inputs']['filename_prefix'].split('/')[-1]}.mp4"
        out.write_bytes(f"cloud render {save['inputs']['filename_prefix']} {graph['13']['inputs']['noise_seed']}".encode())
        return [out]


def test_a_cloud_hit_spends_nothing_and_needs_no_key(tmp_path, monkeypatch):
    monkeypatch.setenv(cloud_backend.KEY_ENV, "sk-test-not-a-key")
    st = _stills(tmp_path / "stills", 4)
    fake = FakeCloud()
    first, notes = cloud_final.cloud_clips(_shots(3), st, tmp_path / "a", {}, 2727, "none", vertical=False, backend=fake,
                                           name="ltx25")
    assert fake.sent == 3 and not notes and len(list((mc.root() / "ltx25cloud").glob("*.mp4"))) == 3
    monkeypatch.delenv(cloud_backend.KEY_ENV, raising=False)  # no key at all: every shot is kept, nothing is sent
    again = FakeCloud()
    seen = []
    second, notes = cloud_final.cloud_clips(_shots(3), st, tmp_path / "b", {}, 2727, "none", vertical=False, backend=again,
                                            name="ltx25", report=lambda stage, frac, detail: seen.append(detail))
    assert again.sent == 0 and again.prepared == 0 and not notes
    assert [p.read_bytes() for p in second] == [p.read_bytes() for p in first]
    assert any("kept from earlier renders, nothing sent" in d for d in seen)


def test_a_cloud_miss_never_renders_without_the_gate(tmp_path, monkeypatch):
    monkeypatch.setenv(cloud_backend.KEY_ENV, "sk-test-not-a-key")
    st = _stills(tmp_path / "stills", 4)
    cloud_final.cloud_clips(_shots(2), st, tmp_path / "a", {}, 2727, "none", vertical=False, backend=FakeCloud(), name="ltx25")
    monkeypatch.delenv(cloud_backend.KEY_ENV, raising=False)
    fake = FakeCloud()
    with pytest.raises(cloud_backend.CloudRefused):  # the third shot was never rendered: it needs the key, and has none
        cloud_final.cloud_clips(_shots(3), st, tmp_path / "b", {}, 2727, "none", vertical=False, backend=fake, name="ltx25")
    assert fake.sent == 0 and fake.prepared == 0
    monkeypatch.setenv(cloud_backend.KEY_ENV, "sk-test-not-a-key")
    fake = FakeCloud()
    cloud_final.cloud_clips(_shots(3), st, tmp_path / "c", {}, 2727, "none", vertical=False, backend=fake, name="ltx25")
    assert fake.sent == 1 and fake.prepared == 1  # with the key, only the miss goes


def test_the_make_still_asks_for_the_credits_tick_first(tmp_path):
    with pytest.raises(RuntimeError, match="Spend my Comfy Cloud credits"):
        dense.run_simple({"duration": 10.0, "beats": []}, ROOT / "examples" / "demo.wav", tmp_path / "x.mp4", tmp_path, {},
                         {"quality_tier": "cloud"}, lambda *a: None)


# ------------------------------------------------------------------------------------------------ seeding


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg")
def test_the_jobs_on_disk_seed_the_cache_and_a_draft_then_hits(tmp_path):
    st = _stills(tmp_path / "stills", 3)
    comfy = FakeComfy()
    work_ui = tmp_path / "work_ui"
    job = work_ui / "jobs" / "abcd1234" / "simple"
    cloud_morph._local_clips(_shots(2), st, job, {}, 7, "none", client=comfy, styles=["melt", "melt"])
    shutil.rmtree(mc.root())  # a machine whose cache is empty: only the job's clips are left
    (job / "notes.txt").write_text("not a clip", encoding="utf-8")
    (job / "cloud_full00.mp4").write_bytes(b"a scaled copy, not a morph")  # the scaled copies stay out
    dry = mc.seed(work_ui, dry_run=True)
    assert dry["seen"] == 2 and dry["kept"] == 2 and not (mc.root() / "ltx095").exists()
    got = mc.seed(work_ui)
    assert got["kept"] == 2 and got["engines"] == {"ltx095": 2}
    assert mc.seed(work_ui)["had"] == 2  # a second seed keeps nothing twice
    again = FakeComfy()
    cloud_morph._local_clips(_shots(2), st, tmp_path / "new", {}, 7, "none", client=again, styles=["melt", "melt"])
    assert again.submitted == []


def test_a_clip_that_does_not_say_enough_is_skipped(tmp_path):
    job = tmp_path / "work_ui" / "jobs" / "abcd1234" / "simple"
    job.mkdir(parents=True)
    (job / "local00.mp4").write_bytes(b"no graph inside")
    got = mc.seed(tmp_path / "work_ui")
    assert got["seen"] == 1 and got["kept"] == 0 and sum(got["skipped"].values()) == 1


def test_the_cli_seeds_and_says_what_it_kept(tmp_path, capsys):
    from xenoform import cli

    (tmp_path / "work_ui" / "jobs").mkdir(parents=True)
    assert cli.main(["morph-cache", "seed", "--work", str(tmp_path / "work_ui"), "--dry-run"]) == 0
    assert "0 clips read" in capsys.readouterr().out
    assert cli.main(["morph-cache", "status"]) == 0
    with pytest.raises(SystemExit, match="no jobs folder"):
        cli.main(["morph-cache", "seed", "--work", str(tmp_path / "nowhere")])
