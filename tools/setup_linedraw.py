"""Configure already-installed local models; never downloads models or images."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from axibridge.linedraw.runtime import config_path, status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    for key in (
        "python",
        "line-code",
        "line-weights",
        "person-weights",
        "normal-code",
        "normal-weights",
        "face-python",
        "face-weights",
    ):
        parser.add_argument("--" + key)
    parser.add_argument("--normal-dependencies", action="append", default=[])
    parser.add_argument("--device", choices=["cpu", "mps", "cuda"])
    args = parser.parse_args()
    if args.check:
        result = status()
        print(json.dumps(result, indent=2))
        return 0 if result["available"] else 1
    config = {k: v for k, v in vars(args).items() if k != "check" and v is not None}
    config["python"] = config.get("python") or sys.executable
    for key in ("line_code", "line_weights", "person_weights"):
        if not config.get(key):
            parser.error("--" + key.replace("_", "-") + " is required")
    target = config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    # Never overwrite a working installation implicitly.
    with target.open("x") as stream:
        json.dump(config, stream, indent=2)
    print(json.dumps(status(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
