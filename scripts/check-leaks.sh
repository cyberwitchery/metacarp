#!/usr/bin/env bash
# Require the self-built compiler to free what it allocates.
#
# The generation-2 compiler is the one we ship, so it is the one measured: a
# codegen bug that drops a delete shows up here and nowhere else, because the
# generation-1 binary is built by the reference compiler and inherits the
# reference's cleanup. Process-lifetime globals are never freed, so the gate
# is a byte budget rather than a demand for zero.
#
# `leaks` is macOS-only; elsewhere this exits successfully without measuring.
set -euo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_root=$(CDPATH= cd -- "$script_dir/.." && pwd)
compiler=${CARP_COMPILER:-"$repo_root/out/carp-compiler"}
carp_root=${CARP_ROOT:-${CARP_DIR:-"$repo_root/../../carp"}}
core_dir=${CARP_CORE_DIR:-"$carp_root/core"}
fixture=${CARP_LEAK_FIXTURE:-"$carp_root/test/map.carp"}
budget=${CARP_LEAK_BUDGET:-200000}
work_dir=${CARP_FIXED_POINT_OUT:-}

if [[ "$(uname -s)" != "Darwin" ]]; then
  printf 'leak check skipped: leaks(1) is macOS-only\n'
  exit 0
fi
if ! command -v leaks >/dev/null; then
  printf 'leak check skipped: leaks(1) not found\n'
  exit 0
fi
if [[ ! -d "$core_dir" ]]; then
  printf 'Carp core not found: %s\n' "$core_dir" >&2
  exit 2
fi
# A missing fixture makes the compiler exit before it allocates anything, which
# reads as a clean run. Fail instead of measuring nothing.
if [[ ! -f "$fixture" ]]; then
  printf 'leak fixture not found: %s\n' "$fixture" >&2
  exit 2
fi

cleanup=false
if [[ -z "$work_dir" ]]; then
  work_dir=$(mktemp -d "${TMPDIR:-/tmp}/carp-leaks.XXXXXX")
  cleanup=true
else
  mkdir -p "$work_dir"
fi

cleanup_work_dir() {
  if $cleanup; then
    rm -rf "$work_dir"
  fi
}
trap cleanup_work_dir EXIT

# check-fixed-point.sh leaves its generation-2 binary here when both scripts
# share a work directory; building it again would double the slowest step.
gen2_compiler="$work_dir/carp-compiler-gen2"
if [[ ! -x "$gen2_compiler" ]]; then
  if [[ ! -x "$compiler" ]]; then
    printf 'compiler not executable: %s\n' "$compiler" >&2
    exit 2
  fi
  "$compiler" -c "$core_dir" -o "$work_dir/gen2.c" "$repo_root/main.carp"
  clang -O2 -I "$repo_root" -I "$core_dir" -Wl,-stack_size,0x20000000 \
    -o "$gen2_compiler" "$work_dir/gen2.c" -lm
fi

report="$work_dir/leaks.txt"
fixture_c="$work_dir/fixture.c"
set +e
leaks --atExit -- "$gen2_compiler" -c "$core_dir" -o "$fixture_c" \
  "$fixture" >"$report" 2>"$work_dir/fixture.err"
set -e

# The budget only means something if the compile it measures actually ran.
if [[ ! -s "$fixture_c" ]]; then
  printf 'leak check failed: %s produced no C\n' "$(basename "$fixture")" >&2
  tail -5 "$work_dir/fixture.err" >&2
  exit 2
fi

summary=$(grep -E '[0-9]+ leaks for [0-9]+ total leaked bytes' "$report" | tail -1)
if [[ -z "$summary" ]]; then
  printf 'leak check failed: no summary in leaks(1) output\n' >&2
  tail -20 "$report" >&2
  exit 2
fi

leaked=$(printf '%s\n' "$summary" | sed -E 's/.*leaks for ([0-9]+) total.*/\1/')
printf 'leaks: %s bytes (budget %s) compiling %s\n' \
  "$leaked" "$budget" "$(basename "$fixture")"

if [[ "$leaked" -gt "$budget" ]]; then
  printf 'leak budget exceeded\n' >&2
  grep -E 'ROOT LEAK' "$report" | sed 's/.*ROOT LEAK: //' | sort | uniq -c |
    sort -rn | head -10 >&2
  exit 1
fi
