#!/usr/bin/env bash
# Compile and run each front-end corpus file with reference Carp and Metacarp.
# Require identical observable output for macros, quasiquote, gensym, dynamic
# evaluation, and syntax sugar.
set -u

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_root=$(CDPATH= cd -- "$script_dir/.." && pwd)

# stock macOS has no `timeout`; use it when present, else a perl alarm.
run_limited() {
  secs=$1; shift
  if command -v timeout >/dev/null 2>&1; then
    timeout "$secs" "$@"
  else
    perl -e 'alarm shift @ARGV; exec @ARGV or die "exec: $!"' "$secs" "$@"
  fi
}

compiler=${CARP_COMPILER:-"$repo_root/out/carp-compiler"}
reference=${CARP_REFERENCE:-"$(command -v carp || echo "$HOME/.local/bin/carp")"}
carp_root=${CARP_ROOT:-${CARP_DIR:-"$repo_root/../../carp"}}
core_dir=${CARP_CORE_DIR:-"$carp_root/core"}
out_root=${CARP_DIFF_OUT:-"${TMPDIR:-/tmp}/carp-expansion-diff"}

mkdir -p "$out_root"
passed=0
failed=0

for file in "$repo_root"/test/expansion-corpus/*.carp; do
  name=$(basename "$file" .carp)
  ours_bin="$out_root/$name.self"
  ours_out="$out_root/$name.self.out"
  ref_out="$out_root/$name.ref.out"

  printf '[diff-expansion] %s\n' "$name"

  if ! "$compiler" -b --log-memory -c "$core_dir" -o "$ours_bin" "$file" \
      > "$out_root/$name.self.log" 2>&1; then
    printf 'FAIL %s (self compile)\n' "$name"
    failed=$((failed + 1))
    continue
  fi
  "$ours_bin" > "$ours_out" 2>&1

  if ! (cd "$carp_root" && run_limited 120 "$reference" -x "$file") \
      > "$ref_out" 2> "$out_root/$name.ref.log"; then
    printf 'FAIL %s (reference compile)\n' "$name"
    failed=$((failed + 1))
    continue
  fi

  if diff --strip-trailing-cr "$ours_out" "$ref_out" > "$out_root/$name.diff" 2>&1; then
    passed=$((passed + 1))
  else
    printf 'FAIL %s (output diff, see %s)\n' "$name" "$out_root/$name.diff"
    failed=$((failed + 1))
  fi
done

printf 'diff-expansion: passed=%d failed=%d out=%s\n' "$passed" "$failed" "$out_root"
[ "$failed" -eq 0 ]
