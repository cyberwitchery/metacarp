#!/usr/bin/env bash
# The canonical local and CI assurance entry point.
#
#   run-assurance.sh phase  phase suites plus lint and formatting
#   run-assurance.sh phase-self  phase suites through the generation-2
#                           compiler (CARP_PHASE_COMPILER, or built fresh)
#   run-assurance.sh self   bootstrap, reference suite, fixed point, leaks,
#                           expansion, library linkage
#   run-assurance.sh sanitize  the reference suite again, every generated
#                           program built with AddressSanitizer
#   run-assurance.sh llvm   the LLVM backend's memory fixtures under both
#                           drivers (needs libLLVM, see LLVM.setup)
#   run-assurance.sh all    phase and self (not sanitize or llvm, which CI
#                           runs as their own jobs)
set -euo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_root=$(CDPATH= cd -- "$script_dir/.." && pwd)
group=${1:-all}
reference=${CARP_REFERENCE:-carp}

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

run_phase() {
  (
    cd "$repo_root"
    run_style_checks
  )
  "$script_dir/run-phase-suites.sh"
}

run_self() {
  cd "$repo_root"
  "$reference" -b --optimize main.carp
  "$script_dir/run-carp-suite-self.sh"
  # Both checks want a generation-2 compiler; share one work directory so it
  # is built once. A caller-supplied CARP_FIXED_POINT_OUT is kept afterwards,
  # so a later `phase-self` can reuse the compiler (CI does).
  self_work=${CARP_FIXED_POINT_OUT:-}
  if [[ -z "$self_work" ]]; then
    self_work=$(mktemp -d "${TMPDIR:-/tmp}/carp-self.XXXXXX")
    trap 'rm -rf "$self_work"' EXIT
  fi
  CARP_FIXED_POINT_OUT="$self_work" "$script_dir/check-fixed-point.sh"
  CARP_FIXED_POINT_OUT="$self_work" "$script_dir/check-leaks.sh"
  if [[ -z "${CARP_FIXED_POINT_OUT:-}" ]]; then
    rm -rf "$self_work"
    trap - EXIT
  fi
  "$script_dir/diff-expansion.sh"
  "$script_dir/check-library-linkage.sh"
}

run_phase_self() {
  carp_root=${CARP_ROOT:-${CARP_DIR:-"$repo_root/../../carp"}}
  core_dir=${CARP_CORE_DIR:-"$carp_root/core"}
  gen2_compiler=${CARP_PHASE_COMPILER:-}
  if [[ -z "$gen2_compiler" ]]; then
    cd "$repo_root"
    "$reference" -b --optimize main.carp
    phase_work=$(mktemp -d "${TMPDIR:-/tmp}/carp-phase-self.XXXXXX")
    trap 'rm -rf "$phase_work"' EXIT
    CARP_FIXED_POINT_OUT="$phase_work" "$script_dir/check-fixed-point.sh"
    gen2_compiler="$phase_work/carp-compiler-gen2"
  fi
  if [[ ! -x "$gen2_compiler" ]]; then
    printf 'generation-2 compiler not executable: %s\n' "$gen2_compiler" >&2
    exit 2
  fi
  CARP_REFERENCE="$gen2_compiler" CARP_PHASE_CORE="$core_dir" \
    "$script_dir/run-phase-suites.sh"
}

run_sanitize() {
  cd "$repo_root"
  "$reference" -b --optimize main.carp
  CARP_SELF_SANITIZE=1 "$script_dir/run-carp-suite-self.sh"
}

run_llvm() {
  cd "$repo_root"
  "$reference" -b --optimize main.carp
  "$reference" -b --optimize main-llvm.carp
  "$script_dir/check-llvm-memory.sh"
}

case "$group" in
  phase) run_phase ;;
  phase-self) run_phase_self ;;
  self) run_self ;;
  sanitize) run_sanitize ;;
  llvm) run_llvm ;;
  all)
    run_phase
    run_self
    ;;
  *)
    printf 'usage: %s [phase|phase-self|self|sanitize|llvm|all]\n' "$0" >&2
    exit 2
    ;;
esac
