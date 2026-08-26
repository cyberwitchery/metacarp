# Semantic delta from upstream Meta-Carp

This branch has two goals that should be reviewed separately:

1. make Meta-Carp a reusable, resident compiler with a stable C-library
   boundary; and
2. make affine obligations at that boundary precise enough for safe Rust
   adapters.

It does **not** give Carp Rust's type system, use Rust's unstable native ABI, or
make every accepted Carp program valid Rust. Rust integration always crosses a
generated `extern "C"` adapter. The compiler contribution is a checkable
ownership contract on both sides of that ABI.

## What changes language semantics

Upstream Carp already distinguishes copied values, owned values, and references
and inserts destruction for owned values. This branch makes four additional
facts explicit:

- a borrow is `Shared` or `Unique`;
- an access names a structured place (root plus dereference, field, index, or
  slice projections);
- each concrete function has parameter effects (`Copy`, `Take`,
  `SharedBorrow`, or `UniqueBorrow`) and a result effect, including which
  parameters its result may borrow from; and
- a registered foreign function may declare the same four parameter modes.

The source-level extension is the optional final mode vector on `register`:

```clojure
(register mutate
  (Fn [(Ref Item) Int] ())
  "item_mutate"
  [unique copy])
```

Omitting it preserves the old classification: unmanaged by-value values copy,
owned by-value values move, and references are shared. An explicit declaration
must agree with that concrete ownership class. It may refine a reference from
`shared` to `unique`, but cannot disguise an owned move as `copy` or an
unmanaged copy as `take`.

A call through a strict `unique` contract must borrow a directly named owner or
forward an existing reference parameter. The checker rejects a simultaneously
live alias and another argument which moves or borrows the same owner. That
requirement propagates through ordinary Carp wrappers, so an exported wrapper
cannot erase the obligation.

Reusable-library emission also rejects a result that borrows from a consumed
by-value parameter. The ordinary executable path retains legacy behavior; the
stricter rule is attached to the new interop boundary where a host would
otherwise receive a dangling pointer.

## Correspondence with Rust

| Rust adapter surface | Meta-Carp contract | Status |
| --- | --- | --- |
| scalar or unmanaged `T` by value | `copy` | checked |
| owned handle/value `T` by value | `take` | checked |
| `&T` | `(Ref T)` plus `shared` | checked conservatively |
| `&mut T` | `(Ref T)` plus `unique` | checked at whole-owner call precision |
| return tied to an input lifetime | result `borrows-from` indices | inferred for shared lifetimes and direct tail borrows |
| `Fn` callback | borrowed closure plus shared callback contract | adapter-owned |
| `FnMut` callback | borrowed closure plus unique callback contract | partly representable; callback lifetime/thread policy is adapter-owned |
| `FnOnce` callback | owned closure passed with `take` | partly representable; adapter generation remains responsible |
| `Send` / `Sync` | no compiler proof yet | unsafe host attestation only |
| traits, futures, Rust enums, const generics | opaque handles or stable carrier functions | Carpaccio/Rust adapter concern |

The important semantic fit is affine transfer plus shared/unique loans—not
layout coincidence. `repr(C)` records, pointer/length views, and opaque handles
can be zero-copy, while Rust-owned containers and trait objects remain behind
handles unless an adapter deliberately exposes a stable representation.

## Where this is deliberately weaker than Rust

- `Ref` remains one Carp type; shared versus unique is an effect in the
  ownership plan and foreign contract, not a distinct source type.
- Places have a projection algebra, but strict foreign-call collection is
  currently whole-root. Field-sensitive collection is a follow-up.
- Built-in Carp mutation produces `UniqueBorrow` summaries but is not yet
  checked with the strict foreign-call rule. Enabling that now would reject
  established disjoint-field patterns because their projections are not fully
  retained.
- Lifetimes are relations in concrete function summaries, not universally
  quantified Rust lifetime parameters.
- `unsafe-sendable` and `requires-send` are preserved attestations, not derived
  `Send` or `Sync` evidence.
- No Rust ABI is consumed. Panics, unloading, callback threads, and async
  executors remain explicit adapter/host policies.

These limits should be stated as part of the proposal: the current work is a
sound, conservative affine FFI seam, not a claim of Rust equivalence.

## What does not intentionally change semantics

Several large parts of the branch are compiler correctness or embedding work
and should not be justified as Rust changes:

- record/sum C layout, aggregate boxing, recursive nominal ordering, strict C99
  definitions, closure cleanup, and qualified ownership identity align emitted
  C and modern Carp programs with the reference implementation;
- rooted library emission, include/link inputs, resident sessions, structured
  reports, and the optional CBOR host expose existing compiler phases to other
  processes; and
- source bootstrap bundles and CI make those paths reproducible.

Keeping these categories separate makes regressions and compatibility claims
reviewable.

## Suggested upstream sequence

1. C/reference-compatibility fixes, each with its focused regression.
2. Backend-neutral places, borrow modes, normalized accesses, and serializers,
   with no new rejection behavior.
3. Function summaries and result borrow relations.
4. Foreign contracts with signature-derived defaults.
5. Optional `register` mode syntax and concrete mode validation.
6. Strict unique-call checking and transitive wrapper effects.
7. Strict reusable-library boundary validation.
8. Rooted library artifacts and the transport-neutral resident session.
9. CBOR hosting and build/bootstrap infrastructure as separate integrations.

The branch can remain an integration branch for Carpaccio, but this order gives
upstream a set of smaller semantic decisions instead of one all-or-nothing
compiler/hosting proposal.
