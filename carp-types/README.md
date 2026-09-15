# carp-types

`carp-types` is the reusable type algebra: monotypes, schemes,
substitutions, structural equality, free-variable collection, and unification
with an occurs check. It has no dependency on parser or compiler IR packages.

A substitution can be applied directly with `Type.apply`, which looks each
variable up in its binding array, or through `Type.solver-from-substitution`,
a read-only view that indexes the same bindings by variable id and answers in
constant time. The indexed view is worth building whenever one substitution is
applied many times, as specialization does with the module substitution.

Reference types carry a separate `MonoLifetime` identity. Schemes quantify type
and lifetime variables independently; immutable and mutable substitutions both
preserve lifetime aliases. `Type.same?` includes lifetime identity, while
`Type.same-representation?` deliberately ignores it for specialization and ABI
layout.

```bash
carp -x test/carp-types.carp
```
