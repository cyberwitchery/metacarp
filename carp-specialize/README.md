# carp-specialize

`carp-specialize` turns inferred concrete global call signatures into a
deduplicated set of specialization instances, keyed by resolved binding ID and
concrete function type. It is demand-driven: unused polymorphic definitions do
not produce instances.

It starts at top-level calls and traverses global calls in each newly added
specialized body. Recursive instance edges terminate through the same
binding/signature deduplication.

Specialized expression types preserve lifetime identities. Instance
deduplication uses runtime representation equality, so lifetime-only
differences do not create duplicate bodies or colliding C symbols.

An interface call is resolved to a matching registered implementation before
an instance is emitted. Builtins are leaf instances; functions continue to
contribute body dependencies.

`Specialize.prepare` builds an invocation-owned `SpecializeContext` for one
unchanged Core/inference input. It owns the scheme index, owner and call buckets, interface implementation buckets, and a
snapshot of native naming policy. The driver reuses this context for named
roots, specialization/ownership closure rounds, and echo demands.

`SpecializationDemands` retains deduplicated copier and deleter requests across
ownership-closure rounds. `Specialize.module-with-demands` borrows these streams
and seeds its work queue in deleter, copier, then named-seed order. The driver
adds requirements and decides convergence; specialization owns request storage
and does not call ownership. Existing specialization entry points keep their
arguments and results.

Each materialization call owns a separate `SpecializeWork`: instance buckets,
owner-local expression positions, an indexed copy of its module substitution,
normalized node types, and exact-type
interface dispatch results. It releases that work before ownership planning.
Named and echo queries allocate no trace memo. Materialization allocates empty
optional slots on its first expression query and boxes only normalized types
it actually visits. No boxed Unit placeholders are allocated.

Call and expression ids repeat across owners. Expression positions are rebuilt
per owner; indexed hits still check the complete reference identity. Dispatch
keys retain lifetimes and variable identities, which `Type.render` omits.
The legacy naming setters change defaults for future contexts; prepared
contexts retain their own snapshots. Other compiler services still require
serialized invocations.

The pattern-slot entry points remain as compatibility facades over
`PatternTyping` in `carp-types/pattern-typing.carp`. That library owns typing
of bound and ignored payloads and the corresponding masked pattern rewrite.
Ownership obtains both slot sets in one traversal; backend lowering requests
only ignored slots.

`captures.carp` provides read-only `CaptureAnalysis`: free bindings of one
lambda or all closures in a concrete module. Ownership closure and backend
lambda lifting use the same lexical binding rules. Analysis does not rewrite
bodies or allocate native symbols.

```bash
carp -x test/carp-specialize.carp
```
