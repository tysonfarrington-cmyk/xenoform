"""Under the hood (docs/UI_REVIEW.md 6.4): each shot's morph request is recorded at render time beside its clip
(``simple.json`` ``renders``, the graphs under ``simple/requests/``), for the Draft, the Final and Cloud Final alike, and
kept in step through a re-render, a swap and a generated run (``shot_recipe``)."""
import json
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
