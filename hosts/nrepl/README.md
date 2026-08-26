# Native Meta-Carp nREPL host

`NreplServer.carp` is a standalone, JVM-free native nREPL host over TCP. It uses
strict bencode, warms `carp-session` once, and exposes independent cheap
session forks. Clojure is not in the server path: ordinary nREPL clients work
because nREPL itself is language-neutral.

The host pins `replikativ/carp-bencode` as a fetched source dependency, so a
Meta-Carp source checkout and compatible Carp Core are sufficient to build it.

Build and start it with:

```sh
./scripts/build-nrepl-host.sh
CARP_DIR=../Carp/core ./out/carp-nrepl
clj-nrepl-eval --port "$(cat .nrepl-port)" '(Int.+ 1 2)'
```

The server binds `127.0.0.1` only. Set `CARP_NREPL_PORT` to a fixed port or
leave it unset/zero to ask the OS for one. The selected port is written to
`.nrepl-port`, or to `CARP_NREPL_PORT_FILE` when set.

The current compatibility subset implements `describe`, `clone`, `close`, `ls-sessions`,
`eval`, `load-file`, `complete`/`completions`, and `lookup`. `eval` performs
macro expansion, resolution, inference, ownership-aware C emission, invokes
`cc` directly without a shell, runs the isolated temporary executable, and
returns its value. Successful definitions are committed only after native
compilation and execution succeed.

The initial host is deliberately sequential. It therefore does not yet satisfy
the full nREPL server contract: requests are not processed asynchronously, and
`stdin` and `interrupt` are not advertised. A worker process/event-loop model
is required before interactive input and interruption can be honest. Program
output and the final echoed value currently share the cell's captured stream,
so cells that both print and return a value are not yet split into separate
nREPL `out` and `value` responses. The implemented subset is sufficient for
`clj-nrepl-eval` and basic editor evaluation, but full CIDER compatibility is a
later milestone.

Module-source resolution remains a host responsibility in `carp-session`.
`load-file` can commit source supplied by a client, but `(load ...)` dependency
resolution and native include/link metadata still need to be connected before
the native nREPL can develop arbitrary Carp/Rust package graphs by itself.
