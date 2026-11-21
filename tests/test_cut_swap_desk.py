"""What the desk says of an edit whose swap failed (``xenoform.cut_swap``; docs/notes/review-21nov.md, "The failed
swap, fixed"): the job is an error with the reason and ``cut_as_it_was``, and app.js adds "The cut is as it was." only
when the job says the cut is. Before, the line was added to every failed edit, over a cut that could be part new.

The swap is failed as tests/test_cut_swap.py fails it (``_FailAt``: a full disk at the k-th file put in place)."""
from __future__ import annotations

from xenoform import cut_swap

from test_cut_swap import FULL, REAL_PUT, _beside, _FailAt, _layer_state
from test_r0_fixes import NODE, _poll_code, _run
from test_stems_mode import fake_render, stems_dir  # noqa: F401  (fixtures)
from test_stems_stop import JOB, KNOBS, _settle, _state, desk  # noqa: F401  (fixtures)


def test_the_desk_reports_a_stems_recut_whose_swap_failed_with_the_cut_as_it_was(desk, monkeypatch):
    client, job = desk
    before = _state(job)
    _FailAt(monkeypatch, 3)
    assert client.post(f"/api/jobs/{JOB}/recut", json=KNOBS).status_code == 200
    j = _settle(client)
    assert j["status"] == "error" and j["cut_as_it_was"] is True and j["error"] == j["detail"]
    assert j["detail"] == f"The re-cut was made but could not be put in the cut's place ({FULL}). Every file and record was put back."
    assert j["edit"] == "recut" and j["video_version"] == j["edit_from"] == 0  # no new version
    assert _state(job) == before and _beside(job) == []
    monkeypatch.setattr(cut_swap, "_put", REAL_PUT)  # and the cut takes the next edit, which lands
    assert client.post(f"/api/jobs/{JOB}/recut", json=KNOBS).status_code == 200
    j = _settle(client)
    assert j["status"] == "done" and j["video_version"] == 1 and j["cut_as_it_was"] is None and j["error"] is None


def test_the_desk_does_not_say_as_it_was_over_a_stems_cut_that_could_not_be_put_back(desk, monkeypatch):
    client, job = desk
    other = job / "layers" / "other" / "xenoform.mp4"
    _FailAt(monkeypatch, 5, never_back=[other])
    assert client.post(f"/api/jobs/{JOB}/recut", json=KNOBS).status_code == 200
    j = _settle(client)
    assert j["status"] == "error" and j["cut_as_it_was"] is False and j["video_version"] == 0
    assert "part old and part new: layers/other/xenoform.mp4 could not be restored" in j["error"]
    assert "as it was" not in j["error"] and "was put back" not in j["error"]
    assert cut_swap.beside(other, cut_swap.WAS).is_file()


def test_the_desk_reports_lay_them_again_whose_swap_failed_with_the_cut_as_it_was(desk, monkeypatch):
    client, job = desk
    before = _state(job)
    _FailAt(monkeypatch, 2)  # the composite is in place, the record will not be written
    assert client.post(f"/api/jobs/{JOB}/composite", json={"prominence": {"other": 1.0}}).status_code == 200
    j = _settle(client)
    assert j["status"] == "error" and j["cut_as_it_was"] is True and j["video_version"] == j["edit_from"] == 0
    assert j["detail"] == f"The new composite was made but could not be put in the cut's place ({FULL}). Every file and record was put back."
    assert _state(job) == before and _beside(job) == []
    monkeypatch.setattr(cut_swap, "_put", REAL_PUT)
    assert client.post(f"/api/jobs/{JOB}/composite", json={"prominence": {"other": 1.0}}).status_code == 200
    j = _settle(client)
    assert j["status"] == "done" and j["detail"] == "Laid together again" and j["cut_as_it_was"] is None


def test_the_desk_reports_a_plain_recut_whose_swap_failed_with_the_cut_as_it_was(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from test_swap import _cut
    from xenoform import ui

    job = _cut(tmp_path, monkeypatch, {})
    before = _layer_state(job)
    monkeypatch.setattr(ui, "work_dir", lambda: tmp_path)
    client = TestClient(ui.create_app())
    try:
        _FailAt(monkeypatch, 2)  # the file is in place, the record will not be written
        assert client.post("/api/jobs/cut/recut", json={"macros": {"chaos": 0.2}}).status_code == 200
        j = {}
        for _ in range(1500):
            j = client.get("/api/jobs/cut").json()
            if j["status"] != "running":
                break
            import time

            time.sleep(0.02)
        assert j["status"] == "error" and j["cut_as_it_was"] is True and j["video_version"] == 0
        assert j["detail"] == f"The re-cut was made but could not be put in the cut's place ({FULL}). Every file and record was put back."
        assert _layer_state(job) == before and _beside(job) == []
    finally:
        with ui._LOCK:
            ui._JOBS.pop("cut", None)
            ui._CANCEL.pop("cut", None)


@NODE
def test_the_desk_adds_as_it_was_only_when_the_job_says_the_cut_is(tmp_path):
    """app.js added "The cut is as it was." to every failed edit. A job whose cut could not be put back says so
    (``cut_as_it_was`` false) and the line is left off; an older desk's job, which has no such field, keeps it."""
    code = _poll_code(r"""
const fresh = () => ({ job: { id: "c1", status: "running" }, lane: { id: "c1" }, easy: { phase: "making", note: "", recutting: true,
  making: { kind: "gpu", title: "Re-cutting" }, startedAt: Date.now() - 36000, reopenId: "", reopenUrl: "" } });
const ends = async (job) => { state = fresh(); answers = [reply(200, Object.assign({ id: "c1", status: "error", video_version: 1, edit_from: 1 }, job))];
  await poll("c1"); return { note: state.easy.note, phase: state.easy.phase, cut: easyVideoId() }; };
(async () => {
  const out = {};
  out.back = await ends({ cut_as_it_was: true, error: "The re-cut was made but could not be put in the cut's place (No space left on device). Every file and record was put back." });
  out.part = await ends({ cut_as_it_was: false, error: "The re-cut was made but could not be put in the cut's place (No space left on device), and putting the cut back failed too. The cut is part old and part new: layers/other/xenoform.mp4 could not be restored." });
  out.older = await ends({ error: "Re-cut did not run. The song file is gone." });
  console.log(JSON.stringify(out));
})();
""")
    got = _run(tmp_path, code)
    assert got["back"]["note"].endswith("Every file and record was put back. The cut is as it was.")
    assert got["part"]["note"].endswith("layers/other/xenoform.mp4 could not be restored.") and "as it was" not in got["part"]["note"]
    assert got["older"]["note"] == "Re-cut did not run. The song file is gone. The cut is as it was."
    assert all(got[k]["phase"] == "result" and got[k]["cut"] == "c1" for k in got)  # the cut stays open either way
