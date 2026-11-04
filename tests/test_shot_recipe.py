"""Under the hood (docs/UI_REVIEW.md 6.4): each shot's morph request is recorded at render time beside its clip
(``simple.json`` ``renders``, the graphs under ``simple/requests/``), for the Draft, the Final and Cloud Final alike, and
kept in step through a re-render, a swap and a generated run (``shot_recipe``)."""
import json
import re
from pathlib import Path

import pytest
from comfy_sdk.workflows import Workflow

from xenoform import beatfx, dense, final_tier, morph_cache as mc, morph_pass as mp, shot_recipe as sr
from xenoform import stills as S

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "examples" / "demo.wav"
GRAPH = json.loads((ROOT / "workflows" / "xenoform_morph.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------------------------- a fake ComfyUI


class Out:
    type = "video"

    def __init__(self, sent: dict):
        self.sent = sent

    def to_file(self, path):
        # the bytes stand for the clip; they carry the seed so two renders of one pair differ
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(json.dumps({"seed": self.sent.get("13", {}).get("inputs", {}).get("noise_seed")}).encode())


class Job:
    def __init__(self, sent: dict):
        self.sent = sent
        self.id = "job"
        self.status = "succeeded"

    def refresh(self):
        return None

    def result(self):
        sent = self.sent

        class R:
            outputs = [Out(sent)]

            def get_outputs(self, node):
                return [Out(sent)]

        return R()


class Client:
    """A ComfyUI through comfy-sdk's own Workflow objects: what is submitted is kept, as the proxy would queue it."""

    def __init__(self):
        self.sent: list[dict] = []
        outer = self

        class assets:
            @staticmethod
            def from_file(path):
                return Path(path).name  # what the upload names the still in ComfyUI's input folder

        class workflows:
            @staticmethod
            def from_file(path):
                return Workflow(json.loads(Path(path).read_text(encoding="utf-8")))

            @staticmethod
            def from_json(graph):
                return Workflow(graph)

        self.assets = assets
        self.workflows = workflows
        self.outer = outer

    def submit(self, wf):
        sent = json.loads(json.dumps(wf.json, default=str))
        self.sent.append(sent)
        return Job(sent)


def _fake_compose(seen):
    def compose(clips, shots, audio, out, **kw):
        seen["clips"] = [str(c) for c in clips]
        Path(out).write_bytes(b"new")
        return {"frames": 1, "seconds": 1.0, "size": "768x432", "aspect": kw["aspect"], "fx": True, "overlay": False,
                "centres": [], "fps": 24, "look": {}, "transitions": []}

    return compose


def _draft_cut(tmp_path, monkeypatch, client) -> Path:
    """A Simple Draft cut rendered through the real Draft loop against the fake ComfyUI, the compose stubbed."""
    monkeypatch.setattr(beatfx, "compose", _fake_compose({}))
    monkeypatch.setattr(S, "usage", lambda: {})
    job = tmp_path / "jobs" / "cut"
    job.mkdir(parents=True)
    state = {"vibe": "cosmic", "aspect": "16:9", "quality_tier": "draft", "energy_preset": "dense", "seed": 4000}
    dense.run_simple({"duration": 12.0, "beats": [i * 0.5 for i in range(24)]}, DEMO, job / "xenoform.mp4", job, {}, state,
                     lambda *a: None, client=client, engine="ltx095")
    return job


def _rec(job: Path) -> dict:
    return json.loads((job / "simple" / "simple.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------------------------- reading a graph


def test_named_reads_the_draft_graph_by_node_class():
    g = json.loads(json.dumps(GRAPH))
    g["3"]["inputs"]["text"] = "a chrome knot melts"
    g["13"]["inputs"]["noise_seed"] = 2733
    g["8"]["inputs"]["img_compression"] = 0
    g["21"]["inputs"]["img_compression"] = 24
    g["22"]["inputs"]["strength"] = 0.8
    g["9"]["inputs"].update({"width": 320, "height": 576, "length": 97})
    got = sr.named(g, ("6", "7"))
    assert got["model"] == "ltx-video-2b-v0.9.5.safetensors" and got["text_encoder"] == "t5xxl_fp8_e4m3fn_scaled.safetensors"
    assert got["prompt"] == "a chrome knot melts" and got["negative"] == g["4"]["inputs"]["text"]
    assert got["seed"] == 2733 and got["steps"] == 20 and got["cfg"] == 3.0 and got["frames"] == 97 and got["fps"] == 24.0
    assert (got["width"], got["height"]) == (320, 576) and got["guide_start"] == 1.0 and got["guide_end"] == 0.8
    assert got["compression"] == [0, 24] and got["lora"] is None and got["sampler"] == "euler"
    with_lora = sr.add_lora(json.loads(json.dumps(g)), "my_style.safetensors", 0.7)
    assert with_lora["20"]["inputs"]["model"] == [sr.LORA_NODE, 0] and with_lora[sr.LORA_NODE]["inputs"]["model"] == ["1", 0]
    assert with_lora["1"]["class_type"] == "CheckpointLoaderSimple" and with_lora["17"]["inputs"]["vae"] == ["1", 2]  # VAE untouched
    assert sr.named(with_lora, ("6", "7"))["lora"] == {"name": "my_style.safetensors", "strength": 0.7}


def test_named_reads_the_final_two_stage_graph_and_the_cloud_graph():
    from xenoform import cloud_final

    fin = final_tier.graph("p", length=73, seed=50, width=448, height=768, out_w=1080, out_h=1920, img_compression=(0, 18),
                           end_strength=0.9, negative="n")
    got = sr.named(fin, ("100", "101"))
    assert got["prompt"] == "p" and got["negative"] == "n" and got["seeds"] == [50, 1050] and got["seed"] == 50
    assert (got["width"], got["height"]) == (448, 768) and got["frames"] == 73 and got["out"] == [1080, 1920]
    assert got["compression"] == [0, 18] and got["guide_end"] == 0.9 and got["cfg"] == 1.0 and len(got["steps_all"]) == 2
    assert got["text_encoder"] == final_tier.TEXT_ENCODER and got["upscaler"] == final_tier.UPSCALER
    cloud = cloud_final.graph("q", length=49, seed=7, width=576, height=1024, img_compression=(30, 0), end_strength=0.6)
    got = sr.named(cloud, ("6", "7"))
    assert got["model"].startswith("ltx-2.5") and got["steps"] == 8 and got["cfg"] == 1.0 and got["compression"] == [30, 0]
    assert got["guide_end"] == 0.6 and (got["width"], got["height"]) == (576, 1024) and got["seed"] == 7


# ---------------------------------------------------------------------------------------------- the Draft loop


def _pair(tmp_path: Path) -> list[dict]:
    from PIL import Image

    out = []
    for k, colour in enumerate(((200, 40, 40), (40, 40, 200), (40, 200, 40))):
        p = tmp_path / f"still{k}.png"
        Image.new("RGB", (64, 36), colour).save(p)
        out.append({"path": str(p), "file": f"cosmic/0{k}_thing.jpg", "noun": f"thing {k}"})
    return out


def test_the_draft_loop_fills_requests_with_the_queued_graph_and_its_time(tmp_path):
    from xenoform.cloud_morph import _local_clips

    stills = _pair(tmp_path)
    shots = [{"seconds": 2.0, "render_s": 2}, {"seconds": 3.0, "render_s": 3}]
    client = Client()
    reqs: list = []
    clips = _local_clips(shots, stills, tmp_path / "w1", {}, 900, "cosmic", client=client, styles=["melt", "shatter"],
                         requests=reqs)
    assert len(clips) == 2 and len(reqs) == 2 and len(client.sent) == 2
    for i, (req, sent) in enumerate(zip(reqs, client.sent)):
        assert req["engine"] == "ltx095" and req["seed"] == 900 + i == sent["13"]["inputs"]["noise_seed"]
        assert req["prompt"] == sent["3"]["inputs"]["text"] and req["negative"] == sent["4"]["inputs"]["text"]
        assert req["frames"] == sent["9"]["inputs"]["length"] == mp.gen_length(shots[i]["render_s"] * 24)
        assert req["steps"] == sent["11"]["inputs"]["steps"] and req["cfg"] == sent["14"]["inputs"]["cfg"]
        assert req["from"]["file"] == stills[i]["file"] and req["to"]["path"] == stills[i + 1]["path"]
        assert req["cached"] is False and req["seconds"] >= 0 and req["style"] == ["melt", "shatter"][i]
        # the record's graph is the one queued, with each still named as its upload names it
        assert {k: v for k, v in req["graph"].items() if k not in ("6", "7")} == {k: v for k, v in sent.items() if k not in ("6", "7")}
        assert req["graph"]["6"]["inputs"]["image"] == sent["6"]["inputs"]["image"] == Path(stills[i]["path"]).name
        # and its key is the morph cache's for that request
        assert req["key"] == mc.key_for(req["graph"], {"6": stills[i]["path"], "7": stills[i + 1]["path"]}, "ltx095")[0]
    assert "shatters" in reqs[1]["prompt"] or "shards" in reqs[1]["prompt"]
    # the same request again: the cache answers, nothing is queued, the record says so
    again: list = []
    _local_clips(shots, stills, tmp_path / "w2", {}, 900, "cosmic", client=client, styles=["melt", "shatter"], requests=again)
    assert len(client.sent) == 2 and [r["cached"] for r in again] == [True, True] and [r["seconds"] for r in again] == [0.0, 0.0]
    assert [r["key"] for r in again] == [r["key"] for r in reqs]
    # no list given: nothing recorded, the loop as before
    assert _local_clips(shots[:1], stills[:2], tmp_path / "w3", {}, 1, "cosmic", client=client) and len(client.sent) == 3


def test_store_keeps_each_graph_once_and_reads_it_back(tmp_path):
    req = {"key": "a" * 64, "graph": {"1": {"class_type": "X", "inputs": {}}}, "seed": 3}
    kept = sr.store(tmp_path, req)
    assert kept["graph"] == f"requests/{'a' * 64}.json" and (tmp_path / kept["graph"]).is_file() and kept["seed"] == 3
    assert sr.graph_of(tmp_path, kept) == req["graph"] and sr.store(tmp_path, kept) == kept
    nokey = sr.store(tmp_path, {"key": None, "graph": {"2": {"class_type": "Y", "inputs": {}}}})
    assert nokey["graph"].startswith("requests/g") and sr.graph_of(tmp_path, nokey) == {"2": {"class_type": "Y", "inputs": {}}}
    assert sr.graph_of(tmp_path, {"graph": "../../etc/passwd"}) is None and sr.store(tmp_path, None) is None


# ---------------------------------------------------------------------------------------------- the cut's record


def test_a_draft_cut_records_every_shots_request_beside_its_clip(tmp_path, monkeypatch):
    client = Client()
    job = _draft_cut(tmp_path, monkeypatch, client)
    rec = _rec(job)
    renders, clips = rec["renders"], rec["clips"]
    assert len(renders) == len(clips) == len(rec["shots"]) and len(client.sent) == len(clips)
    for i, r in enumerate(renders):
        assert r["engine"] == "ltx095" and r["tier"] == "draft" and r["seed"] == 4000 + i and "fallback" not in r
        assert r["graph"] == f"requests/{r['key']}.json"
        graph = sr.graph_of(job / "simple", r)
        assert graph["13"]["inputs"]["noise_seed"] == r["seed"] and graph["3"]["inputs"]["text"] == r["prompt"]
        assert {k: v for k, v in graph.items() if k not in ("6", "7")} == {k: v for k, v in client.sent[i].items() if k not in ("6", "7")}
        assert r["from"]["file"] == rec["stills"][i] and r["to"]["file"] == rec["stills"][i + 1]
        assert r["style"] == rec["morph_styles"][i] and r["render_s"] == rec["plan_shots"][i]["render_s"]
    assert sr.per_shot([{"morph": 1}, {"performer": True}, {"own": True, "morph": 0}, {}], ["a", "b"]) == ["b", None, None, None]


def test_a_rerender_a_swap_and_a_generated_run_keep_the_renders_in_step(tmp_path, monkeypatch):
    client = Client()
    job = _draft_cut(tmp_path, monkeypatch, client)
    before = _rec(job)
    rec = dense.rerender_morph(job, 1, seed=777, cfg={}, client=client)
    assert rec["renders"][1]["seed"] == 777 and rec["renders"][0] == before["renders"][0]
    log = rec["rerenders"][-1]
    assert log["request"] == rec["renders"][1] and log["before"]["clip"] == before["clips"][1]
    assert log["before"]["render"] == before["renders"][1] and log["before"]["style"] == before["morph_styles"][1]
    assert sr.graph_of(job / "simple", rec["renders"][1])["13"]["inputs"]["noise_seed"] == 777
    # a swap: the two morphs that touch the slot get the swapped still's requests
    from xenoform.dense import library_row

    new = next(r["file"] for r in mp.catalogue()["cosmic"] if r["file"] not in rec["stills"])
    assert library_row(new)
    rec = dense.swap_still(job, 2, new, cfg={}, client=client)
    assert rec["renders"][1]["to"]["file"] == new and rec["renders"][2]["from"]["file"] == new
    assert rec["renders"][0] == before["renders"][0] and rec["renders"][1]["seed"] == 4000 + 1  # a swap keeps the cut's seed
    # a generated run: the run's shots carry the run's requests
    rec = dense.insert_generated(job, 0, seconds=3.0, cfg={}, client=client)
    run = rec["inserts"][-1]
    for q in range(run["last"] - run["first"] + 1):
        r = rec["renders"][run["first"] + q]
        assert r["from"]["file"] == run["stills"][q] and r["seed"] == run["seed"] + q
    assert len(rec["renders"]) == len(rec["clips"])


def test_a_final_and_a_cloud_shot_record_their_own_request(tmp_path, monkeypatch):
    from xenoform import cloud_final

    stills = _pair(tmp_path)
    shots = [{"seconds": 2.0, "render_s": 2}]
    client = Client()
    reqs: list = []
    final_tier.final_clips(shots, stills[:2], tmp_path / "fin", {}, 10, "cosmic", client=client, requests=reqs)
    assert reqs[0]["engine"] == "ltx23" and reqs[0]["seeds"] == [10, 1010] and reqs[0]["frames"] == final_tier.gen_length(2)
    assert reqs[0]["graph"]["100"]["inputs"]["image"] == Path(stills[0]["path"]).name and not reqs[0]["cached"]
    sent = client.sent[-1]
    assert {k: v for k, v in reqs[0]["graph"].items() if k not in ("100", "101")} == {k: v for k, v in sent.items() if k not in ("100", "101")}

    class Backend:
        max_parallel = 2

        def prepare(self, graph):
            return graph

        def run(self, graph, out_dir, inputs=None):
            out = Path(out_dir) / "clip.mp4"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b"cloud")
            return [out]

    monkeypatch.setattr(cloud_final, "ready", lambda: {"ready": True, "why": ""})
    creqs: list = []
    cloud_final.cloud_clips(shots, stills[:2], tmp_path / "cl", {}, 20, "cosmic", vertical=False, backend=Backend(), requests=creqs)
    assert creqs[0]["engine"] == "ltx25cloud" and creqs[0]["seed"] == 20 and creqs[0]["guide_end"] == cloud_final.LOOSE["end_strength"]
    assert creqs[0]["prompt"].startswith("The thing 0 slowly") and creqs[0]["cached"] is False


# ---------------------------------------------------------------------------------------------- the recipe routes


def _desk(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from xenoform import ui as ui_mod

    monkeypatch.setattr(ui_mod, "work_dir", lambda: tmp_path)
    return TestClient(ui_mod.create_app())


def _clip_with_graph(path: Path, graph: dict) -> Path:
    """A tiny mp4 carrying a graph in its ``prompt`` tag, as ComfyUI's SaveVideo writes one."""
    import subprocess

    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=64x112:r=24:d=0.5", "-pix_fmt", "yuv420p",
                    "-metadata", f"prompt={json.dumps(graph)}", "-movflags", "use_metadata_tags", str(path)], check=True)
    return path


def test_the_recipe_route_shows_the_used_values_beside_the_preset_and_flags_what_differs(tmp_path, monkeypatch):
    client = Client()
    job = _draft_cut(tmp_path, monkeypatch, client)
    desk = _desk(tmp_path, monkeypatch)
    r = desk.get("/api/jobs/cut/shots/1/recipe")
    assert r.status_code == 200
    got = r.json()
    rec = _rec(job)
    assert got["source"] == "record" and got["recorded"] is True and got["kind"] == "morph" and got["engine"] == "ltx095"
    assert got["used"]["seed"] == 4001 and got["preset"]["seed"] == 4001 and got["preset"]["seed_rule"] == "the cut's seed 4000 + 1"
    assert not any(got["differs"].values()), got["differs"]  # an untouched shot is the preset, field for field
    assert got["used"]["prompt"] == got["preset"]["prompt"] and got["used"]["steps"] == got["preset"]["steps"]
    assert got["rerender"] == {"ok": True, "why": ""} and got["cost"]["gpu_s"] > 0 and got["next_seed"] == 4000 + 1 + 1009
    assert got["workflow"] == "/api/jobs/cut/shots/1/workflow.json" and got["workflow_name"] == "xenoform-cut-shot02.json"
    assert got["choices"]["frames"][0] == 25 and got["choices"]["frames"][-1] == 121 and got["hints"]["cfg"]
    assert got["verified"] is None  # the fake clips carry no graph to check against
    # the workflow: the graph as it was queued, as a file ComfyUI opens
    w = desk.get("/api/jobs/cut/shots/1/workflow.json")
    assert w.status_code == 200 and "attachment" in w.headers["content-disposition"] and "shot02.json" in w.headers["content-disposition"]
    graph = w.json()
    assert graph["13"]["inputs"]["noise_seed"] == 4001 and graph["6"]["_meta"]["title"] == f"Start still: {rec['renders'][1]['from']['noun']}"
    assert {k: v for k, v in graph.items() if k not in ("6", "7")} == {k: v for k, v in client.sent[1].items() if k not in ("6", "7")}
    # another style: its preset prompt
    other = desk.get("/api/jobs/cut/shots/1/recipe?style=shatter").json()
    assert other["preset"]["style"] == "shatter" and other["preset"]["prompt"] != got["preset"]["prompt"] and other["differs"]["prompt"]
    # a re-render with a seed of its own: only the seed differs from the preset
    dense.rerender_morph(job, 1, seed=777, cfg={}, client=client)
    after = desk.get("/api/jobs/cut/shots/1/recipe").json()
    assert after["used"]["seed"] == 777 and [k for k, v in after["differs"].items() if v] == ["seed"]
    assert after["next_seed"] == 4000 + 1 + 2 * 1009
    assert desk.get("/api/jobs/cut/shots/99/recipe").status_code == 400 and desk.get("/api/jobs/nope/shots/0/recipe").status_code == 404
    assert rec["renders"][1]["seed"] == 4001  # the record before the re-render said what the Make sent


def test_a_cut_from_before_the_record_reads_its_clips_graph_or_says_it_was_not_recorded(tmp_path, monkeypatch):
    client = Client()
    job = _draft_cut(tmp_path, monkeypatch, client)
    rec = _rec(job)
    sent = client.sent[2]
    orig = rec["renders"][2]
    graph = json.loads(json.dumps(sent))
    for nid, end in (("6", "from"), ("7", "to")):  # what ComfyUI notes of each LoadImage: the sha256 of the still it read
        graph[nid]["is_changed"] = [mc.sha256_file(orig[end]["path"])]
    clip = _clip_with_graph(job / "simple" / "old02.mp4", graph)
    assert mc.embedded_graph(clip) is not None
    rec["clips"][2] = str(clip)
    rec.pop("renders")
    (job / "simple" / "simple.json").write_text(json.dumps(rec), encoding="utf-8")
    (job / "seed.json").write_text(json.dumps({"seed": 4000, "video_model": "ltx-095", "quality": "turbo"}), encoding="utf-8")
    desk = _desk(tmp_path, monkeypatch)
    got = desk.get("/api/jobs/cut/shots/2/recipe").json()
    assert got["source"] == "clip" and got["recorded"] is False and "Read from the clip itself" in got["note"]
    assert got["used"]["seed"] == 4002 and got["used"]["prompt"] == sent["3"]["inputs"]["text"] and not any(got["differs"].values())
    assert got["used"]["key"] == orig["key"]  # the clip's own graph and still hashes name the request the record had
    w = desk.get("/api/jobs/cut/shots/2/workflow.json").json()
    assert w["13"]["inputs"]["noise_seed"] == 4002 and "is_changed" not in w["6"]
    # a clip that carries nothing: said plainly, the preset and the Seed file's data shown
    nothing = desk.get("/api/jobs/cut/shots/3/recipe").json()
    assert nothing["source"] == "none" and "Not recorded" in nothing["note"] and nothing["used"] == {}
    assert nothing["preset"]["seed"] == 4003 and nothing["seed_file"]["seed"] == 4000 and nothing["rerender"]["ok"] is True
    assert desk.get("/api/jobs/cut/shots/3/workflow.json").status_code == 404


def test_a_final_cut_shows_its_values_and_says_why_it_does_not_re_render(tmp_path, monkeypatch):
    client = Client()
    job = _draft_cut(tmp_path, monkeypatch, client)
    rec = _rec(job)
    for tier, flags, word in (("final", {}, "Final"), ("draft", {"fast": True}, "Fast Final"), ("draft", {"cloud": True}, "Cloud Final")):
        (job / "simple" / "simple.json").write_text(json.dumps({**rec, "tier": tier, **flags}), encoding="utf-8")
        got = _desk(tmp_path, monkeypatch).get("/api/jobs/cut/shots/0/recipe").json()
        assert got["rerender"]["ok"] is False and word in got["rerender"]["why"] and got["used"]["seed"] == 4000
        assert got["tier_label"] == word


# ---------------------------------------------------------------------------------------------- the widened re-render


def test_clean_overrides_takes_the_hand_set_values_and_refuses_plainly():
    got = sr.clean_overrides({"prompt": "  a moth  ", "negative": "", "steps": "24", "cfg": 3.5, "frames": 73, "guide_start": 0.9,
                              "guide_end": "0.6", "compression": 12, "lora": "style.safetensors", "lora_strength": 0.8,
                              "unknown": 1}, loras=["style.safetensors"])
    assert got == {"prompt": "a moth", "negative": "", "steps": 24, "cfg": 3.5, "frames": 73, "guide_start": 0.9, "guide_end": 0.6,
                   "compression": [12, 12], "lora": "style.safetensors", "lora_strength": 0.8}
    assert sr.clean_overrides({"prompt": "", "lora": "none", "compression": [0, 30]}, loras=[]) == {"compression": [0, 30]}
    assert sr.clean_overrides({"lora": "style.safetensors"}, loras=["style.safetensors"])["lora_strength"] == 1.0
    for bad, words in (({"steps": 0}, "steps"), ({"steps": 2.5}, "whole number"), ({"cfg": 50}, "CFG"), ({"frames": 50}, "8k + 1"),
                       ({"frames": 200}, "frames"), ({"guide_end": 1.5}, "last guide"), ({"compression": [1, 2, 3]}, "two"),
                       ({"compression": 101}, "compression"), ({"lora": "x.safetensors"}, "No LoRA called x.safetensors"),
                       ({"prompt": "w" * 3000}, "under 2000"), ({"cfg": "lots"}, "a number")):
        with pytest.raises(ValueError, match=re.escape(words)):
            sr.clean_overrides(bad, loras=["style.safetensors"])


def test_a_rerender_takes_every_value_and_a_lora_and_logs_the_full_request(tmp_path, monkeypatch):
    client = Client()
    job = _draft_cut(tmp_path, monkeypatch, client)
    before = _rec(job)
    monkeypatch.setattr(sr, "lora_files", lambda: ["my_style.safetensors"])
    ov = {"prompt": "a chrome moth folds into a key", "negative": "text, blur", "steps": 12, "cfg": 2.5, "frames": 49,
          "guide_start": 0.9, "guide_end": 0.7, "compression": [5, 25], "lora": "my_style.safetensors", "lora_strength": 0.6}
    rec = dense.rerender_morph(job, 2, seed=123, overrides=ov, timing="beat", cfg={}, client=client)
    sent = client.sent[-1]
    assert sent["3"]["inputs"]["text"] == ov["prompt"] and sent["4"]["inputs"]["text"] == "text, blur"
    assert sent["11"]["inputs"]["steps"] == 12 and sent["14"]["inputs"]["cfg"] == 2.5 and sent["9"]["inputs"]["length"] == 49
    assert sent["10"]["inputs"]["strength"] == 0.9 and sent["22"]["inputs"]["strength"] == 0.7
    assert (sent["8"]["inputs"]["img_compression"], sent["21"]["inputs"]["img_compression"]) == (5, 25)
    assert sent["13"]["inputs"]["noise_seed"] == 123
    assert sent[sr.LORA_NODE]["class_type"] == "LoraLoaderModelOnly" and sent[sr.LORA_NODE]["inputs"]["lora_name"] == "my_style.safetensors"
    assert sent["20"]["inputs"]["model"] == [sr.LORA_NODE, 0]
    r = rec["renders"][2]
    assert r["prompt"] == ov["prompt"] and r["steps"] == 12 and r["frames"] == 49 and r["lora"] == {"name": "my_style.safetensors", "strength": 0.6}
    assert r["key"] != before["renders"][2]["key"]  # another request, another cache key
    assert set(r["overrides"]) == set(ov) | {"seed"} and r["overrides"]["seed"] == 123
    log = rec["rerenders"][-1]
    assert log["overrides"] == r["overrides"] and log["request"] == r and log["timing"] == "beat"
    assert rec["shot_overrides"]["2"]["timing"] == "beat" and rec["plan_shots"][2]["render_s"] == 2
    # the recipe now marks the hand-set rows and what differs from the preset
    desk = _desk(tmp_path, monkeypatch)
    got = desk.get("/api/jobs/cut/shots/2/recipe").json()
    assert set(got["edited"]) == set(ov) | {"seed"}
    assert {k for k, v in got["differs"].items() if v} >= {"prompt", "negative", "steps", "cfg", "frames", "seed", "lora", "compression"}
    # the timing back to the cut's, with the same values: the cache answers, nothing new is queued
    queued = len(client.sent)
    rec = dense.rerender_morph(job, 2, seed=123, overrides=ov, timing="auto", cfg={}, client=client)
    assert len(client.sent) == queued and rec["renders"][2]["cached"] is True and "2" not in (rec.get("shot_overrides") or {})
    with pytest.raises(ValueError, match="morph timing"):
        dense.rerender_morph(job, 2, timing="wobble", cfg={}, client=client)


def test_the_rerender_route_passes_the_new_fields_and_refuses_bad_ones(tmp_path, monkeypatch):
    import threading

    from xenoform import ui as ui_mod

    desk = _desk(tmp_path, monkeypatch)
    folder = tmp_path / "jobs" / "hood"
    (folder / "simple").mkdir(parents=True)
    shots = [{"start": i * 2.0, "end": (i + 1) * 2.0, "seconds": 2.0, "morph": i} for i in range(3)]
    (folder / "simple" / "simple.json").write_text(json.dumps({"plan_shots": shots, "shots": shots, "clips": ["c"] * 3,
                                                                "stills": ["v/0.jpg"] * 4, "tier": "draft"}), encoding="utf-8")
    (folder / "xenoform.mp4").write_bytes(b"old")
    seen = {}
    done = threading.Event()

    def fake(job_dir, shot, **kw):
        seen.update(kw, shot=shot)
        done.set()
        return {"look": {}, "recuts": 1, "rerenders": [{"shot": shot}]}

    monkeypatch.setattr(dense, "rerender_morph", fake)
    try:
        for bad, words in (({"steps": 500}, "steps"), ({"frames": 30}, "8k + 1"), ({"lora": "nope.safetensors"}, "No LoRA"),
                           ({"timing": "wobble"}, "morph timing")):
            r = desk.post("/api/jobs/hood/rerender", json={"shot": 1, **bad})
            assert r.status_code == 400 and words in r.json()["detail"], (bad, r.json())
        r = desk.post("/api/jobs/hood/rerender", json={"shot": 1, "seed": 5, "prompt": "a key", "cfg": 4, "frames": 57,
                                                       "compression": [0, 10], "timing": "snap"})
        assert r.status_code == 200 and r.json()["overrides"] == {"prompt": "a key", "cfg": 4.0, "frames": 57, "compression": [0, 10]}
        assert done.wait(10) and seen["overrides"] == r.json()["overrides"] and seen["timing"] == "snap" and seen["seed"] == 5
    finally:
        with ui_mod._LOCK:
            ui_mod._JOBS.pop("hood", None)


# ---------------------------------------------------------------------------------------------- takes


def _wait_done(desk, job_id: str, version: int) -> dict:
    import time

    for _ in range(100):
        job = desk.get(f"/api/jobs/{job_id}").json()
        if job["status"] == "done" and job.get("video_version", 0) >= version:
            return job
        time.sleep(0.1)
    raise AssertionError(job)


def test_takes_list_every_try_and_an_earlier_one_comes_back_without_a_render(tmp_path, monkeypatch):
    from xenoform import ui as ui_mod

    client = Client()
    job = _draft_cut(tmp_path, monkeypatch, client)
    first = _rec(job)
    dense.rerender_morph(job, 1, seed=777, cfg={}, client=client)
    dense.rerender_morph(job, 1, seed=888, overrides={"steps": 12}, cfg={}, client=client)
    got = sr.takes(job, _rec(job), 1)
    assert [(t["n"], t["source"], t["seed"]) for t in got] == [(0, "make", 4001), (1, "rerender", 777), (2, "rerender", 888)]
    assert [t["current"] for t in got] == [False, False, True] and [t["usable"] for t in got] == [True, True, False]
    assert got[2]["overrides"] == {"steps": 12, "seed": 888} and got[2]["steps"] == 12 and got[0]["clip"] == first["clips"][1]
    desk = _desk(tmp_path, monkeypatch)
    try:
        listed = desk.get("/api/jobs/cut/shots/1/takes").json()
        assert listed["current"] == 2 and [t["n"] for t in listed["takes"]] == [0, 1, 2] and "clip" not in listed["takes"][0]
        clip = desk.get(listed["takes"][0]["url"])
        assert clip.status_code == 200 and clip.content == Path(first["clips"][1]).read_bytes()
        assert desk.post("/api/jobs/cut/shots/1/take", json={"n": 2}).status_code == 400  # playing already
        assert desk.post("/api/jobs/cut/shots/1/take", json={"n": 9}).status_code == 400
        queued = len(client.sent)
        r = desk.post("/api/jobs/cut/shots/1/take", json={"n": 0})
        assert r.status_code == 200 and r.json()["status"] == "running"
        _wait_done(desk, "cut", 1)
        rec = _rec(job)
        assert len(client.sent) == queued  # nothing rendered
        assert rec["clips"][1] == first["clips"][1] and rec["renders"][1] == first["renders"][1] and rec["taken"][-1]["n"] == 0
        assert [t["current"] for t in sr.takes(job, rec, 1)] == [True, False, False]
        recipe = desk.get("/api/jobs/cut/shots/1/recipe").json()
        assert recipe["used"]["seed"] == 4001 and not any(recipe["differs"].values()) and len(recipe["takes"]) == 3
        # a swap on the shot's landing still: the earlier takes morph between other stills now, so they cannot come back
        new = next(r["file"] for r in mp.catalogue()["cosmic"] if r["file"] not in rec["stills"])
        rec = dense.swap_still(job, 2, new, cfg={}, client=client)
        after = sr.takes(job, rec, 1)
        assert after[-1]["current"] and after[-1]["source"] == "swap"
        assert not any(t["usable"] for t in after) and all("before a swap" in t["why"] for t in after[:-1])
    finally:
        with ui_mod._LOCK:
            ui_mod._JOBS.pop("cut", None)


def test_a_rerender_logged_before_the_takes_finds_the_makes_own_clip(tmp_path, monkeypatch):
    client = Client()
    job = _draft_cut(tmp_path, monkeypatch, client)
    rec = dense.rerender_morph(job, 0, seed=55, cfg={}, client=client)
    for r in rec["rerenders"]:
        r.pop("before")  # as an older desk logged it
    (job / "simple" / "simple.json").write_text(json.dumps(rec), encoding="utf-8")
    got = sr.takes(job, rec, 0)
    assert [t["source"] for t in got] == ["make", "rerender"] and Path(got[0]["clip"]).name == "local00.mp4"
    assert got[0]["seed"] == 4000 and got[0]["usable"] is True
    rec = dense.use_take(job, 0, 0, cfg={})
    assert Path(rec["clips"][0]).name == "local00.mp4" and rec["renders"][0] is None  # the Make's request was not kept then


# ---------------------------------------------------------------------------------------------- a shot's Copy recipe


def test_a_recipe_code_carries_shots_own_values_and_old_codes_read_as_before():
    from xenoform import simple_recipe as R

    base = {"vibe": "cosmic", "seed": 4000, "energy_preset": "dense", "aspect": "9:16", "quality_tier": "draft"}
    old = R.encode(base)
    assert "shot_renders" not in R.decode(old)
    own = {"2": {"prompt": "a key folds", "seed": 9, "style": "fold", "steps": 12, "lora": "a.safetensors", "lora_strength": 0.5},
           "x": {"prompt": "junk"}, "3": {"steps": 900}, "4": "nope"}
    code = R.encode({**base, "shot_renders": own})
    back = R.decode(code)
    assert back["shot_renders"] == {"2": {"prompt": "a key folds", "steps": 12, "lora": "a.safetensors", "lora_strength": 0.5,
                                          "seed": 9, "style": "fold"}}  # the damaged entries dropped, as unknown keys are
    assert {k: v for k, v in back.items() if k != "shot_renders"} == R.decode(old)
    out, styles, notes = sr.for_make({"shot_renders": back["shot_renders"]}, 5)
    assert styles == {2: "fold"} and out[2] == {"prompt": "a key folds", "steps": 12, "seed": 9} and out[0] is None
    assert notes == ["shot 3's LoRA a.safetensors is not on this machine: it renders without one"]
    assert sr.for_make({}, 5) == (None, {}, [])


def test_a_draft_make_renders_a_pasted_shots_own_values(tmp_path, monkeypatch):
    client = Client()
    monkeypatch.setattr(beatfx, "compose", _fake_compose({}))
    monkeypatch.setattr(S, "usage", lambda: {})
    job = tmp_path / "jobs" / "own"
    job.mkdir(parents=True)
    state = {"vibe": "cosmic", "aspect": "16:9", "quality_tier": "draft", "energy_preset": "dense", "seed": 4000,
             "shot_renders": {"1": {"prompt": "a key folds into a moth", "seed": 31, "style": "fold", "cfg": 2.0}}}
    dense.run_simple({"duration": 12.0, "beats": [i * 0.5 for i in range(24)]}, DEMO, job / "xenoform.mp4", job, {}, state,
                     lambda *a: None, client=client, engine="ltx095")
    rec = _rec(job)
    assert client.sent[1]["3"]["inputs"]["text"] == "a key folds into a moth" and client.sent[1]["13"]["inputs"]["noise_seed"] == 31
    assert client.sent[1]["14"]["inputs"]["cfg"] == 2.0 and client.sent[0]["13"]["inputs"]["noise_seed"] == 4000
    assert rec["morph_styles"][1] == "fold" and rec["renders"][1]["overrides"] == {"prompt": "a key folds into a moth", "seed": 31, "cfg": 2.0}
    assert {"shot_renders": {"shots": [1]}} in rec["fallbacks"]


def test_the_recipe_route_gives_the_shots_own_recipe_code(tmp_path, monkeypatch):
    from xenoform import simple_recipe as R

    client = Client()
    job = _draft_cut(tmp_path, monkeypatch, client)
    cut_code = R.encode({"vibe": "cosmic", "seed": 4000, "energy_preset": "dense", "aspect": "16:9", "quality_tier": "draft"})
    (job / "meta.json").write_text(json.dumps({"simple": True, "recipe": cut_code}), encoding="utf-8")
    desk = _desk(tmp_path, monkeypatch)
    plain = desk.get("/api/jobs/cut/shots/1/recipe").json()
    assert plain["recipe_code"] == cut_code and plain["recipe_shot"] is False
    dense.rerender_morph(job, 1, seed=55, overrides={"prompt": "a lantern blooms", "steps": 14}, cfg={}, client=client)
    own = desk.get("/api/jobs/cut/shots/1/recipe").json()
    assert own["recipe_shot"] is True and own["recipe_code"] != cut_code
    back = R.decode(own["recipe_code"])
    assert back["shot_renders"] == {"1": {"prompt": "a lantern blooms", "steps": 14, "seed": 55}} and back["seed"] == 4000
    assert desk.post("/api/simple/recipe/encode", json={**R.decode(cut_code), "shot_renders": back["shot_renders"]}).json()["recipe"] \
        == own["recipe_code"]  # the desk's own encode route takes the shots' values too
