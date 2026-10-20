import json
from pathlib import Path
from xenoform import vibes
def test_twelve_featured_distinct():
    f = [v for v in vibes.every() if v.get("featured", 0) > 0]
    assert len(f) == 12
    assert len({(v["palette"], v["material"]) for v in f}) == 12
    assert sum(1 for v in f if "shell" in (v.get("look", "") + v.get("still_style", "")).lower()) <= 1
    root = Path(vibes.REGISTRY).parents[1] / "src/xenoform/ui_static/vibes"
    assert all((root / f"{v['id']}.jpg").is_file() for v in f)
