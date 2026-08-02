#!/usr/bin/env bash
# The canonical local and CI assurance entry point.
#
#   run-assurance.sh phase  phase suites plus lint and formatting
#   run-assurance.sh self   bootstrap, reference suite, fixed point, expansion
#   run-assurance.sh all    both groups (the default)
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
  "$script_dir/run-phase-suites.sh"
  (
    cd "$repo_root"
    run_style_checks
  )
}

run_self() {
  cd "$repo_root"
  "$reference" -b --optimize main.carp
  "$script_dir/run-carp-suite-self.sh"
  "$script_dir/check-fixed-point.sh"
  "$script_dir/diff-expansion.sh"
}

case "$group" in
  phase) run_phase ;;
  self) run_self ;;
  all)
    run_phase
    run_self
    ;;
  *)
    printf 'usage: %s [phase|self|all]\n' "$0" >&2
    exit 2
    ;;
esac
