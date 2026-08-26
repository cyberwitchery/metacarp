#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
server=${1:-"$repo_root/out/carp-session-server-cbor"}
core=${CARP_CORE_DIR:-"$repo_root/../Carp/core"}

if [ ! -x "$server" ]; then
  echo "missing CBOR host: $server" >&2
  exit 1
fi

# Framed canonical CBOR request: [3, "smoke", "ping", []]. The process first
# sends its ready frame and then the response. EOF ends the server cleanly.
actual=$(
  printf '\000\000\000\016\204\003\145smoke\144ping\200' |
    env CARP_DIR="$core" "$server" |
    od -An -tx1 |
    tr -d ' \n'
)
expected='0000000a8403657265616479f5030000000a840365736d6f6b65f5f6'

if [ "$actual" != "$expected" ]; then
  echo "CBOR host smoke mismatch" >&2
  echo "expected: $expected" >&2
  echo "actual:   $actual" >&2
  exit 1
fi

echo "CBOR host smoke: OK"
