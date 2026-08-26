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

## Places, access facts, and summaries

Borrow actions carry an explicit `OwnershipBorrowMode` (`Shared` or `Unique`)
and an `OwnershipPlace`. A place is a root resource plus a flat projection path
(`Deref`, `Field`, `Index`, or `Slice`); unknown indices and bounds use
`Nothing` and conservatively overlap concrete projections. Root-only places are
the compatible representation of the original bare resources.

The plan also normalizes proven actions into `OwnershipAccess` facts. Current
production facts are moves, drops, and explicit borrows; `Read` and `Write` are
reserved in the stable vocabulary for expression-level access collection.

Each concrete body receives an `OwnershipFunctionSummary`. Parameters are
classified as `Copy`, `Take`, `SharedBorrow`, or `UniqueBorrow`; the result
separately records its ownership class and the parameter indices whose
lifetimes it may retain. `Ownership.validate-strict-loans` is applied by
reusable-library emission and is also callable directly by compiler clients. It
currently rejects a result which borrows from a by-value `Take` parameter, a
contract legacy executable compilation accepts but cannot soundly expose as a
Rust-like return lifetime.

Reachable `register`ed C/Rust symbols receive `OwnershipForeignContract`
records keyed by Carp identity and emitted symbol. Signature-derived reference
parameters default to `SharedBorrow`. A register may declare parameter modes as
an optional final array, for example `[unique copy]`; mode count and reference
shape are checked during resolution. After specialization, explicit modes are
also checked against concrete ownership classification: an owned parameter
cannot be declared `copy`, and an unmanaged parameter cannot be declared
`take`. At every `unique` call, the ownership pass
requires a direct borrow of a named owner or a forwarded reference parameter,
and rejects a live alias or another argument derived from that owner. Forwarding
upgrades that parameter in the caller's summary to `UniqueBorrow`, and both the
mode and strictness propagate transitively through ordinary calls. Carp's own
mutation intrinsics also infer `UniqueBorrow`, but their internal overlap check
is relaxed until expression collection preserves field/index projections; this
avoids rejecting safe disjoint-field code while keeping exported host guards
exclusive. The compiler never infers uniqueness from C pointer mutability.

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
