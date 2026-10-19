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
