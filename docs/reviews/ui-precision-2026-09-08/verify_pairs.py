#!/usr/bin/env python3
"""Reject before/after evidence whose drawing fixtures are not identical."""

from __future__ import annotations

import json
from pathlib import Path


HERE = Path(__file__).resolve().parent


def main() -> None:
    before = json.loads((HERE / "captures/before/manifest.json").read_text())
    after = json.loads((HERE / "captures/after/manifest.json").read_text())
    stable = lambda item: {key: value for key, value in item["fixtureEvidence"].items()
                           if key != "timeDependentUi"}
    left = {item["scenario"]: stable(item) for item in before["scenarios"]}
    right = {item["scenario"]: stable(item) for item in after["scenarios"]}
    assert left.keys() == right.keys(), (left.keys() - right.keys(), right.keys() - left.keys())
    mismatches = [name for name in left if left[name] != right[name]]
    if mismatches:
        for name in mismatches:
            print(name)
            print("  before", json.dumps(left[name], sort_keys=True)[:1000])
            print("  after ", json.dumps(right[name], sort_keys=True)[:1000])
        raise SystemExit(f"fixture mismatch in {len(mismatches)} scenario(s)")
    failures = []
    for name, evidence in left.items():
        counts = evidence["geometryCounts"]
        if name.startswith(("compose-", "plot-", "pens-", "settings-", "machine-menu-",
                            "file-menu-", "new-project-", "simulator-")) and not counts["compose"]:
            failures.append(f"{name}: empty Compose geometry")
        if name.startswith(("second-reading-", "homeostat-", "venation-")) and not counts["process"]:
            failures.append(f"{name}: empty process geometry")
        if "comparison" in name and not counts["reference"]:
            failures.append(f"{name}: empty comparison reference geometry")
        if name.startswith("animation-render-popup-") and not counts["renderImage"]:
            failures.append(f"{name}: missing rendered image")
    if failures:
        raise SystemExit("empty fixture evidence:\n" + "\n".join(failures))
    print(f"verified {len(left)} exact recipe + drawing-geometry fixture pairs")


if __name__ == "__main__":
    main()
