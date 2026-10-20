# Xenoform MCP server: let any AI drive the app

Xenoform ships a native [Model Context Protocol](https://modelcontextprotocol.io) server, built on the official Python MCP SDK. Claude Desktop, Claude Code, Cursor, Grok Bot, or any other MCP client can drive the whole app with it: vibes, settings, renders, progress, cancel, My videos, recipe codes, and an editor-style re-cut.

- It wraps the desk's own localhost API, so the desk must be running (`Xenoform.bat`).
- **stdio** is the default. **Streamable HTTP** binds to `127.0.0.1` only (port 47319, path `/mcp`), and the server refuses any other host.
- It never returns keys or tokens.
- Cloud (paid) quality is off unless the call passes `cloud=true` **and** `confirm_spend=true`.

The desk URL comes from `XENO_DESK` (default `http://127.0.0.1:47317`). Set it if your desk runs on a different port, for example `http://127.0.0.1:47330`.

## Install

```bat
cd C:\Projects\xenoform-rc2
.venv\Scripts\python -m pip install -e ".[agent]"
```
`Xenoform-MCP.bat` installs `mcp` on first run if it is missing.

## Run

```bat
Xenoform-MCP.bat                 :: stdio
Xenoform-MCP.bat --http          :: http://127.0.0.1:47319/mcp
python -m xenoform.mcp [--http] [--port 47319] [--desk http://127.0.0.1:47330]
```

## Claude Desktop

Add this to `%APPDATA%\Claude\claude_desktop_config.json`, then restart Claude:
```json
{
  "mcpServers": {
    "xenoform": {
      "command": "C:\\Projects\\xenoform-rc2\\.venv\\Scripts\\python.exe",
      "args": ["-m", "xenoform.mcp"],
      "env": { "XENO_DESK": "http://127.0.0.1:47317" }
    }
  }
}
```

## Claude Code

```bat
claude mcp add xenoform --env XENO_DESK=http://127.0.0.1:47317 -- C:\Projects\xenoform-rc2\.venv\Scripts\python.exe -m xenoform.mcp
:: or, with Xenoform-MCP.bat --http already running:
claude mcp add --transport http xenoform http://127.0.0.1:47319/mcp
```

## Cursor

Put this in `%USERPROFILE%\.cursor\mcp.json` (all projects) or `.cursor\mcp.json` (one project):
```json
{
  "mcpServers": {
    "xenoform": {
      "command": "C:\\Projects\\xenoform-rc2\\.venv\\Scripts\\python.exe",
      "args": ["-m", "xenoform.mcp"],
      "env": { "XENO_DESK": "http://127.0.0.1:47317" }
    }
  }
}
```
For HTTP instead, use `{ "mcpServers": { "xenoform": { "url": "http://127.0.0.1:47319/mcp" } } }`.

## Grok Bot or any HTTP client
Run `Xenoform-MCP.bat --http` and point the client at `http://127.0.0.1:47319/mcp`. The client has to run on the same PC.

## What the AI gets

On connect, the server's **instructions** tell the AI what Xenoform is, the workflow, the defaults (native 9:16, black vibe, preview tier, open weights only), and the spend rules. They also tell it to greet you with "Connected to Xenoform, here's what you can do", suggest a few starters, and ask what you want to make.

**Tools**

| area | tools |
|---|---|
| status | `get_status` (desk, ComfyUI, GPU tier, models / final readiness, recent jobs, settings) |
| catalogue | `list_vibes`, `list_shapes`, `list_transitions`, `list_presets`, `get_autotune_recipe` |
| project | `create_project`, `update_settings`, `get_settings`, `load_audio`, `attach_image` |
| render | `start_render`, `get_render_progress`, `wait_for_render`, `cancel_render`, `get_output`, `list_videos` |
| recipes | `encode_recipe`, `decode_recipe`, `remix_recipe` |
| AI director | `get_audio_analysis`, `get_cut_timeline`, `apply_edit_list`, `get_frames`, `run_review` (built-in critique) |
| storyboard (director view) | `list_registers`, `get_register`, `set_register`, `set_preset`, `analyse_track`, `create_storyboard`, `edit_scene_card`, `set_params`, `apply_note`, `render`, `get_render_status`, `list_versions`, `revert`, `export` |

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
