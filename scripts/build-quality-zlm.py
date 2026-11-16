#!/usr/bin/env python3
"""Build an isolated ZLM copy with the pinned quality adapter; never activates it."""
from datetime import datetime, timezone
import argparse
import difflib
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import shlex
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent


def check_cpp_standards(commands):
    selected = {}
    for entry in commands:
        name = Path(entry["file"]).name
        if name in ("json_value.cpp", "WebHook.cpp", "RtpSequenceStats.cpp"):
            args = entry.get("arguments") or shlex.split(entry["command"])
            standards = [arg for arg in args if arg.startswith("-std=")]
            selected[name] = standards
            if not standards or standards[-1] not in ("-std=c++11", "-std=gnu++11"):
                raise RuntimeError("Expected C++11 for " + name + ": " + str(standards))
    if len(selected) != 3:
        raise RuntimeError("Missing compiler commands for standard compatibility check")
    return selected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resume", help="Existing build ID, e.g. 20261116T113124Z-4597")
    args = parser.parse_args()
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
            if args.resume and not re.fullmatch(r"[0-9]{8}T[0-9]{6}Z-[0-9]+", args.resume):
                raise RuntimeError("Invalid resume build ID")
            folder = ROOT / "build/zlm-quality" / (args.resume or stamp)
            if not folder.resolve().is_relative_to((ROOT / "build/zlm-quality").resolve()):
                raise RuntimeError("Build directory is outside quality builds")
            source = folder / "source"
            if args.resume:
                if not source.is_dir() or not source.resolve().is_relative_to(folder.resolve()):
                    raise RuntimeError("Resume source missing or outside selected directory")
                for process in Path("/proc").iterdir():
                    if process.name.isdigit():
                        try:
                            executable = (process / "exe").resolve(strict=True)
                        except OSError:
                            continue
                        if executable.is_relative_to(folder.resolve()):
                            raise RuntimeError("Selected build has a running executable; stop it before rebuilding")
                report("Resuming isolated build " + str(folder))
            else:
                report("Copying clean pinned source to " + str(source))
                shutil.copytree(original, source, symlinks=True,
                                ignore=shutil.ignore_patterns(".git", "release", "build", "__pycache__"))
            before = {}
            after = {}
            for change in spec["edits"]:
                path = change["path"]
                if path not in after:
                    before[path] = (original / path).read_text(encoding="utf-8")
                    after[path] = before[path]
                if after[path].count(change["before"]) != 1:
                    raise RuntimeError("Adapter anchor mismatch: " + path)
                after[path] = after[path].replace(change["before"], change["after"], 1)
            # Verify all files we will replace before any resumed-source mutation.
            block = ('\n# MediaGateway isolated quality adapter\n'
                     'target_include_directories(zlmediakit PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/MediaGateway/include")\n')
            legacy_block = block.replace('# MediaGateway isolated quality adapter\n',
                '# MediaGateway isolated quality adapter\ntarget_compile_features(zlmediakit PUBLIC cxx_std_17)\n')
            cmake_base = (original / "src/CMakeLists.txt").read_text(encoding="utf-8")
            extension = source / "src/MediaGateway"
            header = extension / "include/mediagateway/quality/RtpSequenceStats.h"
            module_files = [(ROOT / "include/mediagateway/quality/RtpSequenceStats.h", header),
                            (ROOT / "src/quality/RtpSequenceStats.cpp", extension / "RtpSequenceStats.cpp")]
            if args.resume:
                for path, expected in after.items():
                    if (source / path).read_text(encoding="utf-8") != expected:
                        raise RuntimeError("Resume adapter differs; refusing to overwrite: " + path)
                existing = (source / "src/CMakeLists.txt").read_text(encoding="utf-8")
                if existing not in (cmake_base + block, cmake_base + legacy_block):
                    raise RuntimeError("Resume CMake differs from recognized adapter")
                for src_file, dst_file in module_files:
                    current = src_file.read_text(encoding="utf-8")
                    legacy = current.replace('namespace mediagateway { namespace quality {',
                                             'namespace mediagateway::quality {').replace(
                                             '}} // namespace mediagateway::quality',
                                             '} // namespace mediagateway::quality')
                    if dst_file.read_text(encoding="utf-8") not in (current, legacy):
                        raise RuntimeError("Resume module differs; refusing to overwrite: " + str(dst_file))
            patch = []
            for path, text in after.items():
                patch.extend(difflib.unified_diff(before[path].splitlines(True), text.splitlines(True),
                                                 fromfile="a/" + path, tofile="b/" + path))
                (source / path).write_text(text, encoding="utf-8", newline="\n")
            (evidence / "upstream.patch").write_text("".join(patch), encoding="utf-8")
            header.parent.mkdir(parents=True, exist_ok=True)
            for src_file, dst_file in module_files:
                shutil.copyfile(src_file, dst_file)
            (source / "src/CMakeLists.txt").write_text(cmake_base + block, encoding="utf-8", newline="\n")
            flags = ["ENABLE_SERVER=ON", "ENABLE_PLAYER=ON", "ENABLE_HLS=ON", "ENABLE_MP4=ON",
                     "ENABLE_WEBRTC=OFF", "ENABLE_SRT=OFF", "ENABLE_SCTP=OFF", "ENABLE_PYTHON=OFF",
                     "ENABLE_RTPPROXY=OFF", "ENABLE_FFMPEG=OFF", "ENABLE_TESTS=OFF", "DISABLE_REPORT=ON"]
            build = folder / "cmake"
            run(["cmake", "-S", str(source), "-B", str(build), "-G", "Ninja",
                 "-DCMAKE_BUILD_TYPE=RelWithDebInfo", "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON"] + ["-D" + flag for flag in flags])
            commands = json.loads((build / "compile_commands.json").read_text())
            standards = check_cpp_standards(commands)
            (evidence / "cpp-standards.json").write_text(json.dumps(standards, indent=2) + "\n")
            report("PASS: JsonCpp, WebHook and RTP module all compile as C++11")
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
