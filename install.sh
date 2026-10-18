#!/usr/bin/env bash
# Install Xenoform into its own .venv. It does not pip-install into ComfyUI.
# Pass --link-nodes to symlink the pack into ComfyUI/custom_nodes. Off unless you ask.
set -euo pipefail

PACK="$(cd "$(dirname "$0")" && pwd)"
LINK=0
if [[ "${1:-}" == "--link-nodes" ]]; then
  LINK=1
fi

find_python312() {
  if command -v python3.12 >/dev/null 2>&1; then
    command -v python3.12
    return
  fi
  if command -v python3 >/dev/null 2>&1; then
    local ver
    ver="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
    case "$ver" in
      3.1[2-9]|3.[2-9]*) command -v python3; return ;;
    esac
  fi
  return 1
}

if ! PY312="$(find_python312)"; then
  echo "Python 3.12 or newer was not found."
  echo "This installer does not use ComfyUI's Python."
  exit 1
fi

if [[ ! -x "$PACK/.venv/bin/python" ]]; then
  echo "Creating $PACK/.venv with $PY312"
  "$PY312" -m venv "$PACK/.venv"
fi

echo "Installing Python packages into $PACK/.venv"
"$PACK/.venv/bin/python" -m pip install --upgrade pip
"$PACK/.venv/bin/python" -m pip install -r "$PACK/requirements.txt"

if [[ "$LINK" == "1" ]]; then
  COMFY="${COMFYUI_DIR:-}"
  if [[ -z "$COMFY" ]]; then
    for candidate in \
      "$PACK/../ComfyUI" \
      "$HOME/ComfyUI" \
      "$HOME/AI/ComfyUI" \
      "/opt/ComfyUI"
    do
      if [[ -d "$candidate/custom_nodes" ]]; then
        COMFY="$(cd "$candidate" && pwd)"
        break
      fi
    done
  fi
  if [[ -z "$COMFY" ]]; then
    echo "ComfyUI was not found, so the node pack was not linked."
  else
    mkdir -p "$COMFY/custom_nodes"
    ln -sfn "$PACK" "$COMFY/custom_nodes/xenoform"
    echo "Linked the node pack at $COMFY/custom_nodes/xenoform"
  fi
else
  echo "The node pack stays in this folder. Run install.sh --link-nodes if you want it inside ComfyUI custom_nodes."
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "ffmpeg is not on PATH. The desk needs it to write video."
fi

echo
echo "Start the desk with: $PACK/.venv/bin/python -m xenoform ui --host 127.0.0.1 --port 47317"
echo "Open http://127.0.0.1:47317"
echo "ComfyUI stays on http://127.0.0.1:8188. The desk pings /system_stats there."
echo "Live renders use comfy-sdk against comfy-api-proxy on http://127.0.0.1:8189."
echo "Start it with: comfy-api-proxy --comfyui http://127.0.0.1:8188 --port 8189"
