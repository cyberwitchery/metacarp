# carp-session

Warm, transport-independent compiler sessions for notebook and editor hosts.

The initial API provides `Session.api-version`, `Session.create`,
`Session.create-from-module`, `Session.reset`, and transactional
`Session.infer-cell`. Runtime definitions, macros, and nominal types can be
committed and queried with `Session.upsert`, `Session.remove`, and
`Session.definitions`. `Session.create`
loads and checks Core once; subsequent cells and definition rebuilds reuse the
warm Core expansion, resolution, and inference snapshots.

The immutable base expansion snapshot is shared with the current overlay via
`Rc`; it is copied only when expansion actually commits a user definition.
This keeps cheap reset support without duplicating the resident Core state.

Replacement is atomic: the candidate overlay is rebuilt before it is committed,
and resolved global-reference edges identify its transitive dependents. Failed
replacement leaves the previous overlay untouched. Removal drops only the
named definition and that transitive closure, preserving unrelated definitions.
Macro and type replacement/removal conservatively invalidate every later
definition until the expander and type checker record precise use edges. A
committed type exposes its generated constructors and lifecycle functions to
later cells. Interface and implementation definitions remain follow-up work
under issue #21.

On an Apple arm64 host, the real-Core benchmark in `test/benchmark.carp`
currently creates a session in about 1.88 seconds and checks 100 43-byte cells
in about 3.80 seconds: 38.0 ms per cell, with zero failures. The measured peak
memory footprint is about 119 MB (`/usr/bin/time -l`; max RSS about 234 MB).
See [`docs/carp-session.md`](../docs/carp-session.md) for the complete API plan.
