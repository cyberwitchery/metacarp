#!/usr/bin/env bash
# Run every compiler-phase test against the reference Carp compiler.
# Keep this as the single source of truth for the phase suite: CI and local
# assurance both call this script.
set -euo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_root=$(CDPATH= cd -- "$script_dir/.." && pwd)
reference=${CARP_REFERENCE:-carp}
core_dir=${CARP_PHASE_CORE:-}
jobs=${CARP_PHASE_JOBS:-1}
log_memory=${CARP_PHASE_LOG_MEMORY:-1}
memory_tests=${CARP_PHASE_MEMORY_TESTS:-1}

compiler_args=()
if [[ -n "$core_dir" ]]; then
  compiler_args=(-c "$core_dir")
fi

if [[ "$(uname -s)" == "Linux" ]]; then
  ulimit -s 524288
fi

run_phase_test() {
  test_dir=$1
  test_file=$2
  mode=$3
  work_dir=$(mktemp -d "${TMPDIR:-/tmp}/carp-phase-test.XXXXXX")
  (
    trap 'rm -rf "$work_dir"' EXIT
    if [[ "$test_dir" == . ]]; then
      find "$repo_root" -mindepth 1 -maxdepth 1 ! -name out \
        -exec ln -s {} "$work_dir/" \;
      cd "$work_dir"
    else
      mkdir -p "$work_dir/$test_dir"
      find "$repo_root" -mindepth 1 -maxdepth 1 \
        ! -name out ! -name "$test_dir" -exec ln -s {} "$work_dir/" \;
      find "$repo_root/$test_dir" -mindepth 1 -maxdepth 1 ! -name out \
        -exec ln -s {} "$work_dir/$test_dir/" \;
      cd "$work_dir/$test_dir"
    fi
    printf '== %s/%s\n' "$test_dir" "$test_file"
    if [[ "$mode" == memory && "$log_memory" == 1 ]]; then
      "$reference" "${compiler_args[@]}" -x --log-memory "$test_file"
    else
      "$reference" "${compiler_args[@]}" -x "$test_file"
    fi
  )
}

# xargs invokes one fresh script process per task. Each task owns its working
# directory and therefore its `out/Untitled`; the scheduler can distribute the
# expensive compiler/session tests without introducing output races.
if [[ "${1:-}" == --task ]]; then
  if [[ "$#" -ne 4 ]]; then
    printf 'internal usage: %s --task <dir> <file> <normal|memory>\n' "$0" >&2
    exit 2
  fi
  run_phase_test "$2" "$3" "$4"
  exit
fi

emit_task() {
  printf '%s\0%s\0%s\0' "$1" "$2" "$3"
}

phase_tasks() {
  # Start the four heaviest tasks first so the worker pool does not finish
  # small module tests and leave one long session test as a serial tail.
  emit_task . test/carp-compiler.carp normal
  emit_task . carp-session/test/carp-session.carp normal
  emit_task . carp-session/test/core.carp normal
  if [[ "$memory_tests" == 1 ]]; then
    emit_task . carp-session/test/memory.carp memory
  fi

  for directory in \
    carp-graph carp-c-abi carp-primitives carp-module carp-ct-env \
    carp-ct-eval carp-ir carp-resolve carp-types carp-infer carp-specialize \
    carp-ownership carp-backend carp-expand
  do
    for test_file in "$repo_root/$directory"/test/*.carp; do
      emit_task "$directory" "${test_file#"$repo_root/$directory/"}" normal
    done
  done
}

case "$jobs" in
  1|2|3) ;;
  *)
    printf 'CARP_PHASE_JOBS must be 1, 2, or 3, got %s\n' "$jobs" >&2
    exit 2
    ;;
esac

# Carp's package cache is not safe for concurrent first installs. Run the
# smallest carp-reader consumer before opening the worker pool; this is already
# part of the suite, so the warm-up adds no duplicate compilation work.
run_phase_test carp-surface test/carp-surface.carp normal

if ! phase_tasks \
  | xargs -0 -n 3 -P "$jobs" "$script_dir/run-phase-suites.sh" --task
then
  printf 'phase suites failed\n' >&2
  exit 1
fi
