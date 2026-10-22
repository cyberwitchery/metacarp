#!/usr/bin/env bash
# Build and exercise the terminal REPL against real Core, including PTY input.
set -euo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_root=$(CDPATH= cd -- "$script_dir/.." && pwd)
compiler=${CARP_COMPILER:-"$repo_root/out/carp-compiler"}
carp_root=${CARP_ROOT:-${CARP_DIR:-"$repo_root/../../carp"}}
core_dir=${CARP_CORE_DIR:-"$carp_root/core"}
compiler_args=()
if [[ -n "${CARP_READER_SOURCE:-}" ]]; then
  if [[ ! -f "$CARP_READER_SOURCE" ]]; then
    printf 'reader override not found: %s\n' "$CARP_READER_SOURCE" >&2
    exit 2
  fi
  compiler_args+=(--package-override "git@github.com:carpentry-org/carp-reader@0.5.0=$CARP_READER_SOURCE")
fi

if [[ "$(uname -s)" != Darwin ]]; then
  printf 'the REPL terminal host currently targets macOS\n' >&2
  exit 2
fi
cd "$repo_root"
test_dir=$(mktemp -d "${TMPDIR:-/tmp}/metacarp-repl-check.XXXXXX")
trap 'rm -rf "$test_dir"' EXIT
for suite in input syntax paint native/display native/wait native/service; do
  binary="$test_dir/${suite##*/}"
  "$compiler" ${compiler_args[@]+"${compiler_args[@]}"} -c "$core_dir" -b -o "$binary" "carp-repl/test/$suite.carp"
  "$binary"
done
"$compiler" ${compiler_args[@]+"${compiler_args[@]}"} -c "$core_dir" --optimize -b -o out/metacarp-repl main-repl.carp
"$compiler" ${compiler_args[@]+"${compiler_args[@]}"} -c "$core_dir" --optimize -b -o out/metacarp main-metacarp.carp
python3 test/cli.py out/metacarp "$core_dir" -v
python3 carp-repl/test/repl.py out/metacarp "$core_dir" --subcommand repl -v
