#!/usr/bin/env bash
# Link two --library units into one host and require each to keep its own
# globals and helpers.
#
# The fixtures define the same global and helper names. With default linkage,
# ELF binds the second shared library's references to the first one's
# definitions, so its constructor initializes the wrong globals and its code
# reads the other library's data. Everything but a library's roots is `static`
# and hidden, so this holds with or without -fvisibility=hidden; the flag,
# which the readme recommends, only adds hiding what Core's headers define.
set -euo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_root=$(CDPATH= cd -- "$script_dir/.." && pwd)
compiler=${CARP_COMPILER:-"$repo_root/out/carp-compiler"}
carp_root=${CARP_ROOT:-${CARP_DIR:-"$repo_root/../../carp"}}
core_dir=${CARP_CORE_DIR:-"$carp_root/core"}
fixtures="$repo_root/test/library-fixtures"

if [[ ! -d "$core_dir" ]]; then
  printf 'Carp core not found: %s\n' "$core_dir" >&2
  exit 2
fi

work_dir=$(mktemp -d "${TMPDIR:-/tmp}/carp-library.XXXXXX")
trap 'rm -rf "$work_dir"' EXIT

case "$(uname -s)" in
  Darwin) suffix=dylib ;;
  *) suffix=so ;;
esac
flags=(-std=c99 -D_DEFAULT_SOURCE -fPIC -I "$core_dir")

for name in alpha beta; do
  "$compiler" --library -c "$core_dir" -o "$work_dir/$name.c" \
    "$fixtures/$name.carp"
done

expected=$'alpha\nbeta'
for visibility in default hidden; do
  extra=()
  if [[ "$visibility" == hidden ]]; then
    extra=(-fvisibility=hidden)
  fi
  for name in alpha beta; do
    cc "${flags[@]}" ${extra[@]+"${extra[@]}"} -shared \
      -o "$work_dir/lib$name.$suffix" "$work_dir/$name.c" -lm
  done
  cc -o "$work_dir/host" "$fixtures/host.c" -L "$work_dir" -lalpha -lbeta
  output=$(LD_LIBRARY_PATH="$work_dir" DYLD_LIBRARY_PATH="$work_dir" \
    "$work_dir/host")
  if [[ "$output" != "$expected" ]]; then
    printf 'library linkage (%s visibility): expected\n%s\ngot\n%s\n' \
      "$visibility" "$expected" "$output" >&2
    exit 1
  fi
done
printf 'library linkage: two libraries keep their own globals\n'
