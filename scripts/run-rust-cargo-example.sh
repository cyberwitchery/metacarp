#!/usr/bin/env bash
# Build a Rust C-ABI adapter with Cargo, link it into an ordinary Carp program,
# and run the result. This path deliberately has no Carpaccio dependency.
set -euo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_root=$(CDPATH= cd -- "$script_dir/.." && pwd)
compiler=${CARP_COMPILER:-"$repo_root/out/carp-compiler"}
fixture="$repo_root/examples/rust-cargo"
work_dir=$(mktemp -d "${TMPDIR:-/tmp}/metacarp-rust-cargo.XXXXXX")

if [[ -n "${CARP_CORE_DIR:-}" ]]; then
  core_dir=$CARP_CORE_DIR
elif [[ -n "${CARP_ROOT:-${CARP_DIR:-}}" ]]; then
  carp_root=${CARP_ROOT:-$CARP_DIR}
  core_dir="$carp_root/core"
elif [[ -d "$repo_root/../Carp/core" ]]; then
  core_dir="$repo_root/../Carp/core"
elif [[ -d "$repo_root/../carp/core" ]]; then
  core_dir="$repo_root/../carp/core"
else
  core_dir="$repo_root/../../carp/core"
fi

cleanup_work_dir() {
  rm -rf "$work_dir"
}
trap cleanup_work_dir EXIT

case "$(uname -s)" in
  Darwin) library="$fixture/target/release/libmetacarp_rust_example.dylib" ;;
  Linux) library="$fixture/target/release/libmetacarp_rust_example.so" ;;
  *)
    printf 'unsupported host for Rust Cargo example: %s\n' "$(uname -s)" >&2
    exit 2
    ;;
esac

cargo build --release --manifest-path "$fixture/Cargo.toml"
"$compiler" -b --optimize \
  -c "$core_dir" \
  -o "$work_dir/example" \
  --include "$fixture/include" \
  --link "$library" \
  "$fixture/main.carp"

actual=$("$work_dir/example")
if [[ "$actual" != 42 ]]; then
  printf 'expected Rust-backed Carp program to print 42, got: %s\n' "$actual" >&2
  exit 1
fi
printf 'standalone Carp -> Cargo adapter: %s\n' "$actual"
