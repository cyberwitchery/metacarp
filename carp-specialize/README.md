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

Two module-level caches carry data derived from one inferred module, and both
are primed by `prime-trace!` at every public entry and dropped by
`clear-caches!` afterwards: the normalized node types, and an indexed
`Type.solver-from-substitution` view of the module substitution, which is what
applies that substitution wherever a concrete type is needed. A public entry
that does not prime them applies one module's substitution to another's types.

Call and expression ids repeat across owners, so nothing here may be memoized
by id alone; `*trace-positions*` is rebuilt per owner for that reason.

The module also exports the pattern-slot utilities the ownership and backend
phases share: `bound-slot-types` and `unbound-slot-types` type a match
pattern's `Bind` and `Ignore` slots from the constructor declarations and the
scrutinee's concrete type, and `bind-unbound-slots` rewrites chosen `Ignore`
slots to fresh bindings in the same depth-first order — how a by-value match's
dropped payloads get owners the delete plan can free.

```bash
carp -x test/carp-specialize.carp
```
