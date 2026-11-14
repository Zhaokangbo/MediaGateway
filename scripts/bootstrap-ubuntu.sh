#!/usr/bin/env bash
# Run on Ubuntu 24.04. Default is read-only apart from local log output.
set -Eeuo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="${1:---check}"
case "$MODE" in --check|--install) ;; *) echo "Usage: bash $0 [--check|--install]" >&2; exit 2 ;; esac
LOG_DIR="$ROOT/artifacts/environment/$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -p "$LOG_DIR"
exec > >(tee "$LOG_DIR/check.log") 2>&1
trap 'rc=$?; echo "ERROR: line $LINENO, exit $rc"; exit "$rc"' ERR
if [[ ! -f /etc/os-release ]]; then echo "Ubuntu 24.04 required"; exit 1; fi
. /etc/os-release
if [[ "$ID" != ubuntu || "$VERSION_ID" != 24.04 ]]; then
    echo "Expected Ubuntu 24.04; found $ID $VERSION_ID"; exit 1
fi
echo "UTC: $(date -u --iso-8601=seconds)"
echo "OS: $PRETTY_NAME"
uname -m
getconf _NPROCESSORS_ONLN
free -h
df -h "$ROOT"
PACKAGES=(build-essential cmake ninja-build git pkg-config libssl-dev
          ffmpeg curl jq sysstat python3 ca-certificates)
if [[ "$MODE" == --install ]]; then
    if (( EUID == 0 )); then SUDO=(); else SUDO=(sudo); fi
    "${SUDO[@]}" apt-get update
    echo "Installing dependencies; waiting up to 300 seconds for the dpkg lock if needed."
    if "${SUDO[@]}" apt-get -o DPkg::Lock::Timeout=300 install -y "${PACKAGES[@]}"; then
        echo "Dependency installation completed."
    else
        rc=$?
        echo "BLOCKED: dependency installation failed (exit $rc)."
        echo "If another updater holds the lock, let it finish and retry. Do not delete lock files."
        exit "$rc"
    fi
fi
missing=0
for package in "${PACKAGES[@]}"; do
    if ! dpkg-query -W -f='${Status}\n' "$package" 2>/dev/null | grep -qx 'install ok installed'; then
        echo "MISSING: $package"; missing=1
    fi
done
if (( missing )); then
    echo "BLOCKED: install dependencies with bash scripts/bootstrap-ubuntu.sh --install"
    exit 1
fi
dpkg-query -W -f='${Package}\t${Version}\n' "${PACKAGES[@]}" > "$LOG_DIR/packages.tsv"
git --version
cmake --version
c++ --version
ffmpeg -hide_banner -encoders > "$LOG_DIR/ffmpeg-encoders.txt" 2>&1
if ! grep -q 'libx264' "$LOG_DIR/ffmpeg-encoders.txt"; then
    echo "BLOCKED: FFmpeg libx264 encoder missing"; exit 1
fi
if ! grep -Eq '[[:space:]]aac[[:space:]]' "$LOG_DIR/ffmpeg-encoders.txt"; then
    echo "BLOCKED: FFmpeg AAC encoder missing"; exit 1
fi
echo "Listening TCP sockets (inspect planned ports: 8554, 18554, 18080, 18081, 1935, 11935):"
ss -ltn
echo "PASS: environment prerequisites; source download/build/runtime still untested"
echo "Evidence: $LOG_DIR"

