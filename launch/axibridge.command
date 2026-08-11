#!/bin/zsh
# axibridge launcher — double-clickable in Finder.
#
# THE POINT OF THIS FILE is the hard-coded interpreter below. The v1 failure
# mode was pyaxidraw landing in a different Python (conda base) than the app
# ran from, making the native backend silently unavailable. This launcher
# pins the one interpreter that has pyaxidraw installed; if you move the
# repo or rebuild the venv, update PYTHON.

REPO="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$REPO/.venv/bin/python"
PORT=2942

if [[ ! -x "$PYTHON" ]]; then
  echo "✗ pinned interpreter not found: $PYTHON"
  echo "  create it with:  python3 -m venv $REPO/.venv && $REPO/.venv/bin/pip install -e '$REPO[occult]'"
  read -k 1 -s "?press any key to close"
  exit 1
fi

if ! "$PYTHON" -c "import pyaxidraw" 2>/dev/null; then
  echo "⚠ pyaxidraw is not importable in $PYTHON"
  echo "  the native backend will be unavailable. Install it THERE with:"
  echo "  $PYTHON -m pip install https://cdn.evilmadscientist.com/dl/ad/public/AxiDraw_API.zip"
fi

# ffmpeg is the render popup's MP4 export dependency (GIF export needs
# nothing extra) — a machine-level install, not a Python one. Check the same
# well-known Homebrew prefixes the server itself checks (axibridge/api.py's
# _find_ffmpeg): a Finder-launched app bundle doesn't inherit the brew PATH
# even when ffmpeg is genuinely installed, so `command -v` alone would
# under-report it here just like shutil.which alone did server-side. Only
# runs brew when ffmpeg is truly absent from all of those; never fatal —
# GIF export and everything else works without it.
if ! command -v ffmpeg >/dev/null 2>&1 \
   && [[ ! -x /opt/homebrew/bin/ffmpeg ]] && [[ ! -x /usr/local/bin/ffmpeg ]]; then
  if command -v brew >/dev/null 2>&1; then
    echo "⚠ ffmpeg not found — installing via brew (used for MP4 export; GIF export doesn't need it)…"
    brew install ffmpeg || echo "  brew install ffmpeg failed — continuing without it; MP4 export will stay disabled"
  else
    echo "⚠ ffmpeg not found and brew isn't on PATH — MP4 export will be unavailable (GIF export still works)"
  fi
fi

echo "axibridge → http://localhost:$PORT  (interpreter: $PYTHON)"
( sleep 2 && open "http://localhost:$PORT" ) &
exec "$PYTHON" -m axibridge --port "$PORT"
