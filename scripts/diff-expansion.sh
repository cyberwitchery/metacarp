#!/usr/bin/env bash
# The anti-a-priori ratchet: every corpus file is compiled and RUN by both the
# reference compiler and this one; observable behavior must agree exactly.
# The corpus exercises the front end (macros, quasiquote, gensym, dynamic
# evaluation, sugar) so a semantic drift in expansion shows up as an output
# diff even while the main suite stays green.
set -u

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_root=$(CDPATH= cd -- "$script_dir/.." && pwd)

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

  if ! (cd "$carp_root" && timeout 120 "$reference" -x "$file") \
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
