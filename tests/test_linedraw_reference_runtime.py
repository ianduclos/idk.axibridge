import numpy as np
import pytest
from axibridge.linedraw.contracts import LinedrawV3Params


def test_detail_crop_context_clamps_at_source_edge():
    from axibridge.linedraw.worker import detail_crop_bounds
    # .2x.4 rectangle expanded by 35% about centre then clipped.
    r={'polygon':[[0,0],[.2,0],[.2,.4],[0,.4]]}
    assert detail_crop_bounds(r,100,100) == (0,0,24,47)


def test_reference_dispatch_preserves_scale_and_rotation(monkeypatch):
    from axibridge.linedraw import engine, reference_light
    from axibridge.linedraw.contracts import Evidence
    evidence=Evidence(np.ones((20,40,3)), np.ones((20,40)), None,
                      np.ones((20,40)),np.ones((20,40)))
    monkeypatch.setattr(reference_light,'render_light_components',lambda *a,**k:{'contours':[np.array([[10.,5.],[30.,15.]])], 'form':[], 'cores':[]})
    doc=engine.render_document(evidence,LinedrawV3Params(style='light_support',width=100,rotate=90))
    assert doc.width==100 and doc.height==200
    assert list(doc.iter_paths())[0][1].points == [(75.,50.),(25.,150.)]
