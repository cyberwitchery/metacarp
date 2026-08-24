# Invariant and danger map

Maintainer-oriented. Not an architecture overview: this is the list of
cross-module contracts where a locally reasonable change breaks something far
away. Compiled 2026-08-24 at HEAD `105ae80` from a whole-repo review,
adversarial probes, and the regression-test work of the same date, then
updated as fixes landed; line numbers are against that HEAD and will drift.

Each entry is tagged:

- **[semantic]** — a true invariant of the language/compiler semantics;
  cannot be designed away, only enforced better.
- **[implementation]** — a contract of the current design; a redesign could
  remove it, but until then it binds.
- **[accident]** — looks like an invariant, is actually historical residue;
  safe to change deliberately, dangerous to change accidentally.

Enforcement legend: types / validation / tests / construction order /
convention / none.

---

## Identity

### 1. Expression ids survive every rewrite; synthesized nodes never collide with real ones [implementation]

**Invariant.** Every rewrite from `CoreExpr` through `SpecializedExpr` to
backend lowering copies the node's id. Nodes synthesized after resolution use
`-1` or draw from an allocator seeded past the module's watermark
(`seed-backend-locals!` counts down from below the lowest real local,
carp-backend.carp:26-31; `*hoist-serial*` is raised above every specialized
global id, :1964).

**Participants.** carp-ir (`IndexedCoreExpr`, `CoreIR.index-call-sites`,
`identify-generated`), carp-infer (node-types keyed by (owner, id)),
carp-specialize (calls resolved by id), carp-ownership (`OwnershipAction`
sites, duplicate-id rejection per context), carp-backend (`ScopeDelete.site`,
match-temp naming), the source map (`install-source-map!`,
carp-compiler.carp:3670, keyed by id), carp-session provenance
(`CoreProvenance.node-span`).

**Why.** Ids are the only cross-phase join key. Types, spans, ownership
actions, and line directives all attach by id; the IR carries none of them.

**Failure mode.** A pass that clones a subtree without renumbering: ownership
rejects duplicates within a context (loud), but the source map and session
span lookups silently return the first match — the debugger points at the
wrong line, session reports mis-span, no gate fires. A pass that renumbers
real nodes: session identity reuse and `#line` mapping silently detach.

**Enforced by.** Validation for globals only (`CoreIR.duplicate-global-id`,
driver :3834-3840, per category); ownership's per-context uniqueness check;
otherwise convention.

**Strongest evidence.** The `ScopeDelete.site` field exists because set!-site
deletes were confused with let-scope deletes on the same binder during the
gen-2 leak hunt (self-host arc, 2026-07-22; see `carp-compiler-goal-self-host`
history). The global id collision bug (length-based ids aliasing env
bindings) is the ancestral incident.

**Before changing, inspect.** `Ownership.prepare`'s id validation;
`cleanup-for`'s (binder, site) matching; `install-source-map!`;
`Resolve.module-with-provenance-against-reusing`; `identify-generated`.

### 2. Id ranges must never carry semantics [implementation]

**Invariant.** No behavior may branch on the numeric range of an id.
Provenance that used to live in ranges lives in explicit registries
(`*fallback-str-ids*`, carp-compiler.carp:21).

**Why.** The WP-A migration found that the old `(Int.< id 9800000)` check
encoded more than its comment said (it classified both generic fallback strs
and per-instance strs as derived); porting it naively broke derived-str
dispatch for generic instances.

**Failure mode.** Reintroducing a range check ties correctness to allocation
strategy; any allocator change (including the `-g` path, see #21) then
changes semantics between builds.

**Enforced by.** Convention only. **Evidence:** the WP-A incident (pre-release,
not in git history — repo history starts at the squash `701be94`).

**Before changing.** Grep for comparisons against large integer literals near
id handling; check `*fallback-str-ids*` and any new provenance registry.

### 3. Cross-category id sharing is identity, not duplication [implementation]

**Invariant.** A constructor declaration and its callable share one id on
purpose; `duplicate-global-id` checks per category only.

**Failure mode.** "Fixing" the validator to check globally rejects every
constructor. Conversely, extending id sharing to a new category without
updating the validator's category map silently disables the check there.

**Enforced by.** Tests (carp-ir suite: cross-category sharing asserted as
identity). **Before changing:** carp-ir/test assertions on
`duplicate-global-id`.

### 4. Allocation order is part of the ABI [implementation]

**Invariant.** Ids leak into C symbol names (`L<len>_name_<id>` locals, hoist
serials, mangles). Therefore id allocation must be deterministic, and the
byte-identical gen2/gen3 fixpoint (`scripts/check-fixed-point.sh`, CI
self-host job) is transitively a determinism gate over the whole compiler.

**Failure mode.** Any nondeterministic iteration or allocation shows up as a
fixpoint flake in CI — good. The subtle cost: issue #26's plan to
content-address compiled core objects is in tension with this; an upstream id
perturbation renames every downstream symbol and defeats such a cache.

**Enforced by.** Tests (fixpoint, every commit, two OSes).
**Before changing** any allocator: run `run-assurance.sh self`, not just the
phase suites.

---

## Inference and the normalization boundary

### 5. Merged inference results carry an empty substitution; every trace is normalized by its producing run first [implementation, load-bearing]

**Invariant.** An `InferredModule` handed to the back half
(`CarpCompiler.compile-inferred-module-with`, carp-compiler.carp:3756) that
was merged from several inference runs must contain no trace type that still
needs any substitution; its `substitution` field is empty by construction.
`normalized-analysis` / `concat-analysis`
(carp-session/carp-session.carp:99-200) are the only sanctioned merge path.

**Why.** Batch code (carp-specialize :986, :1010, :1871 and the
`*normalized-node-types*` memo) repairs raw traces by applying
`InferredModule.substitution` — which for a merged module is empty, and
`Type.apply`'s empty fast path (carp-types:206) makes the omission silent.

**Failure mode.** Traces retaining solver variables specialize fine until a
later commit makes a dormant polymorphic definition reachable, then fail with
an unresolved-variable/non-concrete rejection days after the actual mistake.
Lived in-tree 2026-07-29 (`7142ddc`) to 2026-08-01 (`f61045a`).

**Enforced by.** Convention + docstring (carp-session:99-103) + one real-Core
regression test (`emits-after-committed-empty-map?`,
carp-session/test/core.carp:60). Adversarially re-tested 2026-08-24 (chained
overlay dormancy, closures, generic-instance derivation, redefinition,
interleaved-query determinism) — held; see the history of `f61045a` and
`37d4fbc` for how the invariant was found.

**Before changing.** Anything that caches or persists a trace type across a
merge boundary; `inferred-environment-with-analysis`; `session-analysis`;
`append-inferred-analysis` call sites in the four `finish-*-overlay`
committers.

### 6. The normalized-base memo is valid only because the base is immutable and `set-overlay!` is the sole overlay mutation point [implementation]

**Participants.** `CompilerSession.analysis` (one-slot cache, doc: "the base
cannot change, so it never goes stale", carp-session:87-89), `set-overlay!`
(:1144-1150), `prepare-emit`.

**Failure mode.** A future "patch the base in place" feature, or a second
overlay mutation path that skips `set-overlay!`, serves stale normalized
traces — the same class as #5 with a fresh entry point.

**Enforced by.** Convention + the docstrings. **Before changing:** every
`Array.aset!` on `CompilerSession.overlay`.

### 7. The value restriction: only syntactic values generalize in lets [semantic]

**Invariant.** `generalizable-value?` (carp-infer) restricts let
generalization to literals/lambdas/references; application results get
monomorphic schemes.

**Why/failure.** Without it, `(let [na (allocate n)] ...)` generalizes to
`forall a. (Array a)` and every use instantiates a fresh element variable —
mutable-array element sharing breaks. This masked three other inference bugs
for a day (2026-07-06 arc: allocate's result type, suffix/prefix signatures,
call-type snapshotting).

**Enforced by.** Code + the HOF/copy-map fixtures. This is standard HM; do
not "simplify" it away.

### 8. Recorded call types reflect post-argument-unification solver state [implementation]

**Invariant.** The callee type recorded per `CallSite` is taken after the
argument unifications' solver bindings apply (the `Type.solver-apply-at`
wrap in carp-infer's Call case).

**Failure mode.** Specialize monomorphizes against a stale signature; a
closure's return type never propagates; "backend function signature is not
concrete" at a distance. **Enforced by** code + the copy-map/HOF fixtures.

### 9. Derived deleters carry a CoreSignature; derived copiers must NOT [implementation, sharp]

**Invariant.** `Derive.deletes` attaches a `CoreSignature (Fn [T] Unit)` to
each generated deleter because `OwnershipClassify.signature-arg0` reads
signatures (and builtins) to build the owned-facts table. `Derive.copies`
attaches none — a generated signature would pin a concrete ref lifetime that
cannot unify with the `copy` interface's lifetime variable; the instance is
pinned instead by a `(the (Ref T))`-style `Annotation` on the match
scrutinee.

**Failure mode, both directions.** Add a sig to copiers: "cannot unify X with
reference" on every generic copier. Remove the deleters' sig: the facts table
stops seeing derived deleters, the types silently classify unmanaged, and the
program leaks with no diagnostic.

**Enforced by.** Nothing mechanical; integration tests
(`derives-generic-deftype-copier?` / `-deleter?`) go red on the loud
direction, the leak direction only trips the memory-flavored suites.

**Before changing.** `signature-arg0`'s sources (builtins AND signatures);
`infer-annotation`; the `managed-renderable?` Annotation case in the backend.

---

## Derive, fixpoint, ownership

### 10. Derive pass order is semantic: copies before deletes, strs before close-generics [implementation]

**Invariant.** `derive-core-owned` (carp-compiler.carp:3557) runs
typedefs → accessors → pair-refs → **copies → deletes** → **strs →
close-generics**. `Derive.derive-target-keys` excludes types that already
have a deleter, so running deletes first silently suppresses copier
generation; strs must precede close-generics so the generic fallback exists
while per-instance strs win dispatch (comment at :3830-3832).

**Failure mode.** Reordering compiles clean and produces shallow-aliasing
copies (double-free once branch deletes fire — the exact shape of the
accessor-copy bug fixed during the gen-2 hunt) or field-less generic `str`
output.

**Enforced by.** Construction order + comments; integration copier/deleter
tests catch the loud half. **Before changing:** `derive-target-keys`'s
exclusion logic; the `strs`-vs-instance-str dispatch.

### 11. Ownership reports; only the driver iterates [implementation]

**Invariant.** `Ownership.prepare` never calls specialize. Requirements
(`DeleteFunction[T]`, copier demands, closure-capture copiers via
`with-closure-delete-requirements`, carp-compiler:2833) are data; the
`specialize-closed` fixpoint (carp-compiler.carp:2913) is the only loop, and
termination rests on requirement types deduping by `CAbi.type-key` into a
finite set.

**Failure mode.** Ownership calling into specialize reintroduces the phase
cycle the design exists to prevent. Worse: a requirement generator that mints
a *different* instance each round (anything not closed under the substitution
that discovered it) loops forever — there is **no iteration cap and no cycle
detector**. The reference compiler shares this exposure (polymorphic
recursion); it is not a reason to add a cap casually, but know it is absent.

**Enforced by.** Architecture + tests (`plans-delete-requirement?`,
`specializes-delete-on-demand?`). **Before changing:** `new-delete-types`,
`new-types-among`, `closure-capture-types`, and the dedup key they share.

### 12. Every managed-element array that reaches a delete site must have its deep deleter demanded; the sentinel is a fallback for unmanaged elements only [implementation, historically fatal]

**Invariant.** `lookup-delete-symbol` (carp-backend.carp:295) consults the
driver-built table first; the `__carp_array_free` sentinel (shallow
`CARP_FREE(data)`) fires only on a miss (sites :475, :1442-1447, :1624-1640,
:1733, :1761). Soundness = the ownership fixpoint demanded an `ArrayDelete`
instance for every managed-element array type, so the table always hits for
those.

**Failure mode.** A miss for `(Array String)` silently shallow-frees: every
element leaks. This — via a renderer arm variant, see #14 — was the single
largest contributor to the gen-2 self-compile balloon (13 of 14.8 GB).

**Enforced by.** The green guard
`deep-deletes-managed-array-element-payloads?` (test/carp-compiler.carp,
added 2026-08-24; covers let-bound and hoisted sites). A cheap upgrade:
error, under a debug flag, when the sentinel is selected while the element
type classifies owned.

**Before changing.** `delete-symbols-for` (driver :2990) keying,
`array-free-symbol`, and every fallback site above.

### 13. Symbol tables key asymmetrically: deleters by arg0 type, copiers by return type [implementation]

`delete-symbols-for` keys by the deleter's argument type-key;
`copy-symbols-for` (:3018) by the copier's **return** type-key (copy takes a
ref, returns the owned value). Unifying them "for consistency" empties one
table; everything still compiles; closures stop deep-copying captures or
deletes stop resolving. Enforced by code + the closure-capture and copier
integration tests. Inspect both functions together, always.

---

## Primitive lowering

### 14. One lowering authority per primitive; a renderer arm must be semantically identical to the definition it bypasses [implementation, historically fatal]

**Invariant.** Call-site lowering knowledge lives in two places: the registry
(payloads: `PrimitiveLowering.ParameterizedTemplate`, `template-c-for`
source templates, externals) and the id-keyed cond in
`render-value-expression`'s GlobalCall case
(carp-c-expressions.carp:256-558; ids 5,6,8,9,10,12,13,14,15,16,17,18,21,48,
49,65,70,73-75 plus symbol-keyed sentinel/closure prefixes). The arm fires
**regardless** of what the declaration table holds. Therefore: adding an arm
for a primitive that has a template is only sound if the arm is semantically
identical to calling the template.

**Failure mode.** The id-72 incident: an inline shallow `CARP_FREE` arm for
`Array.delete` silently clobbered the deep template for every derived
deleter's array field. No diagnostic; discovered by `leaks(1)` at
self-compile scale.

**Enforced by.** Nothing mechanical. Partial guards:
`never-silently-defers-primitive-value-lowering?` (2026-08-24) and
`bench/nbody-codegen.sh`'s codegen regex (manual). A registry-side
`InlineCall` payload + a validate rule forbidding arm/payload overlap would
make recurrence unrepresentable; until then, treat the cond as a shadow
registry.

**Before adding/changing a primitive.** The cond's id list; `template-c-for`
names (carp-primitives:643-680); `PrimitiveTemplate` descriptors; and note
`endo-map` has a bare-name source template while `push-back` relies on
overload dispatch to the qualified one — two mechanisms for the same
bare/qualified pairing (tested working for push-back, exit 2, 2026-08-24).

### 15. The length trio's dispatch is mirrored in two files and must stay identical [implementation]

Arm: carp-c-expressions.carp:395-424 (String/Pattern → strlen, else `.len`,
behind-ref variants). Template body: `CollectionLength`,
carp-c-declarations.carp:1538-1576, comment "the body mirrors that call
lowering". The template exists solely for value-position references
(`&Array.length` passed to a HOF); call sites always take the arm. Editing
one dispatch without the other produces value-position/call-site divergence
for String/Pattern lengths only — the id-72 class at smaller scale. Enforced
by the two comments pointing at each other; nothing else.

### 16. Arm-only primitives have prototypes but no bodies; value-position use must keep being rejected [implementation]

`prototype` emits a declaration for plain intrinsics
(carp-c-declarations.carp:331-341) but nothing defines them; today
value-position references die in the backend (observed: "no concrete deleter
for an owned local" intercepts first). If a change makes such a reference
survive to emission, the result is a **link** error the string-assertion
suites cannot see. Guard: `never-silently-defers-primitive-value-lowering?`
encodes "reject, or emit a definition". If you want `&Array.unsafe-nth` to
work, follow the length pattern (#15), not an exemption.

---

## Compile-time language

### 17. `ExpandConfig.init [@"Dynamic"]` is load-bearing at every real driver [implementation]

Sites: main.carp:734/:1156/:1166, carp-session:1140. Marking `Dynamic` a
prelude is what lets quasiquote's helpers (`reduce`, `map`, `collect-into`,
living in Core's List/Dynamic modules) resolve bare inside macro expansions.
A new driver that forgets it fails with "unknown binding reduce" only for
backtick-using macros, far from the actual omission. Enforced by the
integration test `loads-real-core-gensym?` (test/carp-compiler.carp:465+) and
the expand suites; a new driver has no such guard until it copies the config.

### 18. Two compile-time file stacks; never conflate them [implementation]

`*ct-load-stack*` (drives `current-file`/`relative-to` semantics via the
`Unsafe.load-stack` builtin) vs `*ct-step-files*` (trace attribution;
carp-ct-eval:53-60, comment explicitly warns). Conflating them breaks
relative loads inside foreign macros or mis-attributes trace steps. Enforced
by comments + the session macro-provenance tests
(`macro-generated-errors-anchor-to-invocations?` etc., from `f3e54bb`).

### 19. ct-eval dispatch order is reference semantics: builtins beat same-named definitions [semantic (fidelity)]

`apply-builtin` runs before environment lookup (carp-ct-eval:2763-2770).
carp-ct-infer's duplicated ~91-name `builtin?` table encodes the same rule by
hand. Reordering "to respect user definitions" diverges from reference macro
semantics — and `diff-expansion.sh`'s 6-program corpus will probably not
catch it. The oracle corpus (`carp-ct-infer/corpus/oracle.carp`) would, but
is not in CI. Compile-time strings are Unicode-character-indexed
(`9ae7212`, matching reference Commands.hs) while runtime strings are
byte-indexed — same fidelity class: these asymmetries are upstream's, not
ours to normalize.

### 20. Transient expansion runs against a snapshot copy [implementation]

`ExpandSnapshot` doc (carp-expand:32-34): transient source expands against a
copy so compile-time `set!` effects and failures cannot mutate the warm base.
This single property is what makes every session query transactional.
Enforced by tests (`warm-cells-are-transactional-and-spanned?`,
`warm-expansion-queries-are-transactional?`). Before threading any new
mutable ct-state into expansion, add it to the snapshot's copy path or those
tests go red — they are the tripwire, trust them.

---

## Session bookkeeping

### 21. Overlay replay is per-input — FIXED 2026-08-24 [was: per-definition parallel arrays, violated by upsert]

`inputs`/`references` hold one slot per committed INPUT (the replay list,
reuse identity meaningful only for single-definition inputs);
`definitions`/`dependencies` hold one slot per definition and are replay
OUTPUTS, never replayed. `repeats-previous?` is gone — the 2026-08-24
corruption (name-keyed upsert swapping one slot of a multi-definition run,
duplicating the input on replay and silently discarding the accepted edit)
is unrepresentable. Name-keyed `upsert`/`remove` refuse a definition owned by
a multi-definition input, directing to `upsert-input`/`remove-input`;
`upsert-input` replaces in place (drop+append used to move the input to the
end of the replay list, breaking later-committed dependents — found by the
same adversarial battery). Green guard: `multi-definition-input-upsert-is-atomic?`
in carp-session/test/carp-session.carp.

### 22. Binding follows the latest committed definition of a name — DECIDED and implemented 2026-08-24 [was: base-shadowing fell through invalidation]

Policy chosen: convergence. Replacing an overlay definition or shadowing a
base binding rebinds that name's committed dependents (transitively) to the
new definition; commit order no longer changes the final semantic state.
Mechanism: replay order is binding order, so a shadowing commit moves the
inputs owning its dependents after itself (`reordered-for-shadow`); moved
dependents deliberately DROP their retained identities (re-binding while
keeping the old global identity misresolves the reused replay — found
empirically). `upsert-input` detects shadowing post-rebuild and replays once
more reordered. `remove` keeps its drop semantics: removing a shadow drops
its dependents' inputs and restores the base binding for new cells. Green
guard: `base-shadow-is-commit-order-independent?` in the wired session suite;
the adversarial set (two-level dependents, shadow-of-shadow, remove
restoring the base, independents untouched) was probed before the mechanism
landed.

### 23. `emit-cell` copies the allocator; `infer-cell` deliberately does not [implementation]

Emit's non-mutation and byte-determinism contract rests on the copy
(:1782 vs :1843). Verified 2026-08-24: interleaving allocator-advancing
queries between two emits still yields byte-identical C. Making emit share
the live allocator breaks
`emit-cell-is-deterministic-and-non-mutating?`; making infer-cell copy is
safe (and would make "query" mechanically read-only).

---

## Bootstrap and core loading

### 24. Boot prelude order: `add-c`/`relative-include` are redefined AFTER Core loads [implementation]

main.carp:647-649: Core's Dynamic.carp defines `add-c` through a `Project`
"cmod" config this compiler does not track; the boot redefinitions must land
after `(load "Core.carp")` or Core's version wins and add-c-using programs
fail obscurely. Enforced by construction order + comment only.

### 25. The compiler prelude (`with-compiler-prelude`) belongs to Core-loading callers, not to `compile-module-with` [implementation]

The prelude defines `prefix`/`suffix` via `slice`, which only Core provides;
injecting it in the pure entry points would break every bare (core-less)
compile — including most of the integration suite. `ModuleLoader.load`'s own
test pins that the loader returns exactly the loaded forms. Observed corollary:
`--no-core` combined with `-c` currently dies on "unknown binding slice"
(2026-08-24, uncharacterized — check `no_core_build` in the sweep for the
supported invocation before "fixing" either side).

### 26. Two hand-synchronized world definitions: main.carp's core file list and carp-core-loader's [accident]

Verified byte-identical today (diff of extracted lists, 2026-08-24), in sync
only by discipline. Failure is mostly loud ("module source not found") since
inclusion is actually driven by Core.carp's own load directives; the silent
window is boot-prelude semantic drift between CLI and session. Should be one
shared manifest; until then, upstream core changes (issue #15 / PR #28) must
touch both.

---

## Building the compiler itself (reference-carp meta-invariants)

### 27. Never write a multi-body `let` [semantic, about the reference toolchain]

Reference Carp silently drops trailing `let` body forms. This produced a real
gen-2 semantic divergence (an instantiate counter that never ran in
host-built binaries but ran in self-built ones, once our implicit-do fix made
self honor it). Always `let-do`. Enforced partially by angler's form rules;
the fixpoint gate is the real net.

### 28. `carp -b` exits 0 on type errors, leaving the stale binary [accident, toolchain]

Grep the build log for errors; never trust exit code or binary mtime after a
compiler-source edit. Cost multiple misdiagnosis cycles historically.

---

## Addendum: 2026-08-24 experiment results

Five directed experiments against the map above; full reproducers in
`test/regressions.carp` and `carp-session/test/regressions.carp` (red suites,
unwired).

### 29. Move-after-move — FIXED 2026-08-24 [was: confirmed soundness hole]

The ownership pass rejected borrows used after a move (WP4) but never got
double-move rejection (a deferred WP2 item): both
`(do (consume w) (consume w))` and `(while (flip) (consume w))` on an owned
`w` were accepted and the emitted C consumed twice; the reference rejects
both ("Using a given-away value 'w'"). The conformance sweep was blind
because every upstream use-after-move test uses a *reference* after the
move. **Fix:** `state-mark-moved-checked` in carp-ownership flags a
consuming move of an already-moved local (flag 3, error "an owned value is
used after it was moved in F"); the pre-existing two-pass `While` analysis
makes loop-carried second moves land on the same check. The `Let`
scope-death mark stays on the unchecked variant deliberately — dying after
being consumed is the normal case. Green guards graduated into
test/carp-compiler.carp: `rejects-sequential-move-after-move?`,
`rejects-loop-carried-move?`.

### 30. `*local-binder-serial*` — FIXED 2026-08-24 [was: process-global, never reset]

Local binder ids are `-(serial * 1048576 + pos + 1)` and reach C symbols
(`L<len>_<name>_<id>`); the serial used to be process-global, so two
identically-driven sessions in one process emitted different bytes for the
same cell (observed: `L1_x__x45_3145841` vs `L1_x__x45_6291569`, serial 3
vs 6). **Fix:** the serial resets in `module-inner`'s per-resolution
preamble, making emission a function of module content, not process
history; batch behavior is byte-identical (one resolution per process,
fixpoint-verified). Known accepted tradeoff: locals from *different*
resolution runs can now share ids, which downstream is harmless (locals are
body-scoped everywhere) except for cross-run `CoreProvenance.binding-span`
joins keyed by (id, name, global) — a diagnostics-quality edge, noted here
so nobody rediscovers it as a mystery. Green guard graduated into
carp-session/test/carp-session.carp:
`cross-session-emits-are-deterministic?`.

### 31. Compile-time arithmetic — FIXED 2026-08-24 [was: Int-only vs reference two-domain]

ct-eval now mirrors the pinned reference exactly (Commands.hs commandArith /
commandDiv / commandRound, Types.hs promoteNumber, Obj.hs Number): two-domain
`CtNumber` (integral Long / floating Double) with width promotion
Byte < Int < Long < Float < Double; floor division for integral `/` (Core's
dynamic `imod` depends on it); half-to-even `round` with width-preserving
integral passthrough; the shadowing builtin arms for `mod`/`neg`/`inc`/`dec`
are DELETED so Core's real dynamic definitions run. The surface printer
renders whole-number floats as `3.0f` and non-finite doubles as
`Infinity`/`-Infinity`/`NaN`, since compile-time `str` makes the spelling
observable. Verified 31/31 against the pin-identical reference binary; permanent
parity guard:
test/expansion-corpus/numeric-promotion.carp (wired into diff-expansion,
now 7 programs) plus `expands-float-macro-arithmetic?` in the integration
suite. ct-infer's shape tables updated to match (arithmetic domain/range =
num; the four names removed from its builtin table). Known remaining edges:
integral width is Long-backed (reader-level literal width limits predate
this); reference crashes on integral division by zero where we reject
gracefully (rejection-parity holds).

### 32. Non-regular recursive generics hang both compilers [shared upstream weakness]

`(deftype (Nest a) (Flat [a]) (Deep [(Box (Nest (Pair a a)))]))` plus one
use diverges the delete-derivation worklist: ours times out at 60s, the
reference at 90s. Confirms entry #11's "no cap, no diagnostic" concretely;
conformance-equal, so a fix is a quality improvement, not a divergence
repair.

### Verified safe by the same experiments

Type generations compose with the warm session path (a committed
`deftype` shadow types, rejects old uses, and both generations emit in one
program); overlay-committed interface implementations dispatch for dormant
base generic callers; same-session emission of a let-bearing cell is
byte-identical.

## Five highest-risk places to modify without whole-system knowledge

1. `render-value-expression`'s GlobalCall cond (carp-c-expressions:256-558)
   — every arm silently outranks the declaration table (#14, #15, #16).
2. The `specialize-closed` fixpoint and its requirement generators
   (carp-compiler:2913, 2815-2870) — termination and memory-soundness both
   live here, uncapped (#11, #12).
3. The Derive blocks in carp-compiler.carp — order-sensitive (#10) and
   sig-asymmetric (#9), with the failure modes mostly silent.
4. The session overlay's parallel arrays and replay
   (carp-session:920-1050, 1494-1620) — one already-confirmed silent-loss
   bug; every invariant here is by construction only (#21, #22).
5. Anything that stores or merges inference traces
   (carp-session:95-225, carp-infer's warm entries, compile-inferred-module-*)
   — the normalization boundary (#5, #6): wrong changes stay green for days.

## Five invariants that should become mechanically enforced

1. **#5**: assert on entry to `compile-inferred-module-with` that the
   incoming substitution is empty (one length check; converts the silent
   class to a loud one).
2. **#14**: registry-side `InlineCall` payloads + a `validate-specs` rule
   that a primitive has exactly one call-site authority; export the
   remaining arm ids as data and test the intersection is the declared
   paired set.
3. **#12**: debug-gated error when the array sentinel is selected while the
   element type classifies owned.
4. **#21**: replace the four parallel arrays with per-input records so
   contiguity is unrepresentable (and `repeats-previous?` disappears).
5. **#26**: one shared core manifest module consumed by both main.carp and
   carp-core-loader.

## Five things that look fragile but are actually safe

1. **`-g` vs release divergence**: the debug path allocates ids differently
   (`module-ceiling`), but emitted C is byte-identical modulo `#line` and
   blank lines in RefLift-exercising tests (measured 2026-08-24). Worry when
   an id-range behavior returns (#2), not before.
2. **Bare generic primitives** (`push-back`, etc.) with no bare template:
   overload dispatch resolves them to the qualified template; compiled, ran,
   exit 2. The endo-map bare template is belt-and-suspenders, not a pattern
   to replicate.
3. **The exact-count `known_gaps` carve-outs** in run-carp-suite-self.sh:
   deliberately brittle — any drift in a gap's shape becomes a hard failure
   instead of a quietly widening exemption. Do not loosen.
4. **The dead stack-closure renderer** (`render-closure-construction`,
   unreferenced) and `LineMap.reset!`: inert. Deleting them is safe;
   resurrecting the stack env without consulting the ownership pass is not.
5. **`infer-cell` advancing the live allocator**: burns id space, but
   emission determinism is unaffected because emit copies (verified with
   interleaved queries). Cosmetic, not a correctness hole.
