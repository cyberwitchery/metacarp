#!/usr/bin/env bash
# Guard generated-code quality for the array-access regression in n-body.
# Correctness and stable data-pointer materialization gate the script; runtime
# is reported rather than thresholded because shared CI machines are noisy.
set -euo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_root=$(CDPATH= cd -- "$script_dir/.." && pwd)
reference=${CARP_REFERENCE:-carp}
compiler=${CARP_COMPILER:-"$repo_root/out/carp-compiler"}
carp_root=${CARP_ROOT:-${CARP_DIR:-"$repo_root/../../carp"}}
core_dir=${CARP_CORE_DIR:-"$carp_root/core"}
program=${CARP_NBODY_SOURCE:-"$carp_root/examples/benchmark_n-body.carp"}
out_dir=${CARP_NBODY_OUT:-"${TMPDIR:-/tmp}/carp-nbody-codegen"}
runs=${CARP_NBODY_RUNS:-3}

if [[ ! -x "$compiler" ]]; then
  printf 'compiler not executable: %s\n' "$compiler" >&2
  exit 2
fi
if [[ ! -f "$program" || ! -d "$core_dir" ]]; then
  printf 'reference Carp checkout not found under: %s\n' "$carp_root" >&2
  exit 2
fi
if ! [[ "$runs" =~ ^[1-9][0-9]*$ ]]; then
  printf 'CARP_NBODY_RUNS must be a positive integer\n' >&2
  exit 2
fi

mkdir -p "$out_dir"
reference_c="$out_dir/reference.c"
self_c="$out_dir/self.c"
reference_bin="$out_dir/reference"
self_bin="$out_dir/self"
results="$out_dir/results.tsv"

cd "$repo_root"
"$reference" -b --generate-only --optimize "$program" </dev/null >/dev/null
cp out/main.c "$reference_c"
"$compiler" -c "$core_dir" -o "$self_c" "$program"

# This declaration is the material optimization: all unsafe-nth operations in
# the stable loop must index a cached Planet pointer, not reload bodies->data.
if ! grep -Eq 'Planet\* [A-Za-z0-9_]*array_data[A-Za-z0-9_]* = \(Planet\*\).*bodies.*\.data;' "$self_c"; then
  printf 'generated n-body C does not materialize a stable Planet data pointer\n' >&2
  exit 1
fi

clang_flags=(-O3 -D NDEBUG -march=native -I "$repo_root" -I "$core_dir")
clang "${clang_flags[@]}" -o "$reference_bin" "$reference_c" -lm
clang "${clang_flags[@]}" -o "$self_bin" "$self_c" -lm

printf 'compiler\trun\twall_seconds\tuser_seconds\n' >"$results"
expected="$out_dir/expected.out"

measure_runtime() {
  label=$1
  run=$2
  binary=$3
  output="$out_dir/$label-$run.out"
  timing="$out_dir/$label-$run.time"
  /usr/bin/time -p "$binary" >"$output" 2>"$timing"
  wall=$(awk '$1 == "real" { print $2 }' "$timing")
  user=$(awk '$1 == "user" { print $2 }' "$timing")
  printf '%s\t%s\t%s\t%s\n' "$label" "$run" "$wall" "$user" >>"$results"
}

for run in $(seq 1 "$runs"); do
  measure_runtime reference "$run" "$reference_bin"
  if [[ "$run" == "1" ]]; then
    cp "$out_dir/reference-1.out" "$expected"
  else
    cmp "$expected" "$out_dir/reference-$run.out"
  fi
done

for run in $(seq 1 "$runs"); do
  measure_runtime self "$run" "$self_bin"
  cmp "$expected" "$out_dir/self-$run.out"
done

printf '| compiler output | run | wall (s) | user (s) |\n'
printf '|---|---:|---:|---:|\n'
awk -F '\t' 'NR > 1 { printf "| %s | %s | %.2f | %.2f |\n", $1, $2, $3, $4 }' "$results"
printf '\noutput parity: exact\n'
printf 'stable array data pointer: present\n'
printf 'machine-readable results: %s\n' "$results"
