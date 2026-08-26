#!/usr/bin/env bash
# Build the platform-independent source bundle consumed by Carpaccio installers.
# It contains fixed-point-generated C, Carp Core source/headers, and no native
# executable. Consumers compile the two C translation units with local Clang.
set -euo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_root=$(CDPATH= cd -- "$script_dir/.." && pwd)
fixed_root=${CARP_FIXED_POINT_OUT:-"$repo_root/out/fixed-point"}
compiler=${CARP_FIXED_POINT_COMPILER:-"$fixed_root/carp-compiler-gen2"}
compiler_c=${CARP_FIXED_POINT_C:-"$fixed_root/gen2.c"}
carp_root=${CARP_ROOT:-${CARP_DIR:-"$repo_root/../Carp"}}
core_dir=${CARP_CORE_DIR:-"$carp_root/core"}
release_dir=${METACARP_RELEASE_DIR:-"$repo_root/out/release"}
session_host_c=${CARP_SESSION_HOST_C:-}

if [[ ! -x "$compiler" || ! -f "$compiler_c" ]]; then
  printf 'verified generation-2 compiler/C not found under %s\n' "$fixed_root" >&2
  printf 'run CARP_FIXED_POINT_OUT=%s scripts/check-fixed-point.sh first\n' \
    "$fixed_root" >&2
  exit 2
fi
if [[ ! -f "$core_dir/Core.carp" ]]; then
  printf 'Carp Core not found under %s\n' "$core_dir" >&2
  exit 2
fi

hash_file() {
  if command -v sha256sum >/dev/null; then
    sha256sum "$1" | awk '{ print $1 }'
  else
    shasum -a 256 "$1" | awk '{ print $1 }'
  fi
}

metacarp_revision=$(git -C "$repo_root" rev-parse HEAD)
carp_revision=$(git -C "$carp_root" rev-parse HEAD)
bundle_id="metacarp-bootstrap-${metacarp_revision}-${carp_revision}"
stage=$(mktemp -d "${TMPDIR:-/tmp}/metacarp-bootstrap-bundle.XXXXXX")
bundle="$stage/$bundle_id"
archive="$release_dir/$bundle_id.tar.gz"
next="$archive.next"

cleanup() {
  rm -rf "$stage"
  rm -f "$next"
}
trap cleanup EXIT

mkdir -p "$bundle/carp" "$release_dir"
cp "$compiler_c" "$bundle/carp-compiler.c"
cp -R "$core_dir" "$bundle/carp/core"
cp "$repo_root/LICENSE" "$bundle/LICENSE-METACARP"
cp "$carp_root/LICENSE" "$bundle/LICENSE-CARP"
if [[ -f "$carp_root/LUA_LICENSE" ]]; then
  cp "$carp_root/LUA_LICENSE" "$bundle/LICENSE-LUA"
fi

if [[ -n "$session_host_c" ]]; then
  cp "$session_host_c" "$bundle/carp-session-server-cbor.c"
else
  "$compiler" -c "$core_dir" \
    -o "$bundle/carp-session-server-cbor.c" \
    "$repo_root/hosts/cbor/SessionServer.carp"
fi

compiler_hash=$(hash_file "$bundle/carp-compiler.c")
host_hash=$(hash_file "$bundle/carp-session-server-cbor.c")
cat > "$bundle/manifest.properties" <<EOF
format=1
metacarp_revision=$metacarp_revision
carp_revision=$carp_revision
compiler_c_sha256=$compiler_hash
session_host_c_sha256=$host_hash
protocol=3
EOF

# Stable ownership, ordering, and timestamps make the asset reproducible from
# the same fixed-point C and source revisions. gzip -n omits its timestamp.
tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner \
  -C "$stage" -cf - "$bundle_id" | gzip -n > "$next"
mv "$next" "$archive"

printf 'bootstrap bundle: %s\n' "$archive"
printf 'bootstrap bundle sha256: %s\n' "$(hash_file "$archive")"
