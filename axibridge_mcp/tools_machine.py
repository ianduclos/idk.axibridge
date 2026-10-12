"""The machine. plot/pen/jog/go_home move a real pen: live target only, and
never allow-listed, so Ian approves every call. stop/pause are always fine —
stopping is the safe direction."""

from __future__ import annotations

from typing import Annotated

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from .targets import TargetName, Targets


def _fmt_s(seconds: float) -> str:
    m, s = divmod(round(seconds), 60)
    return f"{m} min {s:02d} s" if m else f"{s} s"


def register(tool, targets: Targets) -> None:
    @tool
    def estimate(plot_target: str = "all", target: TargetName = "live") -> str:
        """Time and travel for a plot of `plot_target` ("all" or a layer id),
        plus the project revision it was computed at. Show Ian this and a
        `see` image, then pass the revision to `plot`."""
        c = targets.client(target)
        rev = c.get("/api/project")["edit_rev"]
        plan = c.get("/api/plan", target=plot_target)
        if c.get("/api/project")["edit_rev"] != rev:
            raise ToolError("project changed while estimating — run estimate again")
        st = c.get("/api/state")["machine"]
        job = plan["job"]
        lines = [
            f"plot {plot_target}: {_fmt_s(job['total_duration'])} total, "
            f"{job['pen_down_distance'] / 1000:.2f} m pen-down, "
            f"{job['travel_distance'] / 1000:.2f} m travel, {job['pen_lifts']} lifts",
            f"backend {st.get('backend')} ({'connected' if st.get('connected') else 'NOT connected'}), "
            f"job {st.get('job_state')}",
            f"revision {rev} — call plot(revision={rev}, plot_target=\"{plot_target}\") to plot exactly this",
        ]
        lines += [f"warning: {w}" for w in plan.get("warnings", [])]
        if plan.get("estimator_note"):
            lines.append(plan["estimator_note"])
        return "\n".join(lines)

    @tool
    def plot(revision: int, plot_target: str = "all", target: TargetName = "live") -> str:
        """MOVES THE MACHINE. Plot `plot_target` on the live app. `revision`
        must be the one `estimate` returned; if the project changed since,
        this refuses — re-estimate and show Ian again."""
        c = targets.live_only(target)
        current = c.get("/api/project")["edit_rev"]
        if current != revision:
            raise ToolError(f"project changed since the estimate (revision {revision} → {current}); "
                            "run estimate again and show Ian before plotting")
        st = c.post("/api/plot/start", {"target": plot_target})
        return (f"plotting {plot_target} on {st.get('backend')} — job {st.get('job_state')}. "
                "stop() halts and returns home.")

    @tool
    def pen(down: bool, target: TargetName = "live") -> str:
        """MOVES THE MACHINE. Raise (down=false) or lower the pen."""
        c = targets.live_only(target)
        c.post("/api/machine/pen", {"down": down})
        return f"pen {'down' if down else 'up'}"

    @tool
    def jog(dx: Annotated[float, Field(ge=-300.0, le=300.0)] = 0.0,
            dy: Annotated[float, Field(ge=-218.0, le=218.0)] = 0.0,
            target: TargetName = "live") -> str:
        """MOVES THE MACHINE. Pen-up relative move in mm."""
        c = targets.live_only(target)
        r = c.post("/api/machine/jog", {"dx": dx, "dy": dy})
        return f"position {r['position']}"

    @tool
    def go_home(target: TargetName = "live") -> str:
        """MOVES THE MACHINE. Pen-up travel to the design origin (0, 0) — the
        physical home corner only when no custom origin is set. Errors on the
        pi_ssh backend, which has no goto."""
        c = targets.live_only(target)
        r = c.post("/api/machine/goto", {"x": 0.0, "y": 0.0})
        return f"position {r['position']}"

    @tool
    def stop(return_home: bool = True, target: TargetName = "live") -> str:
        """Stop the running job (safe to call any time). return_home walks the
        carriage home afterwards (see docs/MCP.md for the pi_ssh caveat)."""
        st = targets.client(target).post("/api/plot/stop", {"return_home": return_home})
        return f"stop sent — job {st.get('job_state')}"

    @tool
    def pause(target: TargetName = "live") -> str:
        """Pause the running job (backends that support it)."""
        st = targets.client(target).post("/api/plot/pause")
        return f"job {st.get('job_state')}"
