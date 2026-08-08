#!/usr/bin/env bash
# Run every compiler-phase test against the reference Carp compiler.
# Keep this as the single source of truth for the phase suite: CI and local
# assurance both call this script.
set -euo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_root=$(CDPATH= cd -- "$script_dir/.." && pwd)
reference=${CARP_REFERENCE:-carp}

if [[ "$(uname -s)" == "Linux" ]]; then
  ulimit -s 524288
fi

run_phase_test() {
  # Carp's default executable path is relative to the current directory.
  # Remove it so a failed compile cannot execute a stale test artifact.
  rm -rf out
  "$reference" -x "$1"
}

cd "$repo_root"

for directory in \
  carp-graph carp-c-abi carp-primitives carp-surface carp-module carp-ct-env \
  carp-ct-eval carp-ir carp-resolve carp-types carp-infer carp-specialize carp-backend \
  carp-expand
do
  (
    cd "$directory"
    for test_file in test/*.carp; do
      printf '== %s/%s\n' "$directory" "$test_file"
      run_phase_test "$test_file"
    done
  )
done

run_phase_test test/carp-compiler.carp
run_phase_test carp-session/test/carp-session.carp
run_phase_test carp-session/test/core.carp
rm -rf out
"$reference" -x --log-memory carp-session/test/memory.carp
