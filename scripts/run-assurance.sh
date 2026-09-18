#!/usr/bin/env bash
# The canonical local and CI assurance entry point.
#
#   run-assurance.sh phase  phase suites plus lint and formatting
#   run-assurance.sh phase-self  phase suites through the self-hosted compiler
#   run-assurance.sh self   bootstrap, reference suite, fixed point, leaks,
#                           expansion
#   run-assurance.sh sanitize  the reference suite again, every generated
#                           program built with AddressSanitizer
#   run-assurance.sh all    phase and self (not sanitize, which CI runs as its
#                           own job)
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

run_phase_self() {
  core_dir=${CARP_CORE_DIR:-${CARP_DIR:-${CARP_ROOT:-}}/core}
  phase_compiler=${CARP_PHASE_COMPILER:-"$repo_root/out/carp-compiler"}
  if [[ ! -x "$phase_compiler" ]]; then
    printf 'self-hosted compiler not found: %s\n' "$phase_compiler" >&2
    exit 2
  fi
  if [[ ! -f "$core_dir/Core.carp" ]]; then
    printf 'Carp Core.carp not found under: %s\n' "$core_dir" >&2
    exit 2
  fi
  CARP_REFERENCE="$phase_compiler" \
    CARP_DIR="${CARP_DIR:-$(dirname -- "$core_dir")}" \
    CARP_PHASE_CORE="$core_dir" \
    CARP_PHASE_LOG_MEMORY=0 \
    CARP_PHASE_MEMORY_TESTS=0 \
    "$script_dir/run-phase-suites.sh"
}

run_self() {
  cd "$repo_root"
  "$reference" -b --optimize main.carp
  "$script_dir/run-carp-suite-self.sh"
  # Both checks want a generation-2 compiler; share one work directory so it
  # is built once. A caller that needs the compiler afterwards (the CI lane
  # that runs the phase suites through generation 2) names that directory in
  # CARP_FIXED_POINT_OUT and owns it; otherwise this is a temporary.
  self_work=${CARP_FIXED_POINT_OUT:-}
  self_work_owned=false
  if [[ -z "$self_work" ]]; then
    self_work=$(mktemp -d "${TMPDIR:-/tmp}/carp-self.XXXXXX")
    self_work_owned=true
    trap 'rm -rf "$self_work"' EXIT
  fi
  CARP_FIXED_POINT_OUT="$self_work" "$script_dir/check-fixed-point.sh"
  CARP_FIXED_POINT_OUT="$self_work" "$script_dir/check-leaks.sh"
  if $self_work_owned; then
    rm -rf "$self_work"
    trap - EXIT
  fi
  "$script_dir/diff-expansion.sh"
}

run_sanitize() {
  cd "$repo_root"
  "$reference" -b --optimize main.carp
  CARP_SELF_SANITIZE=1 "$script_dir/run-carp-suite-self.sh"
}

case "$group" in
  phase) run_phase ;;
  phase-self) run_phase_self ;;
  self) run_self ;;
  sanitize) run_sanitize ;;
  all)
    run_phase
    run_self
    ;;
  *)
    printf 'usage: %s [phase|phase-self|self|sanitize|all]\n' "$0" >&2
    exit 2
    ;;
esac
