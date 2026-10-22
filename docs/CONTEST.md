# #OpenSourceHiggsfield submission checklist

Contest: [Open Source Higgsfield](https://comfy.org/open-source-higgsfield/), run by Comfy. Entries are judged on the public repo and a demo video under two minutes; judges may not run the code.

**Deadline: Friday 30 October 2026, 9:00 am Pacific = Saturday 31 October 2026, 3:00 am AEDT.** Treat Friday evening AEDT as the real cut-off.

## Categories claimed

- **Open Weights Only.** Every default render uses open weights on the user's own GPU: LTX-Video 0.9.5, LTX-2.3 22B distilled fp8, Z-Image Turbo, Wan Animate 2, Real-ESRGAN x4plus. The paid paths (LTX-2.5 partner node, Comfy Cloud, the Add-ons switch) are off by default and collapsed into one section of the README. `tests/test_eligibility.py` fails the build if a default workflow names a partner or API node.
- **LTX bonus.** LTX-2.3 is the core video model for Final, action shots and scene morphs; LTX-Video 0.9.5 renders every Draft morph. Prompts are encoded locally; no LTX API key.

## ComfyUI parts used

- **Comfy Python SDK** (`comfy-sdk` 0.5.0): every render is submitted with `workflows.from_file`, `assets.from_file`, `set_input`, `submit`, `events`, `result`, `get_outputs`, through `comfy-api-proxy` 0.1.6 in front of a local ComfyUI.
- **MCP**: a native MCP server with 45 tools (`python -m xenoform.mcp`, stdio and streamable HTTP on `127.0.0.1:47319/mcp`) so any AI client can direct the app.
- Core ComfyUI nodes only in the shipped graphs (LTX, Wan Animate 2, Z-Image, upscalers); an optional node pack entry (`__init__.py`, `web/`) for the Try It and Setup Check nodes.

## Checklist

- [ ] Public repo at https://github.com/tysonfarrington-cmyk/xenoform (the owner pushes; nothing is pushed by an agent).
- [ ] `LICENSE` is MIT (code). Model, font and picture licences in `docs/LICENCES.md`; picture credits in `CREDITS.md` with no TODO rows.
- [ ] README states "100% open weights by default, all local, built on the Comfy SDK" near the top, with the model and licence table.
- [ ] README has setup instructions (Quick start, Python 3.12, `Xenoform.bat` / `install.sh`) and a judge path with no GPU.
- [ ] `docs/REPRODUCE.md` reproduces the demo in about ten minutes.
- [ ] Demo video under 2:00, 9:16, with the repo URL burned into the end card (the app does this when End card is on: `github.com/tysonfarrington-cmyk/xenoform` from `pyproject.toml`). Upload it, then replace `DEMO_VIDEO_URL` in README.md (top block), this page and the social post.
- [ ] Demo song: "Morph Engine v2", made by the author on Suno Pro inside the billing period (commercial rights per Suno's terms). Not shipped; the repo uses `examples/demo.wav`.
- [ ] `pytest tests/test_docs.py tests/test_install.py tests/test_eligibility.py` passes on the pushed commit; CI (`.github/workflows/ci.yml`, Python 3.12) is green.
- [ ] Public post with **#OpenSourceHiggsfield** on one of X, Reddit, Instagram, LinkedIn, YouTube or TikTok, with the video and the repo link (draft below). Keep the post URL for the form.
- [ ] Typeform submitted with the fields below.

## Typeform fields (draft answers)

| Field | Answer |
| --- | --- |
| Project name | Xenoform |
| One-line description (100 characters) | `Song in, music video out: open-weights LTX morphs on every beat, stems, MIDI, MCP. Comfy SDK.` (93 characters) |
| Repo URL | https://github.com/tysonfarrington-cmyk/xenoform |
| Demo video URL | DEMO_VIDEO_URL |
| Social post URL | (the #OpenSourceHiggsfield post) |
| Categories | Open Weights Only; LTX bonus |
| ComfyUI parts used | Comfy Python SDK (comfy-sdk 0.5.0 + comfy-api-proxy); MCP server (45 tools); core nodes only in the shipped workflows |
| Models | LTX-Video 0.9.5, LTX-2.3 22B distilled fp8, Z-Image Turbo, Wan Animate 2, Real-ESRGAN x4plus (optional: FLUX.2 Klein 4B, ACE-Step 1.5) |
| Licence | MIT |
| Runs on | Windows and Linux, Python 3.12, ComfyUI 0.33+, a 12 GB GPU for renders; the animatic and the judges page need no GPU |

## Social post (draft, under 280 characters)

```
Xenoform: drop in a song, pick a vibe, and one object morphs into the next on every beat. Open weights (LTX-Video, LTX-2.3), all local, built on the Comfy SDK, with stems, MIDI and an MCP server. #OpenSourceHiggsfield
https://github.com/tysonfarrington-cmyk/xenoform
DEMO_VIDEO_URL
```

That is 265 characters with both links counted at X's 23 each; a shortened video link in place of `DEMO_VIDEO_URL` keeps it there. If it runs long, drop "with stems, MIDI and an MCP server".

## After submitting

- Keep the repo and the video public until judging ends.
- Do not force-push over the submitted commit; add commits instead.
- The demo video's end card already carries the repo URL, so a re-render is not needed if the README changes.
