"""Study gallery thumbnails (study bench v3, 2026-10-19).

Ian chose "the study gallery picker": a grid of every study, chosen by eye.
Each thumbnail is the study at its defaults, drawn once per study content
(id + version + a hash of what it draws, the frozen kit and the library) and
kept on disk in the machine-level config dir (`stores.py` conventions; tests
isolate it with AXIBRIDGE_CONFIG_DIR), so a later open is instant and an
edited or refrozen study draws a fresh one.

Drawing a thumbnail runs the study, and a few studies are slow (Shape atlas
~76 s: its clothoid fits; Ledger ~38 s on a first render). So it never runs
in the server process: up to two niced worker processes (one on a machine
with few cores) draw the queue (`python -m axibridge.gesture_studies_thumbs`,
one study per stdin line), off the server's GIL and below its priority, while
the bench keeps previewing; a second worker keeps the other cards coming while
one draws the Shape atlas. The queue is in request order (the gallery's order),
and a card shows a placeholder until its file exists.
"""
from __future__ import annotations

import atexit
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path as FsPath

from .stores import CONFIG_DIR

ROOT = CONFIG_DIR / "gesture_study_thumbs"
KEY_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}-v[0-9]{1,6}-[0-9a-f]{12}$")
#: a thumbnail that took longer than this to draw marks its study slow in the gallery
SLOW_SECONDS = 3.0
TIMEOUT_S = 600.0
MAX_POINTS = 40_000


def key_of(study) -> str:
    """Names one study's drawing: id, version and a hash of everything that
    draws it (engine, recipe, inks, the frozen kit, the current library)."""
    from .sources._gesture_studies import frozen_library as FL  # noqa: PLC0415
    from .sources.gesture_studies import frozen_from  # noqa: PLC0415
    what = {"engine": study.engine, "keep": study.keep, "inks": study.inks, "recipe": study.recipe,
            "kit": frozen_from(), "library": FL.current_snapshot()}
    h = hashlib.sha256(json.dumps(what, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:12]
    return f"{study.id}-v{study.version}-{h}"


# ---------------------------------------------------------------------------
# drawing one thumbnail (the child process)
# ---------------------------------------------------------------------------

def render_svg(study) -> str:
    """The study at its defaults as a small SVG: every ink in its pen colour,
    lines simplified to what a card can show."""
    import shapely  # noqa: PLC0415

    from .registry import get_source, load_builtin_modules  # noqa: PLC0415
    load_builtin_modules()
    src = get_source("gesture_studies")
    doc = src.generate(src.Params(study=study.model_dump(mode="json"), values={}))
    paths = [p for layer in doc.layers for p in layer.paths]
    runs = src.preview_styles(doc) or [{"color": "#100f0f", "width": 0.4, "paths": len(paths)}]
    W, H = float(doc.width or 267.0), float(doc.height or 180.0)
    tol = max(W, H) / 700.0
    lines = []
    for p in paths:
        if len(p.points) >= 3:
            g = shapely.simplify(shapely.linestrings(p.points), tol, preserve_topology=False)
            pts = shapely.get_coordinates(g).tolist()
        else:
            pts = [list(q) for q in p.points]
        lines.append(pts if len(pts) >= 2 else [list(p.points[0]), list(p.points[-1])])
    total = sum(len(x) for x in lines)
    stride = -(-total // MAX_POINTS)
    if stride > 1:
        lines = [x[::stride] + (x[-1:] if (len(x) - 1) % stride else []) for x in lines]
    hair = max(W, H) / 450.0
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:g} {H:g}" width="{W:g}mm" height="{H:g}mm">',
           '<g fill="none" stroke-linecap="round" stroke-linejoin="round">']
    at = 0
    for run in runs:
        width = max(float(run["width"]), hair)
        out.append(f'<g stroke="{run["color"]}" stroke-width="{width:.3g}">')
        for pts in lines[at:at + run["paths"]]:
            out.append('<polyline points="' + " ".join(f"{x:.1f},{y:.1f}" for x, y in pts) + '"/>')
        out.append("</g>")
        at += run["paths"]
    out.append("</g></svg>")
    return "\n".join(out)


def _write(path: FsPath, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".thumb-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _draw_job(job: dict) -> dict:
    from .sources._gesture_studies import studies as ST  # noqa: PLC0415
    key = job["key"]
    if not KEY_RE.fullmatch(key):
        return {"key": key, "error": "bad key"}
    try:
        study = ST.check_study(ST.Study(**job["study"]))
        t0 = time.perf_counter()
        svg = render_svg(study)
        seconds = time.perf_counter() - t0
    except Exception as e:  # noqa: BLE001 — reported on the card, never fatal to the worker
        return {"key": key, "error": f"{type(e).__name__}: {e}"[:300]}
    root = FsPath(job["root"])
    _write(root / f"{key}.svg", svg)
    _write(root / f"{key}.json", json.dumps({"id": study.id, "version": study.version, "seconds": round(seconds, 2)}))
    return {"key": key, "ok": True}


def _worker_main() -> int:
    """`python -m axibridge.gesture_studies_thumbs`: one job per stdin line
    ({"study", "key", "root"}), one answer per stdout line. Exits when stdin
    closes (the server is done with it, or gone)."""
    try:
        os.nice(10)
    except OSError:
        pass
    for line in sys.stdin:
        if line.strip():
            print(json.dumps(_draw_job(json.loads(line))), flush=True)
    return 0


# ---------------------------------------------------------------------------
# the server's queue
# ---------------------------------------------------------------------------

def _workers() -> int:
    return 2 if (os.cpu_count() or 1) > 4 else 1


class Thumbnails:
    """Missing thumbnails, drawn in request order by up to two niced worker
    processes (one where cores are few, as on the Pi). A worker draws jobs
    until the queue is empty, then is let go."""

    def __init__(self, root: FsPath):
        self.root = root
        self._lock = threading.Lock()
        self._queue: list[tuple[str, dict]] = []         # (key, study json)
        self._drawing: set[str] = set()
        self._failed: dict[str, str] = {}
        self._procs: set[subprocess.Popen] = set()
        self._threads: list[threading.Thread] = []
        self._closed = False
        self._epoch = 0

    def file(self, key: str) -> FsPath:
        if not KEY_RE.fullmatch(key or ""):
            raise KeyError("no such thumbnail")
        return self.root / f"{key}.svg"

    def status(self, study) -> dict:
        key = key_of(study)
        meta = self.root / f"{key}.json"
        if (self.root / f"{key}.svg").exists() and meta.exists():
            try:
                seconds = float(json.loads(meta.read_text())["seconds"])
            except (OSError, ValueError, KeyError, TypeError):
                seconds = None
            return {"key": key, "state": "ready", "seconds": seconds,
                    "slow": seconds is not None and seconds > SLOW_SECONDS}
        with self._lock:
            if key in self._failed:
                return {"key": key, "state": "failed", "error": self._failed[key]}
            if key in self._drawing:
                return {"key": key, "state": "drawing"}
            if any(k == key for k, _ in self._queue):
                return {"key": key, "state": "queued"}
        return {"key": key, "state": "missing"}

    def request(self, studies) -> dict[str, dict]:
        """Queue every study whose thumbnail is missing (in this order); → status by id."""
        out = {}
        for st in studies:
            s = self.status(st)
            if s["state"] == "missing":
                with self._lock:
                    if not self._closed and s["key"] not in self._drawing \
                            and all(k != s["key"] for k, _ in self._queue):
                        self._queue.append((s["key"], st.model_dump(mode="json")))
                        s = {**s, "state": "queued"}
            out[st.id] = s
        self._ensure_workers()
        return out

    def _ensure_workers(self) -> None:
        with self._lock:
            self._threads = [t for t in self._threads if t.is_alive()]
            while not self._closed and len(self._threads) < min(_workers(), len(self._queue) + len(self._drawing)) \
                    and self._queue:
                t = threading.Thread(target=self._work, args=(self._epoch,), name="gesture-study-thumbs", daemon=True)
                self._threads.append(t)
                t.start()

    def _next(self, epoch: int) -> tuple[str, dict] | None:
        with self._lock:
            if self._closed or epoch != self._epoch or not self._queue:
                return None
            key, study = self._queue.pop(0)
            self._drawing.add(key)
            return key, study

    def _work(self, epoch: int) -> None:
        job = self._next(epoch)
        if job is None:
            return
        try:
            proc = subprocess.Popen([sys.executable, "-m", "axibridge.gesture_studies_thumbs"],
                                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                    cwd=str(FsPath(__file__).resolve().parent.parent), text=True, bufsize=1)
        except OSError as e:
            with self._lock:
                self._failed[job[0]] = str(e)
                self._drawing.discard(job[0])
            return
        with self._lock:
            self._procs.add(proc)
        try:
            while job is not None:
                key, study = job
                watchdog = threading.Timer(TIMEOUT_S, proc.kill)
                watchdog.start()
                try:
                    proc.stdin.write(json.dumps({"study": study, "key": key, "root": str(self.root)}) + "\n")
                    proc.stdin.flush()
                    line = proc.stdout.readline()
                except (OSError, ValueError):
                    line = ""
                finally:
                    watchdog.cancel()
                try:
                    answer = json.loads(line) if line else {"error": "the drawing process stopped"}
                except ValueError:
                    answer = {"error": "the drawing process answered nonsense"}
                with self._lock:
                    self._drawing.discard(key)
                    if not answer.get("ok"):
                        self._failed[key] = str(answer.get("error"))[:300]
                if not line:
                    return
                job = self._next(epoch)
        finally:
            with self._lock:
                self._procs.discard(proc)
            try:
                proc.stdin.close()
            except OSError:
                pass
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

    def shutdown(self, final: bool = False) -> None:
        """Drop the queue and stop the drawing workers (the app's shutdown);
        `final` (process exit) also refuses later requests."""
        with self._lock:
            self._closed = self._closed or final
            self._epoch += 1
            self._queue.clear()
            self._drawing.clear()
            procs = list(self._procs)
        for proc in procs:
            if proc.poll() is None:
                proc.kill()


thumbnails = Thumbnails(ROOT)
atexit.register(thumbnails.shutdown, True)


if __name__ == "__main__":
    raise SystemExit(_worker_main())
