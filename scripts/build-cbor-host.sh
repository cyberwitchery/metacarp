#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
compiler=${CARP_COMPILER:-"$repo_root/out/carp-compiler"}
core=${CARP_CORE_DIR:-"$repo_root/../Carp/core"}
output=${METACARP_CBOR_HOST:-"$repo_root/out/carp-session-server-cbor"}

if [ ! -x "$compiler" ]; then
  echo "missing Meta-Carp compiler: $compiler" >&2
  exit 1
fi
if [ ! -f "$core/Core.carp" ]; then
  echo "missing Carp Core: $core (set CARP_CORE_DIR)" >&2
  exit 1
fi
mkdir -p "$(dirname -- "$output")"
next="$output.next"
"$compiler" -b --optimize -c "$core" -o "$next" \
  "$repo_root/hosts/cbor/SessionServer.carp"
mv "$next" "$output"
echo "installed $output"
