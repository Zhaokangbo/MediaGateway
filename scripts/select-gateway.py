#!/usr/bin/env python3
"""Select a built gateway while stopped. Source always remains on the baseline."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from instances import ROOT, proc_info


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("variant", choices=("original", "quality"))
    args = parser.parse_args()
    if not sys.platform.startswith("linux"):
        parser.error("Ubuntu required")
    import fcntl
    runtime = ROOT / "runtime"
    runtime.mkdir(exist_ok=True)
    with (runtime / "control.lock").open("a") as guard:
        fcntl.flock(guard, fcntl.LOCK_EX)
        folder = runtime / "gateway"
        folder.mkdir(exist_ok=True)
        state = folder / "process.json"
        if state.exists() and proc_info(json.loads(state.read_text())["pid"]):
            raise RuntimeError("Stop the gateway first: bash scripts/stop.sh gateway")
        selection = folder / "binary-path.txt"
        if args.variant == "original":
            selection.unlink(missing_ok=True)
        else:
            manifest = json.loads((runtime / "builds/latest-quality.json").read_text())
            binary = Path(manifest["binary"]).resolve(strict=True)
            if not binary.is_relative_to((ROOT / "build/zlm-quality").resolve()) or not os.access(binary, os.X_OK):
                raise RuntimeError("Invalid quality binary path")
            if hashlib.sha256(binary.read_bytes()).hexdigest() != manifest["binary_sha256"]:
                raise RuntimeError("Quality binary hash differs from build manifest")
            selection.write_text(str(binary) + "\n")
        print("Selected gateway variant: " + args.variant + "; start it with scripts/start.sh gateway")


if __name__ == "__main__":
    main()
