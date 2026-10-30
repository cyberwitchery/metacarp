# carp-types

`carp-types` is the reusable type algebra: monotypes, schemes,
substitutions, structural equality, free-variable collection, and unification
with an occurs check. It has no dependency on parser or compiler IR packages.

A substitution can be applied directly with `Type.apply`, which looks each
variable up in its binding array, or through `Type.solver-from-substitution`,
a read-only view that indexes the same bindings by variable id and answers in
constant time. The indexed view is worth building whenever one substitution is
applied many times, as specialization does with the module substitution.

A failed unification is a `TypeError`: `Explained` carries a rendered
message, `Unexplained` carries none. The substitution unifier, which
specialization calls many times only to ask whether two types fit, fails
`Unexplained`, so no message is rendered unless a caller reports it.
`TypeError.message` gives the text either way, and `Type.mismatch` builds the
explained error for two types. `Type.solver-changes?` answers whether applying
a solver would change a type, without applying it.

Reference types carry a separate `MonoLifetime` identity. Schemes quantify type
and lifetime variables independently; immutable and mutable substitutions both
preserve lifetime aliases. `Type.same?` includes lifetime identity, while
`Type.same-representation?` deliberately ignores it for specialization and ABI
layout.

`core-instantiation.carp` is an optional bridge to Core IR. Derivation,
specialization, and both backends share its structural conversion of concrete
field types. Callers supply borrowed binding storage and a variable lookup
function, retaining their own binding precedence, fallback, and diagnostic
rules. Concrete reference lifetimes become Static. Inference keeps its separate
fresh-variable and lifetime translation; the base type algebra stays independent
of Core IR.

`pattern-typing.carp` owns constructor-driven pattern payload typing and masked
binding of ignored slots. `PatternTyping.analyze` returns bound and ignored
types together in one owning `PatternSlotTypes` record. Ownership uses this
joint analysis; lowering can request only ignored slots. Both preserve the
same constructor identity checks, generic substitutions, and traversal order.

```bash
carp -x test/carp-types.carp
```
