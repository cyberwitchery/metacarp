# Rust-compatible affine interop

## Current boundary

Carp and Rust already share a practical C ABI for scalars, `repr(C)` records,
pointer/length views, and opaque handles. The remaining mismatch is semantic:
Carp's `(Ref T)` does not distinguish Rust `&T` from `&mut T`, and a C pointer
alone cannot prove either lifetime or exclusivity.

The ownership IR therefore separates representation from proof:

- `OwnershipPlace` identifies a root and projections.
- `OwnershipBorrowMode` distinguishes shared and unique loans.
- `OwnershipFunctionSummary` describes Carp entry/exit effects.
- `OwnershipForeignContract` describes reachable registered symbols.
- `Ownership.validate-strict-loans` rejects contracts which cannot safely cross
  a Rust-like boundary and is applied automatically during reusable-library
  emission.

Signature-derived foreign references remain shared. An explicit register
contract can refine a reference parameter to unique:

```clojure
(register translate
  (Fn [(Ref Point) Double Double] ())
  "point_translate"
  [unique copy copy])
```

Resolution checks the contract against the signature. The call-site checker
then requires a direct borrow of a named owner or a forwarded reference
parameter, and rejects live aliases and other arguments derived from that
owner. Unique requirements propagate through ordinary Carp wrappers to a fixed
point, and every forwarded parameter is upgraded to `UniqueBorrow` in its
function summary so the obligation remains visible at an exported boundary.
In-place field/array setters, push, and pop intrinsics are unique boundaries as
well, so pure Carp mutation receives the same manifest and host guard as Rust
`&mut` calls. Foreign-declared uniqueness is additionally marked `strict` and
that property propagates through wrappers: overlapping calls are rejected in
Carp. Intrinsic Carp mutation is temporarily non-strict internally, while still
producing `UniqueBorrow` summaries, because the expression collector does not
yet retain the field projections needed to accept established safe patterns
such as borrowing `Map.buckets` while mutating `Map.len`.

## Compatibility result

The Carpaccio example links a Rust `cdylib` once and calls it directly from
generated Carp. A Panama-backed `repr(C)` record crosses Clojure → Carp → Rust
without conversion: Rust reads it through `*const T` and mutates the same bytes
through `*mut T`. This confirms that no new object representation is required
for `&mut T`; the required compiler work is loan semantics and contracts.

## Conservative overlap

Two places overlap when they have the same root and their projections do not
prove disjointness. Different known fields or different known array indices may
be disjoint. An unknown index or slice bound overlaps every compatible concrete
projection. A unique loan conflicts with every overlapping live loan; two
shared loans may coexist.

`Ownership.places-overlap?` implements this conservative projection algebra and
is covered for fields, indices, unknown indices, slices, prefixes, and distinct
roots. Unique call collection still operates at whole-root precision; the next
step is teaching accessor/index expressions to produce these places. Strict
foreign loans therefore reject conservatively, while Carp intrinsics defer
internal overlap rejection until that projection information is available.

Unique-effect inference uses snapshot rounds, stops at the first unchanged
round, and copies the fact table once per round rather than once per body. The
next performance step is an indexed reverse-call worklist so a changed callee
revisits only its callers.

## Proof seam

Carpaccio's `:proof` alias loads Ansatz and kernel-checks the small independent
laws used by strict mode:

- shared/shared loans are compatible;
- a unique loan conflicts on either side;
- a result cannot retain a borrow into a taken parameter.

The finite mode and overlap-trace tables live in a versioned EDN contract shared
by Carpaccio's runtime validator and the proof namespace. Ansatz generates a
ground theorem for every table row, proves the quantified laws above, and proves
that unique/rejected overlap states reject or remain rejected. The compiler
remains the producer of facts. Ansatz proves the decision rules; it is not a
mandatory dependency of ordinary Carp compilation.

Library emission returns C and the exact ownership plan used for lowering as
one versioned artifact. Carpaccio stores that manifest with the loaded native
generation, derives Panama loan modes from its root summaries, and dynamically
guards overlapping native address ranges during downcalls. Arenas govern
storage validity; loan guards govern temporary shared/unique access.

## Upstream-sized changes

1. Land `OwnershipBorrowMode`, `OwnershipPlace`, and serializer changes with no
   default behavior change.
2. Land normalized access facts and function summaries.
3. Land foreign-contract records with shared defaults.
4. Land strict validation at the explicit reusable-library/session boundary.
5. ~~Add declaration syntax for unique foreign parameters and enforce it at
   call sites before changing C lowering.~~ Implemented at whole-root lexical
   precision.
6. Extend places and loans field-by-field, with Rust compile-pass and
   compile-fail fixtures for every rule.

Keeping these commits separate makes the representation useful to non-Rust
backends and gives upstream reviewers a clear compatibility boundary.
