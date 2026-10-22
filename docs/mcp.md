# Xenoform MCP server: let any AI drive the app

Xenoform ships a native [Model Context Protocol](https://modelcontextprotocol.io) server, built on the official Python MCP SDK. Claude Desktop, Claude Code, Cursor, Grok Bot, or any other MCP client can drive the whole app with it: vibes, settings, renders, progress, cancel, My videos, recipe codes, and an editor-style re-cut.

- It wraps the desk's own localhost API, so the desk must be running (`Xenoform.bat`).
- **stdio** is the default. **Streamable HTTP** binds to `127.0.0.1` only (port 47319, path `/mcp`), and the server refuses any other host.
- It never returns keys or tokens.
- Cloud (paid) quality is off unless the call passes `cloud=true` **and** `confirm_spend=true`.

The desk URL comes from `--desk` or `XENO_DESK`; set it to `http://127.0.0.1:47317`, the desk `Xenoform.bat` starts. If neither is set, the server uses `XENO_PORT`, or else whichever desk answers first on 47330 or 47317.

## Install

From the repo folder:

```bat
.venv\Scripts\python -m pip install -e ".[agent]"
```
`Xenoform-MCP.bat` installs `mcp` on first run if it is missing. Linux and macOS: `.venv/bin/python -m pip install -e ".[agent]"`.

## Run

```bat
Xenoform-MCP.bat                 :: stdio
Xenoform-MCP.bat --http          :: http://127.0.0.1:47319/mcp
python -m xenoform.mcp [--http] [--port 47319] [--desk http://127.0.0.1:47317]
```

## Connect a client

One snippet for every client. Replace `.venv/Scripts/python.exe` with the absolute path of the checkout's `.venv` Python on your machine (`.venv/bin/python` on Linux and macOS); MCP clients do not resolve relative paths.

Claude Desktop (`%APPDATA%\Claude\claude_desktop_config.json`, then restart Claude) and Cursor (`%USERPROFILE%\.cursor\mcp.json` for all projects, or `.cursor\mcp.json` for one):
```json
{
  "mcpServers": {
    "xenoform": {
      "command": ".venv/Scripts/python.exe",
      "args": ["-m", "xenoform.mcp"],
      "env": { "XENO_DESK": "http://127.0.0.1:47317" }
    }
  }
}
```

Claude Code:
```bat
claude mcp add xenoform --env XENO_DESK=http://127.0.0.1:47317 -- .venv\Scripts\python.exe -m xenoform.mcp
:: or, with Xenoform-MCP.bat --http already running:
claude mcp add --transport http xenoform http://127.0.0.1:47319/mcp
```

For HTTP in Cursor or any other client, use `{ "mcpServers": { "xenoform": { "url": "http://127.0.0.1:47319/mcp" } } }`.

## Grok Bot or any HTTP client
Run `Xenoform-MCP.bat --http` and point the client at `http://127.0.0.1:47319/mcp`. The client has to run on the same PC.

## What the AI gets

On connect, the server's **instructions** tell the AI what Xenoform is, the workflow, the defaults (native 9:16, black vibe, preview tier, open weights only), and the spend rules. They also tell it to greet you with "Connected to Xenoform, here's what you can do", suggest a few starters, and ask what you want to make.

**Tools (45)**

| area | tools |
|---|---|
| status | `get_status` (desk, ComfyUI, GPU tier, models / final readiness, recent jobs, settings) |
| catalogue | `list_vibes`, `list_shapes`, `list_transitions`, `list_presets`, `get_autotune_recipe` |
| project | `create_project`, `update_settings`, `get_settings`, `load_audio`, `attach_image` |
| look and QA | `set_look` (profile, `dance_fx` preset or `auto`, `stem_orbit`, macros), `list_looks`, `review_render` (runs `media_qa` on a finished file), `get_qa` |
| guardrails | `list_guardrails`, `check_guardrails` |
| render | `start_render`, `get_render_progress`, `wait_for_render`, `cancel_render`, `get_output`, `list_videos` |
| recipes | `encode_recipe`, `decode_recipe`, `remix_recipe` |
| AI director | `get_audio_analysis`, `get_cut_timeline`, `apply_edit_list`, `get_frames`, `run_review` (built-in critique) |
| storyboard (director view) | `list_registers`, `get_register`, `set_register`, `set_preset`, `analyse_track`, `create_storyboard`, `edit_scene_card`, `set_params`, `apply_note`, `render`, `get_render_status`, `list_versions`, `revert`, `export` |

The look tools are described in [AI_GUIDE.md](AI_GUIDE.md) under *The house look*.

**Prompts:** `get_started`, `make_music_video(idea, vibe, song_path)`, and `review_cut`.

**Resources:**
- `xenoform://guide`, which is [AI_GUIDE.md](AI_GUIDE.md), the single source for both this page and the AI.
- `xenoform://examples`, `xenoform://vibes`, `xenoform://settings`, `xenoform://storyboard`, `xenoform://lessons`, and `xenoform://transitions`.

**Tiers:**
- `preview` is a CPU animatic, ready in seconds, with no GPU model.
- `draft` and `final` render open-weights LTX on your GPU.
- `cloud` is paid and needs `confirm_spend=true`.

**State:** project settings and job ids persist in `%USERPROFILE%\.xenoform\mcp_project.json` (override with `XENO_MCP_STATE`), so a server restart carries on where it left off.

## Tests
```bat
.venv\Scripts\python -m pytest tests/test_mcp_tools.py tests/test_mcp_client.py
```
- Unit tests run every tool against a mocked desk.
- Client tests use the real MCP client SDK in memory, over stdio and over HTTP. They cover a server restart and the refusal of a non-localhost bind.

## Images, recipe codes, preview

- **Your images as morph targets:** `attach_image(path)` (role `morph_target`, the default) makes the object morph through your pictures in order before the vibe's own objects, on draft and final. With `role="first_frame"`, the picture opens every shot instead.
- **Recipe codes:** `xf1.…` is the desk's code (vibe, idea, aspect, seed, energy, tier). When transitions or shot edits are set, `encode_recipe` returns a versioned `xf2.…` code that wraps the `xf1` code plus those transitions and edits. `decode_recipe` and `remix_recipe` accept `xf1.`, `xf2.` and the advanced `XF-` codes. A code from a newer version is refused with a clear message.
- **Preview** is a portrait 216×384 sketch for 9:16 (square for 1:1, landscape for 16:9).
- **`get_frames`** returns an absolute URL.
