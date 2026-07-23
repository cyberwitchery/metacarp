#!/bin/sh
set -eu

backend_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
generated_c="${TMPDIR:-/tmp}/carp-core-pow.c"
executable="${TMPDIR:-/tmp}/carp-core-pow"

cd "$backend_dir"
carp -b test/core-declarations.carp
./out/core-backend-checkpoint "$generated_c"
clang "$generated_c" -I ../../../carp/core -o "$executable"
"$executable"
