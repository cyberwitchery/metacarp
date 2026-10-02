#!/usr/bin/env bash
# Build a release archive of the self-built compiler for this host.
#
#   build-release.sh [version]
#
# Generation 1 is built the way run-assurance.sh builds it (from a seed,
# CARP_SEED_COMPILER, falling back to the reference), then the fixed-point
# check builds generation 2 and requires it to reproduce its own C. The
# archive ships that generation-2 binary, the Carp core it was built against
# (so `-c core` works out of the box), and the provenance file the check
# writes. With a version argument, the binary's --version must match it.
#
# The archive lands in CARP_RELEASE_OUT (default out/release) as
# carp-compiler-<version>-<os>-<arch>.tar.gz.
set -euo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_root=$(CDPATH= cd -- "$script_dir/.." && pwd)
carp_root=${CARP_ROOT:-${CARP_DIR:-"$repo_root/../../carp"}}
core_dir=${CARP_CORE_DIR:-"$carp_root/core"}
release_out=${CARP_RELEASE_OUT:-"$repo_root/out/release"}
expected_version=${1:-}

if [[ ! -d "$core_dir" ]]; then
  printf 'Carp core not found: %s\n' "$core_dir" >&2
  exit 2
fi

if [[ "$(uname -s)" == "Linux" ]]; then
  ulimit -s 524288
fi

os=$(uname -s | tr '[:upper:]' '[:lower:]')
arch=$(uname -m)
if [[ "$arch" == "arm64" ]]; then
  arch=aarch64
fi

work_dir=$(mktemp -d "${TMPDIR:-/tmp}/carp-release.XXXXXX")
trap 'rm -rf "$work_dir"' EXIT

cd "$repo_root"
"$script_dir/run-assurance.sh" bootstrap
CARP_FIXED_POINT_OUT="$work_dir/fixed-point" "$script_dir/check-fixed-point.sh"
compiler="$work_dir/fixed-point/carp-compiler-gen2"

version=$("$compiler" --version | awk '{ print $2 }')
if [[ -n "$expected_version" && "$version" != "$expected_version" ]]; then
  printf 'compiler reports version %s, release is %s\n' \
    "$version" "$expected_version" >&2
  exit 1
fi

name="carp-compiler-$version-$os-$arch"
stage="$work_dir/$name"
mkdir -p "$stage/bin"
install -m 755 "$compiler" "$stage/bin/carp-compiler"
cp -R "$core_dir" "$stage/core"
if [[ -f "$carp_root/LICENSE" ]]; then
  cp "$carp_root/LICENSE" "$stage/core/LICENSE"
fi
cp README.md LICENSE "$stage/"
{
  cat "$work_dir/fixed-point/bootstrap-provenance.txt"
  printf 'core_revision=%s\n' \
    "$(git -C "$carp_root" rev-parse HEAD 2>/dev/null || printf unknown)"
} | sed "s|^core_dir=.*|core_dir=core|" >"$stage/PROVENANCE"

# the packaged binary must compile against the packaged core, not the build
# tree's.
(cd "$work_dir" && "$stage/bin/carp-compiler" -x -c "$stage/core" \
  "$repo_root/examples/squares.carp")

mkdir -p "$release_out"
tar -czf "$release_out/$name.tar.gz" -C "$work_dir" "$name"
printf 'release archive: %s\n' "$release_out/$name.tar.gz"
