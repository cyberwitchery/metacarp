# carp-ownership

`carp-ownership` is the backend-neutral ownership pass between concrete
specialization and code generation. It classifies concrete types, runs a sound
flow-sensitive borrow check, and produces the move/borrow/delete plan the
backend consumes to emit managed C.

## Type classification

Types are classified as unmanaged, owned, or borrowed from declared semantics,
never from source spelling: a type is owned when a `delete` implementation
exists for it (String, managed `deftype`s, the heap `Array`), references are
borrowed, and everything else is unmanaged. `OwnershipClassify.facts-from-module`
derives the fact table from a resolved module by matching the `delete` interface
by identity.

## Borrow checking

`Ownership.prepare` runs one flow-sensitive `analyze` pass per definition body,
threading a `BorrowState` (a moved set plus per-binding `BorrowOrigin`) through
evaluation order. It rejects, as phase-tagged errors, borrows that escape their
owner (a `Local`-origin reference in tail position) and uses of a borrow whose
owner has already moved. Branch joins union moves and join origins across
`if`/`match`/`while`, `set!` updates a binding's origin, and shared-lifetime
accessors propagate an argument's origin to the result. Only owned locals count
as moved, so unmanaged values are copied, not moved.

## Planning

`OwnershipPlan` is a side table over `SpecializedExpr`, not a rewritten copy.
Its action vocabulary follows Carp's existing semantics — the planner moves,
borrows, and deletes; copying is explicit Carp code, never an action inserted
here. `prepare` populates `actions` with `Delete` and `Move` actions and
`requirements` with one `DeleteFunction` per distinct deleted type. Those
requirements are returned to specialization, which materializes the concrete
deleters before backend lowering.

Deletes are planned for unconsumed owned let-bindings and parameters,
discarded temporaries, the value a `set!` overwrites (unless the new value's
expression consumes the binding), every unconsumed by-value `match` binding —
typed from the pattern and the constructor declarations, so bindings the
branch body never mentions are still covered — and the payloads a wildcard
(`_`) pattern slot drops. Each delete is keyed to the expression that consumes
it (the let, the set! site, the branch body), so the backend can tell a
set!-site delete from a scope-exit delete on the same binder. `match-ref`
branches borrow and never schedule deletes.

## Structured borrow places

A borrow action carries an explicit `Shared` or `Unique` mode and an
`OwnershipPlace`: a root resource followed by field, index, slice, or
dereference projections. Unknown indices and slice bounds are represented
explicitly and therefore overlap conservatively. `Ownership.places-overlap?`
proves separation only for different roots and known-disjoint projections.

This representation does not itself introduce new rejection behavior. The
current planner preserves its existing decisions, while reports serialize the
borrow mode and root. Later loan checking can consume the structured place
without changing the ownership-plan protocol again.

## Identity invariants

Ownership locations are keyed by a concrete specialization context plus the
stable expression ID. IDs are unique within a specialization and across the root
stream, but the space is sparse — a direct global call replaces its callee
reference node, and the pass does not renumber surviving nodes. The concrete
signature is part of the context, so two specializations of the same polymorphic
definition never collide.

```bash
carp -x test/carp-ownership.carp
```
