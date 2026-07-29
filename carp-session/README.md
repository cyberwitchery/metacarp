# carp-session

Warm, transport-independent compiler sessions for notebook and editor hosts.

The API provides `Session.api-version`, `Session.create`,
`Session.create-from-module`, `Session.reset`, and transactional
`Session.infer-cell`. Runtime definitions, macros, nominal types, interfaces,
and implementations can be committed and queried with `Session.upsert`,
`Session.remove`, and `Session.definitions`. Warm editor queries expose
ownership plans, macro expansion, completion, and structured documentation.
`Session.emit-cell` emits a deterministic executable C translation unit without
mutating the session. `Session.create` loads and checks Core once; subsequent
cells and definition rebuilds reuse the warm Core expansion, resolution, and
inference snapshots.

The immutable base expansion snapshot is shared with the current overlay via
`Rc`; it is copied only when expansion actually commits a user definition.
This keeps cheap reset support without duplicating the resident Core state.

Replacement is atomic: the candidate overlay is rebuilt before it is committed,
and resolved global-reference edges identify its transitive dependents. Failed
replacement leaves the previous overlay untouched. Removal drops only the
named definition and that transitive closure, preserving unrelated definitions.
Unchanged definitions and same-kind function, value, external, or interface
replacements retain their compatible global identities across the rebuild.
Macro, type, interface, and implementation replacement/removal conservatively
invalidate every later definition until the compiler records precise semantic
use edges. A committed type exposes its generated constructors and lifecycle
functions to later cells. Committed interface/implementation pairs are retained
in a deduplicated overlay dispatch table for later specialization and codegen.
Syntax returned by a macro, and errors raised while evaluating its body, are
anchored to the caller's invocation span before a cell diagnostic is produced.

On an Apple arm64 host, the real-Core benchmark in `test/benchmark.carp`
currently creates a session in about 1.88 seconds and checks 100 43-byte cells
in about 3.80 seconds: 38.0 ms per cell, with zero failures. The measured peak
memory footprint is about 119 MB (`/usr/bin/time -l`; max RSS about 234 MB).

`test/memory.carp` runs one explicit compiler warm-up, records the stabilized
allocation balance, then performs 20 cycles containing successful and failed
upserts, successful and failed cell checks, editor queries, C emission, derived
types, interface dispatch, and reset. With `--log-memory`, every measured cycle
returns exactly to that baseline; this guards against per-edit leaks while
allowing one-time lazy compiler caches to remain resident.
See [`docs/carp-session.md`](../docs/carp-session.md) for the complete API plan.
