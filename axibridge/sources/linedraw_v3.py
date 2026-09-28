"""Learned contour and shadow drawings with explicit accepted face regions."""

from ..registry import SourceModule, register_source, report_progress
from ..assets import asset_store
from ..linedraw.contracts import LinedrawV3Params
from ..linedraw import runtime
from ..linedraw.engine import render_document


@register_source
class LinedrawV3(SourceModule):
    id = "linedraw_v3"
    label = "Linedraw v3"
    description = "Local learned contours, light form and pen-filled shadows. Open the bench to detect and correct face regions."
    orientation = "param"
    Params = LinedrawV3Params
    bench = {"adapter": "linedraw", "version": 1, "modes": ["new", "resume"]}
    library_bench = True

    def cache_identity(self):
        return runtime.model_identity()

    def generate(self, params):
        name = asset_store.resolve_frame(params.image, params.frame)
        data = asset_store.get(name)
        if not data:
            raise ValueError("Select an uploaded image first")
        if params.model_identity and params.model_identity != runtime.model_identity():
            raise ValueError(
                "Models changed; reopen the Linedraw bench and analyze again"
            )
        evidence = runtime.detect_and_analyze(data, params, progress=report_progress)
        return render_document(evidence, params)
