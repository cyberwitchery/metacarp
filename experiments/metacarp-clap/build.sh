#!/bin/sh
set -eu

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
compiler_root=$(CDPATH= cd -- "$here/../.." && pwd)
clap_dir="$here/.deps/clap"
out_dir="$here/out"
bundle="$out_dir/Metacarp.clap"

if [ ! -f "$clap_dir/include/clap/clap.h" ]; then
  mkdir -p "$here/.deps"
  git clone --depth 1 --branch 1.2.10 https://github.com/free-audio/clap.git "$clap_dir"
fi

cd "$compiler_root"
carp -b --optimize experiments/metacarp-clap/engine.carp

mkdir -p "$bundle/Contents/MacOS" "$bundle/Contents/Resources"
cp "$out_dir/Metacarp" "$bundle/Contents/MacOS/Metacarp"
cp "$here/Info.plist" "$bundle/Contents/Info.plist"
ditto "${CARP_DIR:-../../Carp}/core" "$bundle/Contents/Resources/core"
codesign --force --sign - "$bundle"

echo "$bundle"
