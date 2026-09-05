# carp-session

Warm, transport-independent compiler sessions for notebook and editor hosts.

The API provides `Session.api-version`, `Session.create`,
`Session.create-from-module`, `Session.reset`, and transactional
`Session.infer-cell`. Runtime definitions, macros, nominal types, interfaces,
and implementations can be committed and queried with `Session.upsert`,
`Session.remove`, and `Session.definitions`. Warm editor queries expose
ownership plans, macro expansion, completion, and structured documentation.
`Session.emit-cell` emits a deterministic executable C translation unit without
mutating the session; `Session.lower-cell`/`Session.lower-cell-plain` stop the
same transactional pipeline at the lowered `BackendModule` for alternative
backends (the LLVM session JIT in `carp-llvm-backend/carp-session-jit.carp` —
carp-session itself stays free of libLLVM). `Session.create` loads and checks
Core once; subsequent cells and definition rebuilds reuse the warm Core
expansion, resolution, and inference snapshots.

The LLVM host adds a second persistent layer: one ORC LLJIT and thread-safe
LLVM context per compiler session. Each cell contributes an incremental module
containing only symbols not already published, so compiled globals and their
mutable storage survive later cells. `SessionJit.upsert` and
`SessionJit.remove` conservatively invalidate published native code after a
committed source change while retaining the context, target state, and C
template shim.

`SessionJit.compile-f32-function` is the deliberately narrow native-function
entry point used by the audio experiment. It accepts a named Carp function of
type `(Fn [Float] Float)`, publishes an immutable generation, and returns its
callable address. A failed compilation leaves all earlier generations alive
and callable; the host owns the policy for atomically selecting one.

The immutable base expansion snapshot is shared with the current overlay via
`Rc`; it is copied only when expansion actually commits a user definition.
This keeps cheap reset support without duplicating the resident Core state.

The committed input is the unit of text ownership: `upsert-input` and
`remove-input` act on a whole input in place, and a definition that arrived
in a multi-definition input cannot be edited or removed by name — the
name-keyed calls refuse with a diagnostic pointing at the owning input.
Binding follows the latest committed definition of a name: replacing an
overlay definition or shadowing a base one rebinds that name's committed
dependents to the new definition (their inputs replay after it), and the
report lists them as invalidated. `remove` drops whole inputs, dependents'
inputs included, and reports every definition that disappeared.

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
