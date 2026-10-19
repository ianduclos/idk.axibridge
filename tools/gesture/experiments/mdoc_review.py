"""Round 16 thread D (`mdoc`): the review images — process documents on v2
scores and on two round-15 keepers (listen 15102, arch 15010) as v1 sheets.

    .local/gesture/.venv/bin/python tools/gesture/experiments/mdoc_review.py [names…]

Writes working images to .local/gesture/out/mdoc/ and, with --results, the
chosen ones to tools/gesture/results/mdoc-*.jpg (score/recipe beside each).
"""
from __future__ import annotations

import sys

from mdoc_common import OUT, RESULTS, apply_devices, kit, listen_composer, save, study_recipe, synth


def score_listen_hands(seed: int = 16301, outcomes_p: float = 1.0) -> dict:
    """listen 15102 sealed in the left two-thirds; two hands across the sheet
    that hear it (crossings drawn per crossing by the test relation, which
    also leans) and yield to each other."""
    return {"version": 2, "label": "listen 15102 sealed + two hands", "frame": [250.0, 175.0], "seed": seed,
            "layers": [
                {"id": "S", "role": "sealed", "pen": "black", "region": [5.0, 5.0, 165.0, 165.0],
                 "composer": listen_composer()},
                {"id": "H1", "role": "listener", "pen": "green", "region": [60.0, 20.0, 180.0, 130.0],
                 "part": {"voice": {"id": "hand", "hand": "river_meander", "length": 2.4}}},
                {"id": "H2", "role": "listener", "pen": "purple", "region": [100.0, 40.0, 140.0, 125.0],
                 "part": {"voice": {"id": "hand", "hand": "dance_staccato", "length": 2.2}}},
            ],
            "relations": [
                {"id": "R0", "kind": "mdoc_outcomes", "src": "S", "dst": "H1", "p": outcomes_p,
                 "params": {"w_cross": 0.15, "w_sympathy": 0.3, "streak": 0.45}},
                {"id": "R1", "kind": "mdoc_outcomes", "src": "S", "dst": "H2", "p": 0.5,
                 "params": {"w_cross": 0.15, "w_sympathy": 0.3, "streak": 0.45}},
                {"id": "R2", "kind": "yield", "src": "H1", "dst": "H2"},
            ]}


def score_three_hands(seed: int = 16320) -> dict:
    """Three hands, no composer: a speaker and two listeners, every crossing
    negotiated; the clearest ground for the sympathy trace."""
    return {"version": 2, "label": "three hands", "frame": [250.0, 175.0], "seed": seed,
            "layers": [
                {"id": "A", "role": "speaker", "pen": "black",
                 "part": {"voice": {"id": "hand", "hand": "hokusai", "length": 2.6}}},
                {"id": "B", "role": "listener", "pen": "blue", "region": [30.0, 15.0, 190.0, 145.0],
                 "part": {"voice": {"id": "hand", "hand": "river_bend", "length": 2.4}}},
                {"id": "C", "role": "listener", "pen": "red", "region": [50.0, 30.0, 160.0, 120.0],
                 "part": {"voice": {"id": "hand", "hand": "trail_miner", "length": 2.0}}},
            ],
            "relations": [
                {"id": "R0", "kind": "mdoc_outcomes", "src": "A", "dst": "B",
                 "params": {"w_under": 0.15, "w_over": 0.1, "w_cross": 0.1, "w_stop": 0.05, "w_sympathy": 0.6,
                            "reach": 12.0, "gain": 0.45, "streak": 0.3}},
                {"id": "R1", "kind": "yield", "src": "A", "dst": "C"},
                {"id": "R2", "kind": "mdoc_outcomes", "src": "B", "dst": "C", "p": 0.5},
            ]}


def v1(name: str, seed: int | None = None):
    import pickle  # noqa: PLC0415
    f = OUT / f"{name}{seed or ''}.pkl"
    if f.exists():
        return pickle.loads(f.read_bytes())
    sh = kit.run(study_recipe(name, seed))
    OUT.mkdir(parents=True, exist_ok=True)
    f.write_bytes(pickle.dumps(sh))
    return sh


JOBS = {
    # 1: the census, both readings, on a v2 sheet whose crossings vary
    "census-v2": lambda: (synth.run(score_listen_hands()),
                          [{"id": "mdoc_census", "place": "over"},
                           {"id": "mdoc_census", "place": "beside", "size": 95}]),
    # 2: the sympathy trace on three hands: trace over, specimens beside
    "sympathy": lambda: (synth.run(score_three_hands()),
                         [{"id": "mdoc_sympathy", "place": "over"},
                          {"id": "mdoc_sympathy", "place": "beside", "size": 95}]),
    # 3: listen 15102 (v1): the crossings read off the geometry, and the relation ledger
    "listen15102": lambda: (v1("listen"),
                            [{"id": "mdoc_census", "place": "over"},
                             {"id": "mdoc_ledger", "place": "beside", "size": 125}]),
    # 4: arch 15010 (v1): provenance beside
    "arch15010": lambda: (v1("arch", 15010),
                          [{"id": "mdoc_provenance", "place": "beside", "size": 120}]),
    # 5: the score as a score + the unheard drawing, on the v2 listen sheet
    "staff-unheard": lambda: (synth.run(score_listen_hands()),
                              [{"id": "mdoc_unheard", "place": "beside", "size": 110},
                               {"id": "mdoc_staff", "place": "beside", "side": "bottom", "size": 48}]),
    # 6: provenance + ledger on the v2 listen sheet (the sealed composer's hands traced inside it)
    "provenance-v2": lambda: (synth.run(score_listen_hands()),
                              [{"id": "mdoc_provenance", "place": "beside", "size": 115}]),
    "ledger-v2": lambda: (synth.run(score_listen_hands()),
                          [{"id": "mdoc_ledger", "place": "beside", "size": 125}]),
    "staff-listen": lambda: (v1("listen"), [{"id": "mdoc_staff", "place": "beside", "side": "bottom", "size": 62}]),
    "ledger-unheard": lambda: (synth.run(score_listen_hands()),
                               [{"id": "mdoc_ledger", "place": "beside", "size": 120},
                                {"id": "mdoc_unheard", "place": "beside", "side": "bottom", "size": 120}]),
    "all-v2": lambda: (synth.run(score_listen_hands()),
                       [{"id": "mdoc_census", "place": "over"}, {"id": "mdoc_sympathy", "place": "over"},
                        {"id": "mdoc_ledger", "place": "beside", "size": 125}]),
}


def main(argv):
    results = "--results" in argv
    names = [a for a in argv if not a.startswith("--")] or list(JOBS)
    for i, n in enumerate(names):
        sh, devs = JOBS[n]()
        out = apply_devices(sh, devs)
        p = save(out, (RESULTS / f"mdoc-{i + 1}-{n}.jpg") if results else (OUT / f"r-{n}.jpg"), label=n)
        print(p, out.frame)


if __name__ == "__main__":
    main(sys.argv[1:])
