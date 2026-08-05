---
name: pi
description: Work with the idkpi Raspberry Pi — the repo clone there, scheduling unattended Claude runs, checking results/logs/timers, and hardware boundaries. Use when the user mentions the Pi/idkpi, scheduling remote work, or fetching a Pi run's results.
---

# idkpi as a second bench (set up 2026-07-10)

`ssh idkpi` (Tailscale, key auth, non-interactive-safe). aarch64, Python
3.13, 8G RAM, ~45G free. `claude` (Code CLI) is installed at
`~/.local/bin/claude` — **not on the default non-interactive ssh PATH**;
use `bash -lc "claude …"` or export PATH in scripts. Auth is a personal
login, already verified working. Linger is enabled, so `systemd-run --user`
timers fire without a session.

## The repo clone

- `~/idk.axibridge` — full git clone of `git@github.com:ianduclos/idk.axibridge`
  (private). GitHub access via a **write deploy key**
  (`~/.ssh/github_axibridge`, wired in `~/.ssh/config`); the Pi can pull and
  push branches. Convention: the Pi pushes feature branches only, **never
  main** — the Mac reviews and merges.
- `.venv/` at the clone root: full dev env (`pip install -e . pytest httpx2`
  + pyaxidraw from `https://cdn.evilmadscientist.com/dl/ad/public/AxiDraw_API.zip`).
  Suite runs green and hardware-free: `.venv/bin/python -m pytest -q`.
  Gotcha: starlette's test client needs `httpx2` on this box.
- Git identity is set locally (`ianduclos (idkpi)`), so commits made on the
  Pi are attributable.
- **Distinct from `~/axibridge`** — that older dir holds the axicli venv the
  `pi_ssh` plot backend uses. Don't touch it, don't merge them.

## Scheduling an unattended Claude run

Pattern that works (used for the first generator mission):

1. Write the mission as a plan doc in the repo (`docs/plans/<name>.md`),
   commit and push — the Pi session reads context from the repo, so the
   plan must say: what to read first (CLAUDE.md, docs/MODULES.md), the git
   protocol (fetch, branch from `origin/main`, conventional commits, push
   the branch), verification expectations (pytest + PIL renders it actually
   looks at), a priority order for partial completion, and hard boundaries.
2. Runner script on the Pi (see `~/run-pi-generators.sh` as the template):
   exports PATH, cd to the clone, `git fetch && git checkout -B <branch>
   origin/main`, then
   `claude -p "Read docs/plans/<name>.md and execute it …" --model
   claude-fable-5 --dangerously-skip-permissions`, everything appended to a
   log file in `$HOME`.
3. Schedule: `systemd-run --user --on-active=<delay> --unit=<name> <script>`.
   Inspect: `systemctl --user list-timers`; cancel:
   `systemctl --user stop <name>.timer`; live log: `journalctl --user -u
   <name>.service -f` or tail the script's log file.

`--dangerously-skip-permissions` for unattended runs was the user's explicit
standing choice (2026-07-10) — confirm again only if the mission's blast
radius grows (touching main, hardware, or anything outside the clone).

## Checking results afterwards

- `ssh idkpi tail -50 ~/pi-generators-run.log` (or the mission's log).
- From the Mac: `git fetch origin && git log --oneline origin/<branch>` —
  review the diff locally, merge deliberately.
- Keep versions in lockstep after merging: `ssh idkpi 'cd ~/idk.axibridge
  && git pull'`.

## Hardware boundaries

The AxiDraw may hang off the Pi (`/dev/ttyACM0`). Unattended runs must
never open that port — the suite is simulator-only and nothing in a
software mission needs hardware. Plotting via the Pi remains the Mac's job
through the **"AxiDraw via Pi (ssh)"** backend (`backends/pi_ssh.py`), which
uses the old `~/axibridge/.venv` axicli install. Motors need the barrel-jack
PSU; without it axicli dry-runs silently.
