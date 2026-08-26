#!/usr/bin/env bash
set -euo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
archive=${1:-}
if [[ ! -f "$archive" ]]; then
  printf 'usage: %s bootstrap.tar.gz\n' "$0" >&2
  exit 2
fi
command -v clang >/dev/null || {
  printf 'clang is required to verify the bootstrap bundle\n' >&2
  exit 2
}

work=$(mktemp -d "${TMPDIR:-/tmp}/metacarp-bootstrap-verify.XXXXXX")
cleanup() { rm -rf "$work"; }
trap cleanup EXIT

tar -xzf "$archive" -C "$work"
shopt -s nullglob
roots=("$work"/metacarp-bootstrap-*)
if [[ ${#roots[@]} -ne 1 || ! -f "${roots[0]}/manifest.properties" ]]; then
  printf 'bootstrap archive must contain exactly one manifested root\n' >&2
  exit 1
fi
root=${roots[0]}
for legal in LICENSE-METACARP LICENSE-CARP LICENSE-LUA; do
  [[ -s "$root/$legal" ]] || {
    printf 'bootstrap archive is missing %s\n' "$legal" >&2
    exit 1
  }
done

property() {
  awk -F= -v key="$1" '$1 == key { print substr($0, length(key) + 2) }' \
    "$root/manifest.properties"
}
hash_file() {
  if command -v sha256sum >/dev/null; then
    sha256sum "$1" | awk '{ print $1 }'
  else
    shasum -a 256 "$1" | awk '{ print $1 }'
  fi
}
check_hash() {
  local path=$1 expected=$2 actual
  actual=$(hash_file "$path")
  if [[ "$actual" != "$expected" ]]; then
    printf 'hash mismatch for %s: expected %s, got %s\n' \
      "$path" "$expected" "$actual" >&2
    exit 1
  fi
}

[[ "$(property format)" == 1 ]]
[[ "$(property protocol)" == 3 ]]
check_hash "$root/carp-compiler.c" "$(property compiler_c_sha256)"
check_hash "$root/carp-session-server-cbor.c" \
  "$(property session_host_c_sha256)"

flags=(-O3 -D NDEBUG -D_DEFAULT_SOURCE -std=c99 -w
  -Werror=typedef-redefinition -I "$root/carp/core")
clang "${flags[@]}" -o "$work/carp-compiler" "$root/carp-compiler.c" -lm
clang "${flags[@]}" -o "$work/carp-session-server-cbor" \
  "$root/carp-session-server-cbor.c" -lm

"$work/carp-compiler" --version
CARP_CORE_DIR="$root/carp/core" \
  "$script_dir/smoke-cbor-host.sh" "$work/carp-session-server-cbor"
printf 'bootstrap bundle verification: OK\n'
