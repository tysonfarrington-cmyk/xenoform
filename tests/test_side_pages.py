"""The side pages share one shell (docs/UI_REVIEW.md S1, S2, M6).

Judges, Variations, Moves, Licences and Credits wear the same header (the desk's brand, the page's name, the Open
weights badge, one way back), load the same four stylesheets, and sit in the same column. The judges prompt is
readable on its black screen and its slider takes the accent. Moves shows a picture per clip, keeps the source credit
behind a button, has a file picker the keyboard reaches, and says what enables Render. No GPU."""

from __future__ import annotations

import os
import re
import shutil
import struct
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from xenoform import moves as mv
from xenoform import ui as ui_mod
from xenoform.ui import create_app

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "xenoform" / "ui_static"
PAGES = {"/judges": "Judges", "/variations": "Variations", "/moves": "Moves", "/licences": "Licences", "/credits": "Credits"}
HOSTILE = '"><script>alert(1)</script>'
HEADER = re.compile(r'<header class="top side-top">.*?</header>', re.S)
INDEX = (STATIC / "index.html").read_text(encoding="utf-8")
SIDE = (STATIC / "side.css").read_text(encoding="utf-8")
JUDGES = (STATIC / "judges.html").read_text(encoding="utf-8")
MOVES = (STATIC / "moves.html").read_text(encoding="utf-8")
VARIATIONS = (STATIC / "variations.html").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def client():
    return TestClient(create_app())


def _header(text: str) -> str:
    found = HEADER.findall(text)
    assert len(found) == 1, "one header, not " + str(len(found))
    return found[0]


def _same_but_for_the_name(header: str, name: str) -> str:
    return header.replace(f'<p class="side-title">{name}</p>', '<p class="side-title">NAME</p>').replace(' aria-current="page"', "")


# ---------------------------------------------------------------- S1: one header, one back control, one stylesheet set

@pytest.mark.parametrize("path,name", PAGES.items())
def test_every_side_page_has_one_header_one_back_control_and_the_desk_stylesheets(client, path, name):
    response = client.get(path)
    assert response.status_code == 200, path
    text = response.text
    header = _header(text)
    assert text.count('class="top side-top"') == 1 and '<header class="top">' not in text
    assert f'<p class="side-title">{name}</p>' in header
    # the way back: one, the last thing in the header, the same words and class on every page
    assert text.count("Back to the desk") == 1 and text.count('class="ghost side-back"') == 1
    assert header.rstrip().endswith('<a class="ghost side-back" href="/">&larr; Back to the desk</a>\n</header>')
    # the order the keyboard walks: the brand, the page's badge, then the way back, all before the page
    assert header.index('class="brand"') < header.index('class="ow-badge"') < header.index('class="ghost side-back"')
    assert text.index("</header>") < text.index("<main")
    # theme, app, desk, side: in that order, and the desk's body hook
    order = [text.index(sheet) for sheet in ("theme.css", "app.css", "desk.css", "side.css")]
    assert order == sorted(order) and len(set(order)) == 4
    assert '<body data-desk="1"' in text and 'name="viewport"' in text
    assert '<main class="' in text and "side-page" in text.split("<main", 1)[1].split(">", 1)[0]


def test_the_five_headers_are_one_header_but_for_the_name(client):
    headers = {path: _same_but_for_the_name(_header(client.get(path).text), name) for path, name in PAGES.items()}
    assert len(set(headers.values())) == 1, headers
    # the brand is the desk's own (index.html), the badge says what the desk's badge says
    desk_brand = re.search(r'<a class="brand" href="#simple">(.*?)</a>', INDEX, re.S).group(1)
    desk_brand = re.sub(r">\s+<", "><", desk_brand.strip())
    badge_title = re.search(r'class="ow-badge" href="/licences" title="([^"]+)"', INDEX).group(1)
    one = next(iter(headers.values()))
    assert f'<a class="brand" href="/">{desk_brand}</a>' in one
    assert f'<a class="ow-badge" href="/licences" title="{badge_title}">Open weights</a>' in one


def test_licences_marks_its_own_badge_as_the_current_page(client):
    assert 'aria-current="page"' in _header(client.get("/licences").text)
    for path in ("/judges", "/variations", "/moves", "/credits"):
        assert "aria-current" not in _header(client.get(path).text), path


def test_no_page_keeps_the_old_headers_or_back_links(client):
    for path in PAGES:
        text = client.get(path).text
        assert '<p><a href="/">' not in text, path  # the blue text link of Variations and Moves
        assert '<nav class="views"' not in text and ">Desk</a>" not in text, path  # the judges' slim header
        assert '<a class="brand" href="/"><strong>Xenoform</strong></a>' not in text, path  # the orange wordmark of the doc pages
        assert "judges-foot" not in text, path
    for path in ("/licences", "/credits"):
        text = client.get(path).text
        assert "desk.css" in text and "side.css" in text
        assert '<main class="side-page">' in text and '<article class="panel doc">' in text


def test_the_sources_of_the_pages_hold_no_header_of_their_own():
    for name, page in (("judges", JUDGES), ("moves", MOVES), ("variations", VARIATIONS)):
        assert page.count("<!--side-header-->") == 1, name
        assert "<header" not in page and "Back to the desk" not in page, name
        assert 'href="desk.css"' in page and 'href="side.css"' in page and '<body data-desk="1">' in page, name
        assert page.index('href="desk.css"') < page.index('href="side.css"'), name


@pytest.mark.parametrize("path,name", PAGES.items())
def test_the_desk_base_path_is_honoured_and_escaped_on_every_side_page(client, path, name):
    proxied = client.get(path, headers={"x-xeno-base": "/xenoform"})
    assert proxied.status_code == 200
    text = proxied.text
    header = _header(text)
    assert 'class="brand" href="/xenoform/"' in header and 'href="/xenoform/">&larr; Back to the desk' in header
    assert 'class="ow-badge" href="/xenoform/licences"' in header
    assert 'data-base="/xenoform"' in text
    assert "/xenoform/static/" in text  # the stylesheets: a <base> for the pages of ui_static, the hrefs of the doc pages
    assert 'href="/static/' not in text and 'href="/licences"' not in text and 'href="/credits"' not in text
    hostile = client.get(path, headers={"x-xeno-base": HOSTILE})
    assert hostile.status_code == 200
    assert HOSTILE not in hostile.text and "<script>alert" not in hostile.text
    assert 'data-base=""' in hostile.text and 'class="brand" href="/"' in hostile.text
    for good in ("/static/theme.css", "/static/side.css") if path in ("/licences", "/credits") else ('<base href="/static/">',):
        assert good in hostile.text


def test_the_pages_with_scripts_reach_their_api_under_the_base_path():
    assert 'document.body.dataset.base' in MOVES and 'fetch(api("/api/moves"))' in MOVES
    assert 'fetch(api("/api/moves/render")' in MOVES and "api(`/api/moves/jobs/${id}`)" in MOVES and "api(job.url)" in MOVES
    assert 'document.body.dataset.base' in VARIATIONS and 'fetch(api("/api/batches"))' in VARIATIONS
    assert "fetch(api(path)" in VARIATIONS and "api(it.video)" in VARIATIONS and "api(it.poster)" in VARIATIONS


def test_tables_of_the_doc_pages_scroll_inside_their_own_box(client):
    text = client.get("/licences").text
    assert text.count('<div class="doc-scroll"><table>') == text.count("</table></div>") >= 3
    assert "<table>" not in text.replace('<div class="doc-scroll"><table>', "")
    assert ".doc-scroll { margin: 8px 0 16px; overflow-x: auto; }" in SIDE
    assert re.search(r"@media \(max-width: 640px\) \{[^@]*\.top\.side-top \.ow-badge \{ display: none; \}", SIDE)


def test_side_css_is_tokens_and_no_important():
    rules = re.sub(r"/\*.*?\*/", "", SIDE, flags=re.S)
    assert "!important" not in rules
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", rules), "a colour that is not a token"
    names = re.findall(r"var\((--[\w-]+)", rules)
    assert names and all(name.startswith("--x-") for name in names), sorted(set(names))
    assert "@media (max-width: 640px)" in rules and ".side-top .side-title" in rules and "text-overflow: ellipsis" in rules


# ---------------------------------------------------------------- S2: the judges prompt and slider

def test_the_judges_prompt_is_readable_and_the_slider_takes_the_accent():
    style = JUDGES.split("<style>", 1)[1].split("</style>", 1)[0]
    prompt = re.search(r"\.screen \.empty, \.screen \.status \{([^}]*)\}", style).group(1)
    assert "color: var(--x-text-2);" in prompt and "zinc" not in prompt
    slider = re.search(r"\.energy input, \.energy #energy \{([^}]*)\}", style).group(1)
    assert "accent-color: var(--x-accent);" in slider
    # the old names that read dark on dark are gone from the page's own rules
    for old in ("var(--zinc-50)", "var(--zinc-500)", "var(--ink)", "var(--nightshade)", "var(--muted)"):
        assert old not in style, old
    assert "#drop.over" in style and ".drop.over" not in style  # judges.js puts .over on #drop: the outline shows
    assert 'href="/licences"' in JUDGES and 'href="/credits"' in JUDGES  # the foot keeps both links


# ---------------------------------------------------------------- M6: Moves

def test_the_moves_page_says_what_it_waits_for_and_hides_the_credit_behind_a_button():
    page = MOVES
    # a styled file control: a label that is the .upload component, the input inside it, no bare native input
    assert re.search(r'<label class="upload">Choose a character picture<input type="file" id="img" accept="image/png,image/jpeg,image/webp"></label>', page)
    assert page.count('type="file"') == 1
    assert 'id="img-name"' in page and 'id="img-thumb"' in page and "URL.createObjectURL" in page
    # Render stays, disabled, with the line beside it and every state's words
    assert re.search(r'<button type="button" id="go" class="generate" disabled aria-describedby="why">Render this move</button>', page)
    for words in ("Choose a character picture first", "Pick a move", "This move is not downloaded yet: run <code>python scripts/fetch_moves.py ${esc(m.id)}</code>",
                  "Ready: renders on this machine, about ${st.seconds.toFixed(1)} s of video"):
        assert words in page, words
    assert "if (!m.local)" in page and "$(\"go\").disabled = !w.ok" in page  # a move that is not downloaded keeps Render off
    # the credit sits behind a real button; the card face never prints the attribution or a raw URL
    assert 'class="move-info" aria-expanded="false" aria-controls="src-${id}"' in page and "View the original clip" in page
    assert "attribution" not in page and "m.download" not in page
    assert 'target="_blank" rel="noopener noreferrer"' in page and "m.licence_short" in page and "m.category_name" in page
    card = page.split("function card(m) {", 1)[1].split("// What the Render button waits for", 1)[0]
    face = card.split("return `", 1)[1].split('<div class="move-source"', 1)[0]
    assert "source_url" not in face and "m.author" not in face and "m.fit_note" not in face and "m.licence" not in face
    # every id and endpoint the page used before
    for kept in ('id="moves"', 'id="look"', 'id="go"', 'id="status"', 'id="out"', "/api/moves", "/api/moves/render", "/api/moves/jobs/", "FormData"):
        assert kept in page, kept


def test_moves_rows_carry_plain_words_and_a_short_licence():
    rows = mv.moves(include_avoid=True)
    assert len(rows) == 15
    assert {r["licence_short"] for r in rows} == {"Pexels licence", "Mixkit licence"}
    assert all(r["category_name"][:1].isupper() and r["category_name"] != r["category"] for r in rows)
    assert mv.category_name("dance-hiphop") == "Hip-hop dance" and mv.category_name("walk-to-camera") == "Walk to camera"
    assert mv.category_name("dance-new-thing") == "Dance new thing" and mv.licence_name({"licence": "CC0 (public domain)"}) == "CC0"
    assert mv.licence_name({}) == "Licence not recorded"


def _tiny_clip(dest: Path, seconds: int = 3) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=10", "-t", str(seconds),
                    "-c:v", "mpeg4", "-pix_fmt", "yuv420p", str(dest)], check=True)


def _jpeg_size(data: bytes) -> tuple[int, int]:
    assert data[:2] == b"\xff\xd8", "not a jpeg"
    at = 2
    while at < len(data):
        assert data[at] == 0xFF
        marker = data[at + 1]
        if marker in (0xC0, 0xC1, 0xC2):
            height, width = struct.unpack(">HH", data[at + 5:at + 9])
            return width, height
        at += 2 + struct.unpack(">H", data[at + 2:at + 4])[0]
    raise AssertionError("no frame header")


@pytest.fixture()
def moves_desk(tmp_path, monkeypatch):
    library = tmp_path / "library"
    monkeypatch.setattr(mv, "LIBRARY", library)
    monkeypatch.setattr(ui_mod, "work_dir", lambda: tmp_path)
    return TestClient(create_app()), library, tmp_path


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is not installed")
def test_the_thumb_route_answers_one_cropped_frame_for_a_local_clip_and_404_for_the_rest(moves_desk):
    client, library, tmp_path = moves_desk
    _tiny_clip(library / "px_8688817.mp4")
    got = client.get("/api/moves/px_8688817/thumb.jpg")
    assert got.status_code == 200 and got.headers["content-type"] == "image/jpeg"
    assert got.headers["cache-control"] == "no-cache"
    assert _jpeg_size(got.content) == (mv.THUMB_W, mv.THUMB_H) == (240, 416)  # a landscape clip, cropped to the 9:16 the model gets
    assert (tmp_path / "moves" / "thumbs" / "px_8688817.jpg").is_file()
    assert client.get("/api/moves/px_8377696/thumb.jpg").status_code == 404  # in the manifest, not downloaded
    assert client.get("/api/moves/nope/thumb.jpg").status_code == 404  # not a move
    assert client.get("/api/moves/..%2f..%2fconfigs/thumb.jpg").status_code == 404
    # the list names a thumb for the clip that is here and for no other
    rows = {m["id"]: m for m in client.get("/api/moves").json()["moves"]}
    assert rows["px_8688817"]["local"] is True and rows["px_8688817"]["thumb"] == "/api/moves/px_8688817/thumb.jpg"
    assert all("thumb" not in m and m["local"] is False for key, m in rows.items() if key != "px_8688817")
    assert client.get("/api/moves").json()["fps"] == mv.FPS == 24


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is not installed")
def test_the_thumb_is_made_once_and_again_when_the_clip_is_newer(moves_desk):
    client, library, tmp_path = moves_desk
    clip = library / "px_8688817.mp4"
    _tiny_clip(clip)
    assert client.get("/api/moves/px_8688817/thumb.jpg").status_code == 200
    cached = tmp_path / "moves" / "thumbs" / "px_8688817.jpg"
    old = cached.stat().st_mtime - 1000
    os.utime(cached, (old, old))
    os.utime(clip, (old - 5, old - 5))  # the clip is older than its picture: the picture stands
    assert client.get("/api/moves/px_8688817/thumb.jpg").status_code == 200
    assert cached.stat().st_mtime == pytest.approx(old, abs=1)
    os.utime(clip, (old + 500, old + 500))  # a newer clip: a new picture
    assert client.get("/api/moves/px_8688817/thumb.jpg").status_code == 200
    assert cached.stat().st_mtime > old + 100
    assert [p.name for p in cached.parent.iterdir()] == ["px_8688817.jpg"]  # no part file left behind


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is not installed")
def test_a_clip_that_is_not_a_video_gives_404_not_a_server_error(moves_desk):
    client, library, tmp_path = moves_desk
    library.mkdir(parents=True)
    (library / "px_8688817.mp4").write_bytes(b"not a video at all")
    assert client.get("/api/moves/px_8688817/thumb.jpg").status_code == 404
    assert not list((tmp_path / "moves" / "thumbs").glob("*"))


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is not installed")
def test_a_newer_clip_that_cannot_be_read_leaves_the_picture_there_was(moves_desk):
    client, library, tmp_path = moves_desk
    clip = library / "px_8688817.mp4"
    _tiny_clip(clip)
    first = client.get("/api/moves/px_8688817/thumb.jpg")
    assert first.status_code == 200
    clip.write_bytes(b"damaged")
    later = clip.stat().st_mtime + 100
    os.utime(clip, (later, later))
    again = client.get("/api/moves/px_8688817/thumb.jpg")
    assert again.status_code == 200 and again.content == first.content
    assert [p.name for p in (tmp_path / "moves" / "thumbs").iterdir()] == ["px_8688817.jpg"]


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is not installed")
def test_a_clip_shorter_than_the_seek_still_gets_its_first_frame(moves_desk):
    client, library, _ = moves_desk
    _tiny_clip(library / "px_8688817.mp4", seconds=1)  # the manifest's quarter of 13.56 s is 1.5 s: past the end
    assert client.get("/api/moves/px_8688817/thumb.jpg").status_code == 200


def test_the_moves_list_without_clips_has_no_thumbs_and_the_page_serves(moves_desk):
    client, _, _ = moves_desk
    data = client.get("/api/moves").json()
    assert data["moves"][0]["id"] == "px_8688817" and not any("thumb" in m for m in data["moves"])
    assert all(m["local"] is False for m in data["moves"])
    assert client.get("/moves").status_code == 200
    assert client.post("/api/moves/render", data={"move": "px_8688817"}).status_code == 400
