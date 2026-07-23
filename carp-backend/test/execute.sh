#!/usr/bin/env bash
# Runtime execution harness for the self-hosting Carp compiler.
#
# Compiles a real-Core program (test/execute-core.carp) through the compiler,
# links the emitted C against the reference Carp runtime headers, runs it, and
# asserts the process exit code. This is the only test that executes real Core;
# core-declarations.carp only string-matches the emitted C.
#
# Usage: run from the carp-backend/ directory:  bash test/execute.sh
set -u

CORE_HEADERS="${CARP_CORE_HEADERS:-../../../carp/core/}"
OUT_C="test/execution-out.c"
OUT_BIN="test/execution-out"
EXPECTED="${1:-64}"   # expected process exit code (Int.pow 2 6 == 64)

echo "[execute] compiling real Core through the self-hosting compiler..."
STATUS="$(carp -x test/execute-core.carp 2>&1)"
if ! printf '%s' "$STATUS" | grep -q 'COMPILED'; then
  echo "[execute] FAIL: compiler did not emit C"
  printf '%s\n' "$STATUS" | grep -Ei 'ERROR|error' | head
  exit 1
fi

echo "[execute] linking against reference runtime ($CORE_HEADERS)..."
if ! clang -I "$CORE_HEADERS" -o "$OUT_BIN" "$OUT_C" 2> test/execution-clang.log; then
  echo "[execute] FAIL: clang error"
  head test/execution-clang.log
  exit 1
fi

"./$OUT_BIN"
ACTUAL=$?
if [ "$ACTUAL" -eq "$EXPECTED" ]; then
  echo "[execute] PASS: exit $ACTUAL (expected $EXPECTED)"
  exit 0
else
  echo "[execute] FAIL: exit $ACTUAL (expected $EXPECTED)"
  exit 1
fi
