"""The public docs say what the contest form needs, and say nothing stale."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO_URL = "https://github.com/tysonfarrington-cmyk/xenoform"


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_readme_names_the_models_and_the_repo():
    readme = _read("README.md")
    assert "Wan Animate 2" in readme
    assert REPO_URL in readme
    assert "Python 3.12" in readme
    assert "Comfy SDK" in readme or "comfy-sdk" in readme


def test_readme_has_no_stale_placeholders_or_local_paths():
    readme = _read("README.md")
    assert "PLACEHOLDER" not in readme
    assert "C:\\Projects" not in readme
    assert "LTX-2.5 status" not in readme


def test_readme_keeps_the_demo_video_line_for_the_owner():
    assert "DEMO_VIDEO_URL" in _read("README.md")


def test_every_docs_link_in_readme_resolves():
    readme = _read("README.md")
    links = re.findall(r"\]\((docs/[^)#]+\.md)\)", readme)
    assert links, "README should link into docs/"
    missing = [link for link in links if not (ROOT / link).is_file()]
    assert missing == []


def test_contest_page_carries_the_hashtag_and_deadline():
    contest = _read("docs/CONTEST.md")
    assert "#OpenSourceHiggsfield" in contest
    assert REPO_URL in contest
    assert "Open Weights Only" in contest and "LTX bonus" in contest
    assert "30 October 2026" in contest


def test_license_is_mit():
    text = _read("LICENSE")
    assert text.lstrip().startswith("MIT License")
    assert "Permission is hereby granted, free of charge" in text


def test_credits_have_no_todo_rows():
    assert "TODO" not in _read("CREDITS.md")


def test_licences_page_lists_wan_animate_2():
    licences = _read("docs/LICENCES.md")
    assert "Wan Animate 2" in licences
    assert "moves_wan_animate2.json" in licences
    assert "C:\\Projects" not in licences


def test_mcp_doc_uses_relative_paths_and_the_desk_port():
    mcp = _read("docs/mcp.md")
    assert "C:\\Projects" not in mcp
    assert "127.0.0.1:47317" in mcp
    assert "127.0.0.1:47319/mcp" in mcp


def test_reproduce_page_exists_and_points_at_the_bundled_song():
    page = _read("docs/REPRODUCE.md")
    assert "examples/demo.wav" in page
    assert "media_qa" in page


def test_changelog_has_the_release():
    assert "## 0.3.0" in _read("CHANGELOG.md")
