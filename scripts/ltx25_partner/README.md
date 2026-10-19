# LTX-2.5 partner renders (PAID Add-on, not the default path)

`workflows/ltx25_partner_flf_api.json` uses LoadImage A and LoadImage B, feeds them into
`LtxApi25ImageToVideo` (image plus last_frame), then SaveVideo. The node runs on Lightricks'
servers and bills Comfy credits. It isn't part of `eligibility.DEFAULT_WORKFLOWS` and
stays outside the open-weights default path.

- `render.py`: dry run by default. It validates the graph locally against `/object_info`
  (GET only), checks the stills and prints the exact cost from the node's own price table.
  `--confirm` submits one entry through comfy-sdk to comfy-api-proxy (:8189). It needs
  a Comfy API key in `$COMFY_ORG_API_KEY`, sent as `extra_data.api_key_comfy_org`.
  A browser sign-in doesn't apply to API or SDK submits. It refuses `--all --confirm`
  and anything over `--max-usd` (default US$1.10). Every paid run is appended to
  `judge_logs/ltx25_partner/ledger.jsonl`.
- `preview.py`: FREE previews of the same pairs with the local LTX 0.9.5 morph graph.
  It refuses any graph containing a partner or API node.
- `shortlist.json`: the 10 candidate pairs (stills from `src/xenoform/ui_static/objects`).

Prices (Comfy partner pricing, 211 credits = US$1): Fast 720p US$0.1287/s and Pro 720p
US$0.1716/s. Fast allows 2 to 20s and Pro allows 2 to 10s.

## Simple mode: Cloud quality (off by default)

`src/xenoform/cloud_morph.py` wires this node into Simple mode behind a "Cloud quality" toggle.

- Pick a song and the **black** vibe, then switch on **Cloud quality** (and optionally **Beat overlay**). Press Make.
- The desk calls `POST /api/cloud/estimate`, which is read-only. It plans beat-aligned shots of about 5s each, rendered as Fast 720p 24fps with durations snapped to 2/3/4/5/6/8/10. It chains the stills A->B->C and shows credits, US$ and A$.
- Nothing is paid until you click **Confirm and render**. The click carries a single-use HMAC token that expires after 30 minutes and must cover the cost.
- Each clip is capped at US$5. Override the cap with `XENO_CLOUD_CAP_USD`.
- A 20s clip is 4 x 5s Fast 720p = US$2.574, about 543 credits, about A$3.71.
- A free local LTX 0.9.5 draft of the same chain renders and plays first. Then all partner shots go out in ONE prompt, so ComfyUI runs them in parallel. They are stitched on the beat grid, the song is muxed in, and the cut is labelled "cloud-rendered (LTX-2.5 partner node)".
- On any failure the free local cut stays and a warning explains why.
- `XENO_CLOUD_DRY_RUN=1` swaps the paid engine for a free ffmpeg mock. `XENO_CLOUD_NEVER=1` refuses every paid submit.
- The key is read from `COMFY_ORG_API_KEY` in the desk process only. It is never written to plans, logs or results.

### Custom cut points

Cloud quality can also take a cut plan (`cut_plan` in `/api/cloud/estimate` and `/api/generate`, or **Cut plan** in the UI, which loads a JSON file). A cut plan replaces the automatic ~5s beat grid.

- **Stills:** an optional `stills` list of black-pool nouns, one more than the number of shots.
- **Shot times:** each shot has `start` and `end`, contiguous on the song.
- **Render length:** `render_s` must be one of 2/3/4/5/6/8/10, so 2s is the minimum. If you leave it out, it's derived from `speed`.
- **Speed:** `speed` is render_s ÷ slot length. It's checked to within 20%.
- **Speed ramp:** optional `ease: "in"` makes the morph accelerate into the cut.
- **Effects:** optional `effects`, each placed at a song time `t`:
  - `punch`: zoom and flash
  - `stutter`: repeat a 2-frame slice
  - `hold`: freeze
  - `skip`: lurch ahead
  - `reverse`: play backwards for a beat

Only render seconds cost money: the estimate is the sum of render_s × US$0.1287 for Fast 720p. Speed, ease and effects are free post-processing in `stitch`. Every shot still starts on still A and ends on still B, so the chain stays continuous.

The cost card and the single-use confirm click are unchanged. The confirm must cover the cut plan's own price.
