#!/usr/bin/env bash
# Does not install packages, change proxies, start services, or overwrite dirty sources.
set -Eeuo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ "${1:-}" == --help ]]; then
    echo "Usage: bash scripts/build-zlm.sh (optional JOBS=2)"; exit 0
fi
if (( $# )); then echo "Unexpected arguments" >&2; exit 2; fi
bash "$ROOT/scripts/bootstrap-ubuntu.sh" --check
LOG_DIR="$ROOT/artifacts/build/$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -p "$LOG_DIR" "$ROOT/upstream"
exec > >(tee "$LOG_DIR/build.log") 2>&1
trap 'rc=$?; echo "FAIL: build line $LINENO, exit $rc; evidence: $LOG_DIR"; exit "$rc"' ERR
LOCK="$ROOT/upstream.lock.json"
URL="$(jq -er '.repositories.ZLMediaKit.url' "$LOCK")"
REV="$(jq -er '.repositories.ZLMediaKit.commit' "$LOCK")"
[[ "$REV" =~ ^[0-9a-f]{40}$ ]] || { echo "Invalid locked revision"; exit 1; }
SRC="$ROOT/upstream/ZLMediaKit"
BUILD="$ROOT/build/zlm-${REV:0:12}"
JOBS="${JOBS:-2}"
[[ "$JOBS" =~ ^[1-9][0-9]*$ ]] || { echo "JOBS must be positive integer"; exit 1; }
cp "$LOCK" "$LOG_DIR/upstream.lock.json"
if [[ ! -e "$SRC" ]]; then
    git clone --no-checkout "$URL" "$SRC"
    git -C "$SRC" checkout --detach "$REV"
else
    [[ -d "$SRC/.git" || -f "$SRC/.git" ]] || { echo "Existing source is not a Git checkout: $SRC"; exit 1; }
    if [[ -n "$(git -C "$SRC" status --porcelain --untracked-files=normal)" ]]; then
        echo "Refusing to modify dirty source checkout: $SRC"; exit 1
    fi
    [[ "$(git -C "$SRC" rev-parse HEAD)" == "$REV" ]] || {
        echo "Existing checkout differs from lock; inspect it manually before continuing"; exit 1;
    }
fi
git -C "$SRC" submodule update --init --recursive
git -C "$SRC" submodule status --recursive | tee "$LOG_DIR/submodules.txt"
if grep -Eq '^[-+U]' "$LOG_DIR/submodules.txt"; then
    echo "Submodule revision mismatch"; exit 1
fi
if [[ -n "$(git -C "$SRC" status --porcelain --untracked-files=normal)" ]]; then
    echo "Source or submodule is dirty; refusing build"; exit 1
fi
python3 - "$LOCK" "$SRC" "$LOG_DIR/source-manifest.json" <<'PY'
import json, subprocess, sys
from pathlib import Path
lock = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
src = Path(sys.argv[2])
def git(*args):
    return subprocess.check_output(["git", "-C", str(src), *args], text=True).strip()
assert git("rev-parse", "HEAD") == lock["repositories"]["ZLMediaKit"]["commit"]
for module in lock["submodules"]:
    path = module["path"]
    actual = subprocess.check_output(
        ["git", "-C", str(src / path), "rev-parse", "HEAD"], text=True).strip()
    if actual != module["commit"]:
        raise SystemExit(f"Locked submodule mismatch: {path}")
manifest = {
    "zlm_commit": git("rev-parse", "HEAD"),
    "submodules_recursive": git("submodule", "status", "--recursive").splitlines(),
    "scope": "resolved checkout; does not lock OS packages",
}
Path(sys.argv[3]).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
PY
cmake -S "$SRC" -B "$BUILD" -G Ninja \
    -DCMAKE_BUILD_TYPE=RelWithDebInfo \
    -DENABLE_SERVER=ON -DENABLE_PLAYER=ON \
    -DENABLE_HLS=ON -DENABLE_MP4=ON \
    -DENABLE_WEBRTC=OFF -DENABLE_SRT=OFF -DENABLE_SCTP=OFF \
    -DENABLE_PYTHON=OFF -DENABLE_RTPPROXY=OFF \
    -DENABLE_FFMPEG=OFF -DENABLE_TESTS=OFF -DDISABLE_REPORT=ON \
    -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
cp "$BUILD/CMakeCache.txt" "$LOG_DIR/CMakeCache.txt"
cmake --build "$BUILD" --target MediaServer --parallel "$JOBS"
# ZLM may place its executable in release/ rather than the CMake build directory.
mapfile -t CANDIDATES < <(find "$SRC/release" "$BUILD" -type f -name MediaServer -executable 2>/dev/null | sort -u)
if (( ${#CANDIDATES[@]} != 1 )); then
    printf 'Expected exactly one MediaServer; found %s. Inspect build log.\n' "${#CANDIDATES[@]}"
    printf '%s\n' "${CANDIDATES[@]}"; exit 1
fi
BIN="${CANDIDATES[0]}"
sha256sum "$BIN" | tee "$LOG_DIR/binary.sha256"
printf '%s\n' "$BIN" > "$LOG_DIR/binary-path.txt"
echo "PASS: MediaServer target compiled"
echo "NOT TESTED: server startup, API, RTSP input, playback, reconnection"
echo "Binary: $BIN"
echo "Evidence: $LOG_DIR"

