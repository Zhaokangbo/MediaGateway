#!/usr/bin/env python3
"""Build an isolated ZLM copy with the pinned quality adapter; never activates it."""
from datetime import datetime, timezone
import difflib
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + str(os.getpid())
    evidence = ROOT / "artifacts/quality-build" / stamp
    evidence.mkdir(parents=True)
    with (evidence / "build.log").open("w", encoding="utf-8") as log:
        def report(message):
            print(message, flush=True)
            log.write(message + "\n")
            log.flush()

        def run(command):
            report("COMMAND: " + json.dumps(command))
            with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  text=True, errors="replace") as child:
                for line in child.stdout:
                    report(line.rstrip())
                if child.wait():
                    raise RuntimeError("Command failed; inspect build.log")

        try:
            if not sys.platform.startswith("linux"):
                raise RuntimeError("Ubuntu required")
            original = ROOT / "upstream/ZLMediaKit"
            spec = json.loads((ROOT / "integrations/zlm/quality-edits.json").read_text(encoding="utf-8"))
            lock = json.loads((ROOT / "upstream.lock.json").read_text(encoding="utf-8"))
            def git(*args):
                return subprocess.check_output(["git", "-C", str(original), *args], text=True).strip()
            if git("rev-parse", "HEAD") != spec["base_commit"] or spec["base_commit"] != lock["repositories"]["ZLMediaKit"]["commit"]:
                raise RuntimeError("Upstream HEAD/lock differs from adapter baseline")
            if git("status", "--porcelain", "--untracked-files=normal"):
                raise RuntimeError("Upstream has local changes; refusing to copy")
            modules = git("submodule", "status", "--recursive")
            if any(line[:1] in ("-", "+", "U") for line in modules.splitlines()):
                raise RuntimeError("Initialize and verify pinned submodules first")
            for module in lock["submodules"]:
                actual = subprocess.check_output(["git", "-C", str(original / module["path"]), "rev-parse", "HEAD"], text=True).strip()
                if actual != module["commit"]:
                    raise RuntimeError("Submodule differs from lock: " + module["path"])
            jobs = int(os.environ.get("JOBS", "2"))
            if jobs < 1:
                raise RuntimeError("JOBS must be positive")
            folder = ROOT / "build/zlm-quality" / stamp
            source = folder / "source"
            report("Copying clean pinned source to " + str(source))
            shutil.copytree(original, source, symlinks=True,
                            ignore=shutil.ignore_patterns(".git", "release", "build", "__pycache__"))
            before = {}
            after = {}
            for change in spec["edits"]:
                path = change["path"]
                if path not in after:
                    before[path] = (source / path).read_text(encoding="utf-8")
                    after[path] = before[path]
                if after[path].count(change["before"]) != 1:
                    raise RuntimeError("Adapter anchor mismatch: " + path)
                after[path] = after[path].replace(change["before"], change["after"], 1)
            patch = []
            for path, text in after.items():
                patch.extend(difflib.unified_diff(before[path].splitlines(True), text.splitlines(True),
                                                 fromfile="a/" + path, tofile="b/" + path))
                (source / path).write_text(text, encoding="utf-8", newline="\n")
            (evidence / "upstream.patch").write_text("".join(patch), encoding="utf-8")
            extension = source / "src/MediaGateway"
            header = extension / "include/mediagateway/quality/RtpSequenceStats.h"
            header.parent.mkdir(parents=True)
            shutil.copyfile(ROOT / "include/mediagateway/quality/RtpSequenceStats.h", header)
            shutil.copyfile(ROOT / "src/quality/RtpSequenceStats.cpp", extension / "RtpSequenceStats.cpp")
            with (source / "src/CMakeLists.txt").open("a", encoding="utf-8") as file:
                file.write('\n# MediaGateway isolated quality adapter\n'
                           'target_compile_features(zlmediakit PUBLIC cxx_std_17)\n'
                           'target_include_directories(zlmediakit PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/MediaGateway/include")\n')
            flags = ["ENABLE_SERVER=ON", "ENABLE_PLAYER=ON", "ENABLE_HLS=ON", "ENABLE_MP4=ON",
                     "ENABLE_WEBRTC=OFF", "ENABLE_SRT=OFF", "ENABLE_SCTP=OFF", "ENABLE_PYTHON=OFF",
                     "ENABLE_RTPPROXY=OFF", "ENABLE_FFMPEG=OFF", "ENABLE_TESTS=OFF", "DISABLE_REPORT=ON"]
            build = folder / "cmake"
            run(["cmake", "-S", str(source), "-B", str(build), "-G", "Ninja",
                 "-DCMAKE_BUILD_TYPE=RelWithDebInfo", "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON"] + ["-D" + flag for flag in flags])
            run(["cmake", "--build", str(build), "--target", "MediaServer", "--parallel", str(jobs)])
            binary = source / "release/linux/RelWithDebInfo/MediaServer"
            if not binary.is_file() or not os.access(binary, os.X_OK):
                raise RuntimeError("Expected MediaServer output is missing")
            inputs = ["integrations/zlm/quality-edits.json", "include/mediagateway/quality/RtpSequenceStats.h",
                      "src/quality/RtpSequenceStats.cpp", "scripts/build-quality-zlm.py"]
            manifest = dict(base_commit=spec["base_commit"], binary=str(binary.resolve()),
                            binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
                            inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
                            submodules=modules.splitlines(), evidence=str(evidence))
            (evidence / "build-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
            runtime = ROOT / "runtime/builds"
            runtime.mkdir(parents=True, exist_ok=True)
            temporary = runtime / (stamp + ".json")
            temporary.write_text(json.dumps(manifest, indent=2) + "\n")
            os.replace(temporary, runtime / "latest-quality.json")
            report("PASS: isolated quality MediaServer compiled; NOT ACTIVATED")
            report("NOT TESTED: live packets, API, protocol regression")
            report("Evidence: " + str(evidence))
            return 0
        except Exception as ex:
            report("FAIL: " + str(ex))
            report("Evidence: " + str(evidence))
            return 1


if __name__ == "__main__":
    sys.exit(main())
