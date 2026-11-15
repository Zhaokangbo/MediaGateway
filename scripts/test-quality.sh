#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT/artifacts/quality/$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -p "$OUT"
exec > >(tee "$OUT/test.log") 2>&1
trap 'rc=$?; echo "FAIL: quality test line $LINENO, exit $rc; Evidence: $OUT"; exit "$rc"' ERR
echo "UTC: $(date -u --iso-8601=seconds)"
c++ --version
cmake --version
cmake -S "$ROOT" -B "$ROOT/build/quality" -DCMAKE_BUILD_TYPE=RelWithDebInfo -DBUILD_TESTING=ON
cmake --build "$ROOT/build/quality" --parallel 2
ctest --test-dir "$ROOT/build/quality" -V
echo "PASS: standalone C++ sequence statistics"
echo "NOT TESTED: live RTP integration, API export, upstream regression, performance"
echo "Evidence: $OUT"
