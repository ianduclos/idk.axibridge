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

echo "axibridge → http://localhost:$PORT  (interpreter: $PYTHON)"
( sleep 2 && open "http://localhost:$PORT" ) &
exec "$PYTHON" -m axibridge --port "$PORT"
