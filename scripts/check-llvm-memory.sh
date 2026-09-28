#!/usr/bin/env bash
# Run the LLVM backend's memory fixtures under both drivers.
#
# Each fixture in carp-llvm-backend/test/memory is built with --log-memory by
# the C driver and by the LLVM driver. A fixture exits non-zero when its own
# Debug.memory-balance check fails, and both drivers must print the same
# output, so a delete one backend places and the other drops fails here (#79).
set -euo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_root=$(CDPATH= cd -- "$script_dir/.." && pwd)
c_compiler=${CARP_COMPILER:-"$repo_root/out/carp-compiler"}
llvm_compiler=${CARP_LLVM_COMPILER:-"$repo_root/out/carp-compiler-llvm"}
carp_root=${CARP_ROOT:-${CARP_DIR:-"$repo_root/../../carp"}}
core_dir=${CARP_CORE_DIR:-"$carp_root/core"}
fixture_dir="$repo_root/carp-llvm-backend/test/memory"

for compiler in "$c_compiler" "$llvm_compiler"; do
  if [[ ! -x "$compiler" ]]; then
    printf 'compiler not executable: %s\n' "$compiler" >&2
    exit 2
  fi
done
if [[ ! -d "$core_dir" ]]; then
  printf 'Carp core not found: %s\n' "$core_dir" >&2
  exit 2
fi

work_dir=$(mktemp -d "${TMPDIR:-/tmp}/carp-llvm-memory.XXXXXX")
trap 'rm -rf "$work_dir"' EXIT

failed=0
for fixture in "$fixture_dir"/*.carp; do
  name=$(basename "$fixture" .carp)
  for lane in c llvm; do
    if [[ "$lane" == c ]]; then compiler=$c_compiler; else compiler=$llvm_compiler; fi
    # -x builds into ./out, so each lane gets its own directory
    mkdir -p "$work_dir/$lane"
    # the programs' output is compared; the build's diagnostics (clang
    # warnings naming each driver's own temporary file) go to stderr apart
    if (cd "$work_dir/$lane" \
      && "$compiler" -c "$core_dir" -x --log-memory "$fixture") \
      >"$work_dir/$name.$lane.out" 2>"$work_dir/$name.$lane.err"
    then
      printf '[ok]   %s (%s)\n' "$name" "$lane"
    else
      printf '[fail] %s (%s)\n' "$name" "$lane"
      sed 's/^/       /' "$work_dir/$name.$lane.err" "$work_dir/$name.$lane.out"
      failed=1
    fi
  done
  if ! diff -u "$work_dir/$name.c.out" "$work_dir/$name.llvm.out" \
    >"$work_dir/$name.diff"
  then
    printf '[fail] %s: the drivers disagree\n' "$name"
    sed 's/^/       /' "$work_dir/$name.diff"
    failed=1
  fi
done

exit "$failed"
