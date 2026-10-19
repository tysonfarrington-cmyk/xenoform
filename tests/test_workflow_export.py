"""The storyboard downloads as one ComfyUI workflow. Vanilla nodes only."""

from fastapi.testclient import TestClient

from xenoform.eligibility import audit_graph
from xenoform.ui import create_app
from xenoform.workflow_export import latent_length, storyboard_workflow


def test_length_is_a_legal_ltx_count():
    assert latent_length(2.0, 12) % 8 == 1
    assert latent_length(0.1, 12) >= 9


def test_storyboard_is_a_loadable_open_weights_graph():
    graph = storyboard_workflow(
        {
            "seed": 2727,
            "fps": 12,
            "scenes": [
                {"index": 0, "start": 0, "end": 2, "prompt": "the fox holds", "beat": "hold"},
                {"index": 1, "start": 2, "end": 4, "prompt": "the fox hits the drop", "beat": "climax"},
            ],
        }
    )
    assert graph["version"] == 0.4
    assert isinstance(graph["nodes"], list) and isinstance(graph["links"], list)
    kinds = [node["type"] for node in graph["nodes"]]
    assert kinds.count("SaveVideo") == 2
    assert "CLIPLoader" in kinds
    assert "CheckpointLoaderSimple" in kinds
    assert not any("LtxApi" in kind or "GemmaAPI" in kind or "partner" in kind.lower() for kind in kinds)
    prompts = [value for node in graph["nodes"] if node["type"] == "CLIPTextEncode" for value in node["widgets_values"]]
    assert any("fox holds" in str(value) for value in prompts)
    seeds = [node["widgets_values"][0] for node in graph["nodes"] if node["type"] == "RandomNoise"]
    assert 2727 in seeds
    ids = {node["id"] for node in graph["nodes"]}
    for link in graph["links"]:
        assert link[1] in ids and link[3] in ids
    api = {str(node["id"]): {"class_type": node["type"], "inputs": {}} for node in graph["nodes"]}
    assert audit_graph(api, "storyboard") == []


def test_workflow_route_returns_the_graph():
    client = TestClient(create_app())
    response = client.post("/api/workflow", json={"scenes": [{"start": 0, "end": 1, "prompt": "one object"}]})
    assert response.status_code == 200
    body = response.json()
    assert body["version"] == 0.4
    assert body["xenoform"]["shots"] == 1
