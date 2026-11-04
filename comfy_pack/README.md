# Xenoform for ComfyUI

A song becomes a music video of LTX morphs on the beat, inside ComfyUI. The nodes read the song (beats, sections, the
drop), plan the cut the way the Xenoform desk does (shots on the beat, a chain of objects, each morph's style and
timing), hand each morph to ComfyUI's own LTX 0.9.5 nodes, and cut the rendered morphs to the song.

Everything is the song's: the canvas is its sections, beats and drops, and every shot is snapped to them. There is no
camera and no 3D view.

## Install

**ComfyUI-Manager, from the git URL** (the way to install it until the pack is on the Comfy Registry):

1. Manager > **Install via Git URL** > `https://github.com/tysonfarrington-cmyk/xenoform`
2. Restart ComfyUI. ComfyUI loads custom nodes only when it starts.
3. Load `custom_nodes/xenoform/comfy_pack/workflows/xenoform_demo.json` (drag it onto the canvas) and press **Queue**.

The Manager clones the whole repository into `custom_nodes/xenoform`; the repository's `__init__.py` registers these
nodes and serves the editor. Its `requirements.txt` lists nothing, so nothing is pip-installed into ComfyUI's Python.

**By hand, the same thing:** `git clone https://github.com/tysonfarrington-cmyk/xenoform` inside `ComfyUI/custom_nodes`,
then restart ComfyUI.

**The pack folder alone:** copy `comfy_pack/` into `ComfyUI/custom_nodes/` under any name (`xenoform-nodes`, say) and
restart. It carries what it needs: the demo song, the dozen Liquid chrome stills of that vibe's curated chain, and the
vibe registry's looks and tuning. Every other vibe borrows those stills and keeps its own look; the whole repository has
every vibe's own stills. Install one or the other, not both (the second copy's nodes would replace the first's).

**Models** (the stock LTX 0.9.5 morph, as the desk's Draft uses): `models/checkpoints/ltx-video-2b-v0.9.5.safetensors`
and `models/text_encoders/t5xxl_fp8_e4m3fn_scaled.safetensors` (the links are in `pyproject.toml`). ComfyUI 0.33 has
every node the demo uses. ffmpeg must be on PATH, or the `imageio-ffmpeg` ComfyUI installs usually carry, for the
Assemble.

**Python packages:** none beyond ComfyUI's own (numpy, Pillow, torch, PyAV). If librosa is installed, the song analysis
runs the desk's own librosa code; without it, the same steps run in numpy and give the same beats, sections and drop on
the bundled songs (the tests measure it).

## For Tys, after the contest

Install through the Manager from the git URL (above) and restart ComfyUI once: it loads custom nodes only at start, so
nothing here is in the running ComfyUI until then. Then fill in `PublisherId` in `pyproject.toml` (this folder's, to
publish the pack alone; the repository root has its own `[tool.comfy]` for the whole repository) and run
`comfy node publish` to put it on the Registry, where the Manager's search finds it.
