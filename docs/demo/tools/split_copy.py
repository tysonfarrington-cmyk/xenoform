"""Split a voice copy at its sentence ends: one row a sentence, read one wav a row, so the voice stops between sentences
(Kokoro runs a line's sentences together). The first sentence keeps the line's id (and its chapter); the rest are
<id>_2, <id>_3 ... A row's "say" is split the same way and must have as many sentences as its text.

    python split_copy.py <voice copy json>          (in place; a row already split is left as it is)
"""
import json
import re
import sys
from pathlib import Path

END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")


def sentences(text):
    return [s.strip() for s in END.split(text.strip()) if s.strip()]


path = Path(sys.argv[1])
copy = json.loads(path.read_text(encoding="utf-8"))
out = []
for row in copy["lines"]:
    if re.search(r"_\d+$", row["id"]):
        out.append(row)
        continue
    texts = sentences(row["text"])
    says = sentences(row["say"]) if row.get("say") else None
    if says is not None and len(says) != len(texts):
        raise SystemExit(f"{row['id']}: say has {len(says)} sentences, text {len(texts)}")
    for k, t in enumerate(texts):
        new = {"id": row["id"] if k == 0 else f"{row['id']}_{k + 1}", "text": t}
        if k == 0 and row.get("chapter"):
            new["chapter"] = row["chapter"]
        if says and says[k] != t:
            new["say"] = says[k]
        out.append(new)
copy["lines"] = out
path.write_text(json.dumps(copy, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
print(path.name, len(out), "rows")
