#!/usr/bin/env bash
# Build generations 2 and 3 and require their generated C to be identical.
set -euo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_root=$(CDPATH= cd -- "$script_dir/.." && pwd)
compiler=${CARP_COMPILER:-"$repo_root/out/carp-compiler"}
carp_root=${CARP_ROOT:-${CARP_DIR:-"$repo_root/../../carp"}}
core_dir=${CARP_CORE_DIR:-"$carp_root/core"}
work_dir=${CARP_FIXED_POINT_OUT:-}

if [[ ! -x "$compiler" ]]; then
  printf 'compiler not executable: %s\n' "$compiler" >&2
  exit 2
fi
if [[ ! -d "$core_dir" ]]; then
  printf 'Carp core not found: %s\n' "$core_dir" >&2
  exit 2
fi

cleanup=false
if [[ -z "$work_dir" ]]; then
  work_dir=$(mktemp -d "${TMPDIR:-/tmp}/carp-fixed-point.XXXXXX")
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

if [[ "$(uname -s)" == "Linux" ]]; then
  ulimit -s 524288
fi

gen2_c="$work_dir/gen2.c"
gen2_compiler="$work_dir/carp-compiler-gen2"
gen3_c="$work_dir/gen3.c"

"$compiler" -c "$core_dir" -o "$gen2_c" "$repo_root/main.carp"

link_flags=(-O2 -I "$repo_root" -I "$core_dir")
if [[ "$(uname -s)" == "Darwin" ]]; then
  link_flags+=(-Wl,-stack_size,0x20000000)
fi
clang "${link_flags[@]}" -o "$gen2_compiler" "$gen2_c" -lm

"$gen2_compiler" -c "$core_dir" -o "$gen3_c" "$repo_root/main.carp"
cmp "$gen2_c" "$gen3_c"
printf 'fixed point: gen2 and gen3 C are byte-identical\n'
