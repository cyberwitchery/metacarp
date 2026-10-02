#!/usr/bin/env bash
# The canonical local and CI assurance entry point.
#
#   run-assurance.sh bootstrap  only build generation 1 (out/carp-compiler)
#   run-assurance.sh phase  lint and formatting, then the phase suites
#                           through generation 2
#   run-assurance.sh self   reference suite, fixed point, leaks, expansion,
#                           library linkage
#   run-assurance.sh sanitize  the reference suite again, every generated
#                           program built with AddressSanitizer
#   run-assurance.sh llvm   the LLVM backend's tests and its memory fixtures
#                           under both drivers (needs libLLVM, see LLVM.setup)
#   run-assurance.sh all    phase and self (not sanitize or llvm, which CI
#                           runs as their own jobs)
#
# Everything is built by this compiler, not the reference: generation 1 comes
# from a seed, a compiler an earlier build of this repository produced
# (CARP_SEED_COMPILER, else the out/carp-compiler already here). Only with no
# seed, or one too old to build the current source, is generation 1 built
# through the reference, once. The reference itself stays for what compares
# against it: the expansion diff and the generation benchmark.
set -euo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_root=$(CDPATH= cd -- "$script_dir/.." && pwd)
group=${1:-all}
reference=${CARP_REFERENCE:-carp}
carp_root=${CARP_ROOT:-${CARP_DIR:-"$repo_root/../../carp"}}
core_dir=${CARP_CORE_DIR:-"$carp_root/core"}
compiler="$repo_root/out/carp-compiler"

if [[ "$(uname -s)" == "Linux" ]]; then
  ulimit -s 524288
fi

run_style_checks() {
  if [[ "${CARP_SKIP_STYLE:-0}" == "1" ]]; then
    printf 'style checks skipped (CARP_SKIP_STYLE=1)\n'
    return
  fi
  command -v angler >/dev/null || {
    printf 'angler is required (or set CARP_SKIP_STYLE=1)\n' >&2
    exit 2
  }
  command -v carp-fmt >/dev/null || {
    printf 'carp-fmt is required (or set CARP_SKIP_STYLE=1)\n' >&2
    exit 2
  }

  mapfile_supported=false
  if [[ "$(type -t mapfile || true)" == "builtin" ]]; then
    mapfile_supported=true
  fi
  if $mapfile_supported; then
    mapfile -d '' carp_files < <(find . -name '*.carp' -not -path '*/out/*' -print0)
    angler "${carp_files[@]}"
    carp-fmt --check "${carp_files[@]}"
  else
    # macOS ships Bash 3.2, which has no mapfile. Carp filenames in this
    # repository contain no whitespace, so word splitting is safe here.
    # shellcheck disable=SC2046
    angler $(find . -name '*.carp' -not -path '*/out/*')
    # shellcheck disable=SC2046
    carp-fmt --check $(find . -name '*.carp' -not -path '*/out/*')
  fi
}

bootstrapped=false

# Build generation 1 from the current source, once per run.
bootstrap() {
  if $bootstrapped; then
    return
  fi
  cd "$repo_root"
  mkdir -p out
  seed=${CARP_SEED_COMPILER:-}
  seed_copy=
  if [[ -z "$seed" && -x "$compiler" ]]; then
    # the build replaces out/carp-compiler, so the seed runs from a copy
    seed_copy=$(mktemp "${TMPDIR:-/tmp}/carp-seed.XXXXXX")
    cp "$compiler" "$seed_copy"
    seed=$seed_copy
  fi
  if [[ -n "$seed" && -x "$seed" ]] \
    && "$seed" -c "$core_dir" --optimize -b -o out/carp-compiler.next main.carp
  then
    mv out/carp-compiler.next "$compiler"
  else
    printf 'no seed compiler could build the current source; building generation 1 through the reference\n' >&2
    "$reference" -b --optimize main.carp
  fi
  if [[ -n "$seed_copy" ]]; then
    rm -f "$seed_copy"
  fi
  bootstrapped=true
}

# Build and check generation 2 into $1. With CARP_FIXED_POINT_REUSE=1, a
# directory that already holds a passed check of this revision is kept instead:
# CI hands one job's generation 2 to the next. It is opt-in because a revision
# does not name uncommitted changes, so only a clean checkout may reuse.
fixed_point() {
  provenance="$1/bootstrap-provenance.txt"
  if [[ "${CARP_FIXED_POINT_REUSE:-0}" == "1" && -f "$provenance" \
    && -x "$1/carp-compiler-gen2" ]] \
    && grep -qx "source_revision=$(git -C "$repo_root" rev-parse HEAD)" \
      "$provenance"
  then
    printf 'fixed point: reusing the check in %s\n' "$1"
    return
  fi
  CARP_FIXED_POINT_OUT="$1" "$script_dir/check-fixed-point.sh"
}

run_phase() {
  (
    cd "$repo_root"
    run_style_checks
  )
  bootstrap
  # the phase suites run through generation 2, this source compiled by itself;
  # CARP_FIXED_POINT_OUT keeps it for a later group in the same job
  phase_work=${CARP_FIXED_POINT_OUT:-}
  if [[ -z "$phase_work" ]]; then
    phase_work=$(mktemp -d "${TMPDIR:-/tmp}/carp-phase.XXXXXX")
  fi
  fixed_point "$phase_work"
  CARP_REFERENCE="$phase_work/carp-compiler-gen2" CARP_PHASE_CORE="$core_dir" \
    "$script_dir/run-phase-suites.sh"
  if [[ -z "${CARP_FIXED_POINT_OUT:-}" ]]; then
    rm -rf "$phase_work"
  fi
}

run_self() {
  bootstrap
  cd "$repo_root"
  "$script_dir/run-carp-suite-self.sh"
  # Both checks want a generation-2 compiler; share one work directory so it
  # is built once. A caller-supplied CARP_FIXED_POINT_OUT is kept afterwards.
  self_work=${CARP_FIXED_POINT_OUT:-}
  if [[ -z "$self_work" ]]; then
    self_work=$(mktemp -d "${TMPDIR:-/tmp}/carp-self.XXXXXX")
    trap 'rm -rf "$self_work"' EXIT
  fi
  fixed_point "$self_work"
  CARP_FIXED_POINT_OUT="$self_work" "$script_dir/check-leaks.sh"
  if [[ -z "${CARP_FIXED_POINT_OUT:-}" ]]; then
    rm -rf "$self_work"
    trap - EXIT
  fi
  "$script_dir/diff-expansion.sh"
  "$script_dir/check-library-linkage.sh"
}

run_sanitize() {
  bootstrap
  cd "$repo_root"
  CARP_SELF_SANITIZE=1 "$script_dir/run-carp-suite-self.sh"
}

run_llvm() {
  bootstrap
  cd "$repo_root"
  "$compiler" -c "$core_dir" --optimize -b -o out/carp-compiler-llvm main-llvm.carp
  # the backend's own tests resolve their fixtures relative to its directory
  (
    cd carp-llvm-backend
    "$compiler" -c "$core_dir" -x test/carp-llvm-backend.carp
  )
  "$script_dir/check-llvm-memory.sh"
}

case "$group" in
  bootstrap) bootstrap ;;
  phase) run_phase ;;
  self) run_self ;;
  sanitize) run_sanitize ;;
  llvm) run_llvm ;;
  all)
    run_phase
    run_self
    ;;
  *)
    printf 'usage: %s [bootstrap|phase|self|sanitize|llvm|all]\n' "$0" >&2
    exit 2
    ;;
esac
