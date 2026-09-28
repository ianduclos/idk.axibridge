import unittest
import copy
from unittest.mock import patch

import numpy as np

from tools.linedraw_research.allocation import prepare_case, select_details, _ellipse_mask, _clip_path


def rectangle(x0, y0, x1, y1):
    return [[x0,y0], [x1,y0], [x1,y1], [x0,y1]]


def fixture():
    return {"id": "fixture", "width": 100, "height": 100, "people": [
        {"id": "back", "owner_polygon": rectangle(0,0,70,99),
         "face": {"id": "back-face", "ellipse": [25,20,7,7]},
         "regions": [{"id":"back-hand", "person_id":"back", "category":"hands_feet", "polygon":rectangle(10,10,40,40)},
                     {"id":"back-body", "person_id":"back", "category":"body", "polygon":rectangle(0,0,70,99)}]},
        {"id": "front", "owner_polygon": rectangle(40,0,99,99),
         "face": {"id": "front-face", "ellipse": [70,20,7,7]},
         "regions": [{"id":"front-hand", "person_id":"front", "category":"hands_feet", "polygon":rectangle(65,65,90,90)},
                     {"id":"front-body", "person_id":"front", "category":"body", "polygon":rectangle(40,0,99,99)}]},
    ]}


def candidate(cid, points, confidence=1.):
    return {"id":cid,"points":points,"length":0.,"confidence":confidence,"score":0.}


def exact_ellipse_intersection_length(points, ellipse):
    cx, cy, rx, ry = ellipse
    total = 0.
    for start, end in zip(points[:-1], points[1:]):
        a, b = np.asarray(start, dtype=float), np.asarray(end, dtype=float)
        p, d = (a-[cx,cy])/[rx,ry], (b-a)/[rx,ry]
        coeff = [np.dot(d,d), 2*np.dot(p,d), np.dot(p,p)-1]
        roots = np.roots(coeff)
        fractions = [0., 1.] + [float(r.real) for r in roots if abs(r.imag)<1e-9 and 0<r.real<1]
        fractions.sort()
        for t0,t1 in zip(fractions[:-1],fractions[1:]):
            middle = p+d*(t0+t1)/2
            if np.dot(middle,middle)<1:
                total += float(np.linalg.norm(b-a))*(t1-t0)
    return total


class SelectionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.probability = np.ones((100,100), dtype=np.float32)
        cls.case = fixture()
        cls.prepared = prepare_case(cls.case, cls.probability)

    def test_prepare_case_does_not_touch_filesystem_or_mutate_inputs(self):
        case = fixture()
        probability = self.probability.copy()
        original = copy.deepcopy(case)
        with patch("builtins.open", side_effect=AssertionError("filesystem access")):
            prepared = prepare_case(case, probability)
        self.assertEqual(case, original)
        np.testing.assert_array_equal(probability, self.probability)
        self.assertEqual(prepared["guide"]["case_id"], "fixture")

    def test_exclusive_owners_regions_and_face(self):
        p = self.prepared
        self.assertTrue(p["owners"]["front"][50,50])
        self.assertFalse(p["owners"]["back"][50,50])
        self.assertTrue(p["owners"]["back"][50,20])
        self.assertFalse(p["regions"]["back-body"][20,25])
        self.assertFalse(p["regions"]["back-body"][20,20])
        self.assertFalse(p["regions"]["back-body"][20,50])
        self.assertFalse(np.any(p["regions"]["back-body"] & p["regions"]["back-hand"]))

    def test_clipping_and_multi_owner_preservation(self):
        line = candidate("wide", [[0.5,50.5],[99.5,50.5]])
        evidence = {"case_id":"fixture", "whole_candidates":[line]}
        out = select_details(evidence, self.case, self.prepared, "whole", 4)
        self.assertEqual(out["counts"], {"back":1,"front":1})
        self.assertEqual({p["person_id"] for p in out["selected"]}, {"back","front"})
        self.assertTrue(all(len(p["points"]) >= 2 for p in out["selected"]))

    def test_duplicates_joins_and_redistribution(self):
        paths = [candidate("a", [[10.5,70.5],[20.5,70.5]]),
                 candidate("duplicate", [[10.51,70.51],[20.51,70.51]]),
                 candidate("b", [[20.6,70.5],[30.5,70.5]]),
                 candidate("far", [[5.5,80.5],[15.5,80.5]])]
        evidence = {"case_id":"fixture", "regions":{"back-body":paths}}
        out = select_details(evidence, self.case, self.prepared, "regional", 3)
        self.assertEqual(out["counts"]["back"], 2)
        self.assertEqual(out["counts"]["front"], 0)
        self.assertEqual(out["diagnostics"]["regions"]["back-body"]["after_dedup"], 3)
        self.assertTrue(any("+" in p["id"] for p in out["selected"]))

    def test_face_and_priority_clip(self):
        evidence = {"case_id":"fixture", "whole_candidates":[
            candidate("face", [[21.5,20.5],[29.5,20.5]]),
            candidate("hand", [[10.5,35.5],[30.5,35.5]])]}
        out = select_details(evidence, self.case, self.prepared, "whole", 2)
        self.assertEqual(out["counts"]["back"], 1)
        self.assertEqual(out["selected"][0]["region_id"], "back-hand")

    def test_region_exclusion(self):
        case = copy.deepcopy(self.case)
        case["id"] = "fixture-exclusion"
        case["people"][1]["regions"][1]["exclude_polygons"] = [rectangle(50,50,60,60)]
        prepared = prepare_case(case, self.probability)
        self.assertTrue(prepared["owners"]["front"][55,55])
        self.assertFalse(prepared["regions"]["front-body"][55,55])

    def test_budget_is_independent_for_each_person(self):
        evidence = {"case_id": "fixture", "whole_candidates": [
            candidate("back", [[8.5, 70.5], [28.5, 70.5]]),
            candidate("front", [[72.5, 70.5], [92.5, 70.5]])]}
        result = select_details(evidence, self.case, self.prepared, "whole", 1)
        self.assertEqual(result["counts"], {"back": 1, "front": 1})
        self.assertEqual(len(result["selected"]), 2)

    def test_continuous_face_ellipse_clearance(self):
        # This diagonal cuts 3.9 px through the exact ellipse while slipping
        # between protected pixel centers without the one-pixel guard.
        points = [[16.191688899229653,20.713008736289687],
                  [25.559717332286148,7.742270774344538]]
        ellipse = self.case["people"][0]["face"]["ellipse"]
        unguarded = ~_ellipse_mask(ellipse,100,100)
        self.assertGreater(sum(exact_ellipse_intersection_length(p,ellipse)
                               for p in _clip_path(points,unguarded)), 3.)
        evidence = {"case_id":"fixture", "whole_candidates":[candidate("diagonal",points)]}
        selected = select_details(evidence,self.case,self.prepared,"whole",4)["selected"]
        self.assertTrue(selected)
        self.assertTrue(all(exact_ellipse_intersection_length(p["points"],ellipse)<1e-8
                            for p in selected))


if __name__ == "__main__":
    unittest.main()
