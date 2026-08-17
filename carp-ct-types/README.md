# carp-ct-types

> **Experimental.** Supports the opt-in
> [`carp-ct-infer`](../carp-ct-infer/README.md) phase; nothing else uses it.

`carp-ct-types` is the tag lattice of the compile-time language and the shape
homomorphism over it. It is the type algebra for `carp-ct-eval`'s values, the
way `carp-types` is the type algebra for the runtime program. It depends on
nothing.

The lattice is not invented here. It is `CtValue` crossed with `SurfaceForm`,
which is a tree under one root, so unrelated tags have disjoint leaves:

```
Obj
├─ Syntax
│  ├─ Lit
│  │  ├─ Num ── Int Byte Long Float Double
│  │  └─ Bool Char String Pattern
│  ├─ Symbol
│  ├─ Seq ── List Array StaticArray Dictionary
│  └─ Comment
├─ Closure
├─ Macro
├─ Builtin
└─ Collection
```

A shape is a set of leaves, held as a bitmask, and the Boolean-algebraic
operations are the set operations: `⊔` is union, `⊓` is intersection, `¬` is
complement within the lattice, `⊤` is every leaf and `⊥` is none. Subtyping is
inclusion.

This is the shape homomorphism `H` of Boolean-algebraic subtyping, from Chau
and Parreaux, *The Simple Essence of Boolean-Algebraic Subtyping* (POPL 2026).
`H` is the family that rules out impossible constructor pairings by
contradiction, which is what a checker reporting only provable impossibilities
needs. On a fragment with no record fields and no function-depth subtyping it
is exact, so it can be the decision procedure rather than an approximation of
one. The component homomorphisms `J`, `D` and `C`, which are what would let the
pass reason about a field's type or a function's domain, are not implemented.

Two consequences of the lattice worth stating, because both are language
decisions rather than encoding details:

- `Collection` is a sibling of `Seq`, not a subtag. They are distinct runtime
  representations that the evaluator converts between at a boundary, and a
  conversion is not a subtyping relation. Operations accepting either say so
  with a union, which is what `listy` is.
- `Num` is a real interior node, so `S-TagSub` gives arithmetic its domain for
  free.

Type variables and unbound names map to `⊤`. Under a guarded assumption
context a variable can only be introduced and eliminated by the pure
Boolean-algebraic rules, so any element of the target algebra preserves
monotonicity; `⊤` is the sound and imprecise choice.

```bash
carp -x ../carp-ct-infer/test/carp-ct-infer.carp
```

The lattice's own assertions live in that suite alongside the checker's, since
they are the same claim tested at two altitudes.
