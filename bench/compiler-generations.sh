#!/usr/bin/env bash
# Compare the reference compiler and two self-hosted generations on the same
# workload: generating C for this compiler. Linking generations is setup work
# and is deliberately excluded from the measurements.
set -euo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_root=$(CDPATH= cd -- "$script_dir/.." && pwd)
reference=${CARP_REFERENCE:-carp}
carp_root=${CARP_ROOT:-${CARP_DIR:-"$repo_root/../../carp"}}
core_dir=${CARP_CORE_DIR:-"$carp_root/core"}
out_dir=${CARP_BENCH_OUT:-"${TMPDIR:-/tmp}/carp-generation-bench"}
runs=${CARP_BENCH_RUNS:-1}

if [[ ! -d "$core_dir" ]]; then
  printf 'Carp core not found: %s\n' "$core_dir" >&2
  exit 2
fi
if ! [[ "$runs" =~ ^[1-9][0-9]*$ ]]; then
  printf 'CARP_BENCH_RUNS must be a positive integer\n' >&2
  exit 2
fi

mkdir -p "$out_dir/log"
results="$out_dir/results.tsv"
printf 'generation\trun\twall_seconds\tuser_seconds\tmax_rss_kib\n' >"$results"

measure() {
  generation=$1
  run=$2
  shift 2
  log="$out_dir/log/$generation-$run.log"
  metrics="$out_dir/log/$generation-$run.time"

  if [[ "$(uname -s)" == "Darwin" ]]; then
    /usr/bin/time -l "$@" </dev/null >"$log" 2>"$metrics"
    wall=$(awk '/ real / { print $1; exit }' "$metrics")
    user=$(awk '/ user / { print $3; exit }' "$metrics")
    rss_bytes=$(awk '/maximum resident set size/ { print $1; exit }' "$metrics")
    rss_kib=$((rss_bytes / 1024))
  else
    /usr/bin/time -f '__CARP_BENCH__\t%e\t%U\t%M' "$@" </dev/null >"$log" 2>"$metrics"
    row=$(grep '^__CARP_BENCH__' "$metrics")
    wall=$(printf '%s\n' "$row" | cut -f2)
    user=$(printf '%s\n' "$row" | cut -f3)
    rss_kib=$(printf '%s\n' "$row" | cut -f4)
  fi

  printf '%s\t%s\t%s\t%s\t%s\n' \
    "$generation" "$run" "$wall" "$user" "$rss_kib" >>"$results"
}

build_compiler() {
  source_c=$1
  binary=$2
  flags=(-O3 -D NDEBUG -I "$repo_root" -I "$core_dir")
  if [[ "$(uname -s)" == "Darwin" ]]; then
    flags+=(-Wl,-stack_size,0x20000000)
  fi
  clang "${flags[@]}" -o "$binary" "$source_c" -lm
}

cd "$repo_root"
printf 'benchmark revision: %s\n' "$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
printf 'runs per generation: %s\n' "$runs"
printf 'output: %s\n' "$out_dir"

# The last run's generated C becomes the input used to link the next compiler.
for run in $(seq 1 "$runs"); do
  measure reference "$run" "$reference" -b --generate-only --optimize main.carp
  cp out/main.c "$out_dir/gen1.c"
done
build_compiler "$out_dir/gen1.c" "$out_dir/carp-compiler-gen1"

for run in $(seq 1 "$runs"); do
  measure gen1 "$run" "$out_dir/carp-compiler-gen1" \
    -c "$core_dir" -o "$out_dir/gen2.c" main.carp
done
build_compiler "$out_dir/gen2.c" "$out_dir/carp-compiler-gen2"

for run in $(seq 1 "$runs"); do
  measure gen2 "$run" "$out_dir/carp-compiler-gen2" \
    -c "$core_dir" -o "$out_dir/gen3.c" main.carp
done

cmp "$out_dir/gen2.c" "$out_dir/gen3.c"

printf '\n| compiler | run | wall (s) | user (s) | max RSS (MiB) |\n'
printf '|---|---:|---:|---:|---:|\n'
awk -F '\t' 'NR > 1 { printf "| %s | %s | %.2f | %.2f | %.1f |\n", $1, $2, $3, $4, $5 / 1024 }' "$results"
printf '\nfixed point: gen2 and gen3 C are byte-identical\n'
printf 'machine-readable results: %s\n' "$results"
