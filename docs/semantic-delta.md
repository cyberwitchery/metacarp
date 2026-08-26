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

## How closely the systems match today

It helps to separate ownership, loans, and lifetimes. They cooperate, but they
are not the same rule.

| Question | Rust | This Meta-Carp branch | Match |
| --- | --- | --- | --- |
| Who destroys an ordinary resource? | the last owning value, through `Drop` | the one owned binding, through `delete` | close |
| What does a by-value call do? | moves unless the type is `Copy` | moves an owned value; copies unmanaged data | close |
| Can the compiler silently duplicate an owner? | only through `Copy`; `Clone` is explicit | managed copies are explicit | intentionally stricter |
| May read-only aliases coexist? | yes, through `&T` | yes, through shared `Ref` effects | close at checked calls |
| May mutation coexist with another access? | no safe overlapping access during an active `&mut T` | no overlapping live root alias at a strict `unique` call | partial |
| When does a loan end? | normally at its final use in the control-flow graph | origin and move analysis is flow-sensitive, but named aliases are primarily lexical | Rust is more precise |
| Can a reference be reborrowed? | yes, with inferred nested lifetimes | forwarding a reference parameter is supported; general reborrow calculus is not | partial |
| Can fields be borrowed independently? | ordinary struct fields, yes | represented, but not yet collected for every strict call | representation only |
| Can array elements be borrowed independently? | generally requires a trusted splitting API | known indices/slices are representable as disjoint, but not fully collected | neither is automatic in general |
| Can one field be moved while others remain usable? | supported in cases such as non-`Drop` structs | ownership is generally tracked at binding/root granularity | no |
| How is a returned loan connected to inputs? | quantified lifetime parameters and inference | concrete `borrows-from` parameter indices | useful subset |
| What about interior mutability? | `UnsafeCell` and safe abstractions such as `Cell`/`RefCell` | no general corresponding static model | no |
| What crosses threads? | derived/implemented `Send` and `Sync` | unchecked host attestations only | no proof yet |

The strongest current correspondence is therefore an ordinary monomorphic FFI
function: values copy or transfer, references are shared or unique for the
call, and a borrowed result is tied to one or more inputs. Rust's higher-ranked
lifetimes, partial moves, two-phase borrows, interior mutability, and trait
reasoning are outside the current contract.

### `unique` and Rust `&mut` are related, not identical

Both enforce the same central law: while an exclusive loan is active, no
overlapping access is allowed. Rust makes this part of the reference type and
integrates it with control-flow lifetime inference and reborrowing. Meta-Carp
keeps `(Ref T)` as the representation type and records `UniqueBorrow` as an
effect of a concrete function or foreign call.

Consequently, translating a checked Meta-Carp `unique` parameter to Rust
`&mut T` is conservative for the call boundary. Translating arbitrary Carp
`Ref` code into arbitrary Rust reference code is not yet justified.

## Places and field access

A **place** is a path to storage rather than the value read from that storage.
Rust's Reference calls local variables, dereferences, fields, and indexes place
expressions. The Meta-Carp ownership IR uses the same useful decomposition:

```text
root + projection + projection + ...
```

Examples:

| Source idea | Normalized place |
| --- | --- |
| an entire `body` | `body` |
| `body.position` | `body . Field("position")` |
| `body.position.x` | `body . Field("position") . Field("x")` |
| `(*pointer).x` | `pointer . Deref . Field("x")` |
| `particles[3]` | `particles . Index(3)` |
| `particles[i]` | `particles . Index(?)` |
| `particles[0..4]` | `particles . Slice(0, 4)` |

The overlap algebra is conservative:

- different roots are disjoint;
- a whole place overlaps all of its subplaces, so `body` overlaps
  `body.position`;
- different known fields are disjoint;
- different known indices are disjoint;
- an index outside a known half-open slice is disjoint from that slice;
- known non-overlapping half-open slices are disjoint;
- unknown indices or bounds overlap compatible projections; and
- dereferences and mismatched projection kinds do not establish disjointness.

Three implementation stages must not be confused:

1. **Representation:** `OwnershipPlace` can express all the paths above.
2. **Collection:** the expression walker must recover the correct place for
   every read, write, borrow, move, drop, accessor, pattern, and call argument.
3. **Enforcement:** loan checking must compare all simultaneously live accesses
   with `places-overlap?`.

This branch has the representation and overlap decision, but collection is not
yet complete. Strict registered `unique` calls currently require a direct
borrow of a named owner or a forwarded reference and check the whole root.
Carp mutation intrinsics record unique effects but temporarily use relaxed
internal enforcement. The IR therefore describes the intended next calculus;
it must not be advertised as completed field-sensitive checking.

Rust provides a useful comparison. Its borrow checker understands that two
named struct fields are disjoint, but does not generally prove that two array
indices differ. The standard library packages the latter proof in trusted APIs
such as `split_at_mut`. Meta-Carp should use the same pattern where static
projection proof is unavailable: a small checked or trusted split primitive
returns references whose disjointness is explicit, instead of teaching the
compiler arbitrary container mathematics.

## Related work

This design sits between several established approaches:

- [Carp's memory model](https://github.com/carp-lang/Carp/blob/master/docs/Memory.md)
  supplies explicit move/borrow/copy operations and deterministic destruction.
- [Rust's place and borrow semantics](https://doc.rust-lang.org/reference/expressions/operator-expr.html)
  and [non-lexical lifetimes](https://rust-lang.github.io/rfcs/2094-nll.html)
  are the immediate model for shared/exclusive loans and control-flow-relative
  loan duration. [Oxide](https://arxiv.org/abs/1903.00982) isolates a formal
  Rust-like core, while [RustBelt](https://doi.org/10.1145/3158154) explains how
  unsafe library implementations can justify safe Rust interfaces.
- [Clean uniqueness typing](https://clean.cs.ru.nl/download/html_report/CleanRep.2.2_11.htm)
  permits destructive update behind functional interfaces when a value is
  known to be private.
- [Linear Haskell](https://arxiv.org/abs/1710.09756) attaches multiplicity to
  function arrows, showing another route for mixing ordinary functional code
  with linear resources and protocols.
- [Cyclone regions](https://www.cs.cornell.edu/projects/cyclone/papers/cyclone-regions.pdf)
  and unique pointers combine explicit regions, borrowed pointers, and
  individual resource ownership without changing pointer representation.
- [Perceus](https://www.microsoft.com/en-us/research/publication/perceus-garbage-free-reference-counting-with-reuse-2/)
  derives precise reference counts and in-place reuse from a functional core.
  It represents the complementary strategy: infer mutation/reuse from
  functional code rather than require all imperative intent to be stated as an
  affine procedure.
- [The Move borrow checker](https://arxiv.org/abs/2205.05181) demonstrates a
  modular, intraprocedural reference-safety analysis for resource values.

Carpaccio's use of arenas adds region lifetime management at the JVM/native
boundary. Arenas establish how long storage exists; shared/unique loans govern
what may access that live storage. One mechanism does not replace the other.

## Could Meta-Carp be a scripting language for Rust?

Potentially, if “scripting” means a trusted, interactive native extension
language. The current branch does not yet meet the stronger latency and hot
reload requirements implied by that phrase.

The ingredients fit the direction:

- Lisp syntax and macros for rapid construction;
- a resident compiler session and REPL;
- generated bindings to ordinary Cargo packages;
- affine checking that fits Rust APIs better than a garbage-collected dynamic
  language; and
- native code that can later be packaged without the REPL or JVM.

It would differ from an interpreted Rust scripting engine such as
[Rhai](https://rhai.rs/book/): compiled Carp has native privileges, native
failure modes, and compilation/link latency. It is closer to
[Mun's](https://mun-lang.org/) goal of native hot reload, but with an affine
Lisp and stable-C-ABI generation boundaries.

Carp already has a useful project-oriented REPL: it can load/reload files,
inspect types and generated C, run macros, and build from the same session.
However, the [compiler manual](https://carp-lang.github.io/carp-docs/Manual.html)
draws an important boundary. Dynamic/compile-time functions execute in the
compiler, while an ordinary `defn` expression is emitted through C, built as an
executable, and run as a child process. That is a good interactive development
interface, but not native hot replacement inside a running Rust process.

### Current interactive status

| Capability | Current status |
| --- | --- |
| Keep Core and compiler analysis resident | yes; `carp-session` reuses a warm base |
| Check a small edit without rebuilding Core | yes; measured warm inference is tens of milliseconds on the recorded hosts |
| Emit native source from a warm session | yes; the session emits a rooted C translation unit |
| Incrementally compile only a changed native definition | no; reusable object/code partitioning remains a planned `build-cell` milestone |
| Link and load a new generation while a host keeps running | supplied by Carpaccio's JVM host, not by standalone Meta-Carp |
| Redirect existing native callers to a replacement safely | no general mechanism yet |
| Retire code while owners, borrows, callbacks, or threads may refer to it | no complete lifetime protocol yet |
| Beat incremental Cargo/rustc edit-to-running latency | plausible for small C generations, but not established by a comparative benchmark |

The compiler bootstrap timings are not REPL timings: building a self-hosted
compiler processes the whole compiler. Conversely, a warm `infer-cell`
benchmark measures analysis but excludes the C compiler, linker, dynamic
loader, and host-wrapper refresh. A credible scripting benchmark must measure
the complete interval from replacing one definition to successfully calling
the replacement, and compare it with an already-warm incremental Cargo build.

The likely implementation is generation based. Keep Rust dependencies in
cached stable-ABI adapters, emit only the affected Carp roots, compile a small
position-independent object or shared library, and load it without restarting
the host. Calls inside one generation remain direct. Calls that must follow a
redefinition use an explicit stable entry table or versioned handle; old direct
callers continue to use their old generation. Unloading is permitted only after
all owners, loans, callbacks, threads, and function handles tied to that
generation have retired. Retaining old generations for the process lifetime is
a safe first policy, but not a complete long-running reload solution.

The description should therefore be **interactive affine native extension
language for Rust**, not an unqualified scripting language. It is promising for
trusted game, simulation, audio, scientific, and hardware kernels. It is not a
sandbox for untrusted scripts.

To make that claim practical still requires a Rust-native host crate, generated
safe Rust façades for Carp exports, affected-root/object caching, fast
incremental compilation and linking, generation-aware symbol replacement,
cross-platform compiler delivery, end-to-end latency benchmarks, and explicit
policies for callbacks, panics, threads, and outstanding owners during unload.

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

These limits should be stated as part of the proposal: the current work is an
intentionally conservative affine FFI seam, not a claim of Rust equivalence or
a complete safety proof.

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
