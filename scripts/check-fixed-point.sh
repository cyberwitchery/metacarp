#!/usr/bin/env bash
# Build generations 2 and 3, require byte-identical C, and smoke the result.
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
smoke_c="$work_dir/hello.c"
smoke_binary="$work_dir/hello"
provenance="$work_dir/bootstrap-provenance.txt"

hash_file() {
  if command -v sha256sum >/dev/null; then
    sha256sum "$1" | awk '{ print $1 }'
  else
    shasum -a 256 "$1" | awk '{ print $1 }'
  fi
}

"$compiler" -c "$core_dir" -o "$gen2_c" "$repo_root/main.carp"

link_flags=(-O3 -D NDEBUG -D_DEFAULT_SOURCE -std=c99 -Wall
  -Werror=typedef-redefinition
  -I "$repo_root" -I "$core_dir")
if [[ "$(uname -s)" == "Darwin" ]]; then
  link_flags+=(-Wl,-stack_size,0x20000000)
fi
clang "${link_flags[@]}" -o "$gen2_compiler" "$gen2_c" -lm

"$gen2_compiler" -c "$core_dir" -o "$gen3_c" "$repo_root/main.carp"
cmp "$gen2_c" "$gen3_c"

"$gen2_compiler" -c "$core_dir" -o "$smoke_c" \
  "$repo_root/examples/hello.carp"
clang "${link_flags[@]}" -o "$smoke_binary" "$smoke_c" -lm
smoke_output=$("$smoke_binary")
if [[ "$smoke_output" != "OK" ]]; then
  printf 'bootstrap smoke expected OK, got: %s\n' "$smoke_output" >&2
  exit 1
fi

revision=$(git -C "$repo_root" rev-parse HEAD 2>/dev/null || printf unknown)
compiler_hash=$(hash_file "$compiler")
fixed_point_hash=$(hash_file "$gen2_c")
{
  printf 'source_revision=%s\n' "$revision"
  printf 'input_compiler=%s\n' "$compiler"
  printf 'input_compiler_sha256=%s\n' "$compiler_hash"
  printf 'fixed_point_c_sha256=%s\n' "$fixed_point_hash"
  printf 'core_dir=%s\n' "$core_dir"
  printf 'smoke=OK\n'
} >"$provenance"

printf 'fixed point: gen2 and gen3 C are byte-identical (%s)\n' \
  "$fixed_point_hash"
printf 'bootstrap smoke: OK\n'
printf 'source revision: %s\n' "$revision"
if ! $cleanup; then
  printf 'bootstrap provenance: %s\n' "$provenance"
fi
