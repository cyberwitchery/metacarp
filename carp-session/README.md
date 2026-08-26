# carp-session

Warm, transport-independent compiler sessions for notebook and editor hosts.

Upstream introduced `Session.api-version` at revision 1. This branch uses
revision 2 for its incompatible public report/artifact extensions. Internal
storage refactors and moving a transport adapter do not consume API revision
numbers. The CBOR wire protocol and encoded library-artifact format are
independently versioned.

The revision-2 API provides `Session.api-version`, `Session.create`,
`Session.create-from-module`, `Session.fork`, `Session.reset`, and transactional
`Session.infer-cell`. Runtime definitions, macros, nominal types, interfaces,
and implementations can be committed and queried with `Session.upsert`,
`Session.remove`, and `Session.definitions`. Warm editor queries expose
ownership plans, macro expansion, completion, and structured documentation.
`Session.emit-cell` emits a deterministic executable C translation unit without
mutating the session, while `Session.emit-library` accepts explicit named roots
and emits the corresponding entry-point-free translation unit for native
hosts. `Session.emit-library-with-build` additionally carries host-resolved
include directories and native library paths in the artifact; these are data,
not source-controlled build commands. `Session.create` loads and checks Core once; subsequent
cells and definition rebuilds reuse the warm Core expansion, resolution, and
inference snapshots.

The immutable warm compiler base is held behind one `Rc`. `Session.fork`
increments that reference and copies only the mutable overlay, so nREPL clones
do not reload Core or duplicate its resident state. Expansion snapshots within
an overlay are copied only when expansion commits a user definition.

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

On the development Linux x86-64 host at `7aee762`, four runs of the same
already-built benchmark created a session in 1.66--1.68 seconds and checked
100 cells in 8.12--8.19 seconds: 81.15--81.87 ms per cell, with zero failures
and about 348 MB peak RSS. Cross-platform absolute timings are not a regression
comparison; retain both measurements until CI records per-platform history.

Base trace normalization uses `Type.solver-from-substitution`, so variable
lookup is indexed rather than scanning the complete inference substitution for
every type node. On the Carpaccio development host, resident creation measured
about 5.2 seconds and a first rooted library emission about 0.37 seconds.

`test/memory.carp` runs one explicit compiler warm-up, records the stabilized
allocation balance, then performs 20 cycles containing successful and failed
upserts, successful and failed cell checks, editor queries, C emission, derived
types, interface dispatch, and reset. With `--log-memory`, every measured cycle
returns exactly to that baseline; this guards against per-edit leaks while
allowing one-time lazy compiler caches to remain resident.
See [`docs/carp-session.md`](../docs/carp-session.md) for the complete API plan.

The session API is deliberately transport-neutral. The optional native adapter
under `hosts/cbor` uses the source-only `carp-cbor` package; the session library
itself has no transport dependency. The adapter exposes ownership reports and rooted
library emission from the exact ownership plan used by lowering, so native
hosts never need a second analysis run to construct their ABI manifest.
