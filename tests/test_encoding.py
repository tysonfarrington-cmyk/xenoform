"""No double-encoded text in the source (26 Oct): "·" had been saved as "Â·" and "×" as "Ã—" (UTF-8 read as Windows-1252
and saved again), so the making screen read "9 Draft (LTX 0.9.5) morphs Â· 9 shots". This fails on any such sequence."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# a lead byte of a two- or three-byte UTF-8 character read as cp1252 (Â, Ã, â), followed by what its continuation bytes
# become in cp1252 (the 0x80-0xBF block and the curly quotes, dashes, bullets and symbols cp1252 puts there)
MOJIBAKE = re.compile(
    "[ÂÃâ][\u0080-¿–—‘’‚“”„†‡•…"
    "‰‹›€™ŒœŠšŸŽžƒˆ˜]"
)


def test_no_double_encoded_text_in_the_source():
    hits = []
    for folder in ("src", "configs"):
        for path in (ROOT / folder).rglob("*"):
            if path.suffix not in {".py", ".js", ".json", ".html", ".css", ".md"} or "__pycache__" in path.parts:
                continue
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if MOJIBAKE.search(line):
                    hits.append(f"{path.relative_to(ROOT)}:{n}")
    assert not hits, hits
