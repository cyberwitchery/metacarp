# The calculus behind the BAS checker

This writes down what `carp-ct-typecheck/bas.carp` and `bas-check.carp`
implement, and argues why a definition it accepts does not go wrong. The
argument leans on MLstruct+ as Chau and Parreaux present it (POPL 2026,
"The Simple Essence of Boolean-Algebraic Subtyping", §3 and §4); where the
checker departs from that system, the departure is named and what it needs
is stated as an obligation. Nothing here is mechanised.

## 1. The claim

The semantics the claim is about is written down in `docs/ct-semantics.md`.
Compile-time evaluation either answers a value, raises an error, or does not
terminate. Errors split in two:

- **type errors**: a builtin given a kind of value it does not accept, `car`
  or `cdr` of something that is not a cons, a call of something that is not
  a function or of a function with the wrong number of arguments, an `if` or
  `while` whose condition is not a bool, a value that is not a form where
  the evaluator reads a form, an unbound name;
- **intended errors**: a builtin whose job is to fail (`macro-error` and the
  like, typed with result ⊥), errors raised inside code run by `eval`, and a
  macro that fails to expand at run time.

**Claim.** Let every definition group of a program check. Then running any
of its definitions on arguments of its parameter types raises no type error.
It may answer a value of its result type, raise an intended error, or not
terminate.

The claim holds under the obligations O1 to O5 in §7 (O1 is reduced to
the paper's theorem in §7.1). The census does not check whole programs: it checks each
Core definition with what it depends on. A failing definition is not
covered, and §6 says what that means for the ones that pass.

## 2. Values

The values are those of `CtValue`: syntax (literals, lists, arrays, static
arrays, dictionaries, comments, patterns), closures, builtins, macros, and
lists and arrays holding a value that is not syntax. Each value has one
**constructed type**, `BVal.of-value`:

- a literal: its kind's tag (`#Int`, `#String`, …); a symbol or bool: the
  final tag of that literal (`#Symbol:foo`, `#True`);
- a sequence: a chain of cells `#KCons ⊓ {car : τ} ⊓ {cdr : π}` ending in
  `#KNil`, for `K` in List, Array, Static; an array's tail is a list,
  because that is what the evaluator's `cdr` of an array answers. A list or
  array holding a non-form has the same type as the form would; its `car`
  is simply not a form type;
- a closure, a builtin, a macro: `#Closure`, `#Builtin`, `#Macro`. A
  builtin known by name gets its builtin type, `#Builtin ⊓ (A → R)`.

The tags form a tree under `#Obj`; a tag is below its ancestors, unrelated
tags are disjoint, literal tags are final. Closed sets (`Bool`, `Number`,
`List`, `Nil`, …) are unions of final tags, not tags, so a later subtag
cannot widen them.

## 3. Types and subtyping

    τ ::= ⊤ | ⊥ | #T | τ → τ | {car : τ} | {cdr : τ} | α | τ ⊔ τ | τ ⊓ τ | ¬τ

Functions take one argument, an argument list built from `#ArgsNil` and
`#ArgsCons` cells, so `(f a b)` constrains `f` to
`(#ArgsCons ⊓ {car : A} ⊓ {cdr : #ArgsCons ⊓ {car : B} ⊓ {cdr : #ArgsNil}}) → β`.
Arity is part of the domain, and a variadic builtin takes argument lists of
any length.

Subtyping is Boolean-algebraic subtyping as in MLstruct+: a Boolean algebra
over the atoms, the tag tree, and the merge rules

    (τ1 → τ2) ⊓ (π1 → π2) ≡ (τ1 ⊔ π1) → (τ2 ⊓ π2)
    {a : τ} ⊓ {a : π}      ≡ {a : τ ⊓ π}

The merge rule for arrows is what makes inference principal and free of
search, and it is why no builtin may have two arrows (§5).

**Departure D1: tagged functions.** In MLstruct+ a value's constructed type
is a function type or an object `T{a_i : τ_i}`; tags belong to objects only.
Here a function value carries a tag as well (`#Closure ⊓ (A → R)`). The
solver's final comparison (`BSolve.finish`) treats the left normal form as at
most one tag, at most one arrow and the fields, and relates it to the right
by: a tag under one of the right's tags; an arrow against an arrow
(contravariant domain, covariant result); a field against the same field.
An arrow is never related to a tag or a field, nor a tag to an arrow. §7.1
reduces this to MLstruct+ by an encoding: a tagged function is an object
whose `apply` field holds the function.

## 4. Terms and typing

The lowering (`BLower`) turns compile-time IR into these terms (`BE`):

    e ::= lit | prim | x | (e …)coll | λx̄.e | e(ē) | if e e e
        | if x is T e e | let x = e in e | set! x e | while e e | e.f | fail

Judgements are `Γ ⊢ e : τ` at a level, as in Simple-sub, with the bounds of
the variables as the context. The rules, as `BTyper.typeof` applies them:

- **Lit**: the constructed type of the literal.
- **Prim**: the builtin's declared type (§5), instantiated.
- **Var**: the variable's scheme, instantiated above its level. Locals are
  monomorphic; top-level definitions are generalised (MLstruct+ also has
  polymorphism only at the top level).
- **Lam**: fresh `ᾱ` for the parameters; `#Closure ⊓ (args(ᾱ) → τ)`.
  With a rest parameter, the domain ends in `args*(ε)` (any number of
  arguments of type `ε`) instead of `#ArgsNil`, and the rest parameter is
  `List(ε)`.
- **Macro**: as Lam with the tag `#Macro`, each parameter's variable below
  the type of forms, a rest parameter `List(ε)` with `ε` below the type of
  forms, and the body's type below the type of forms: a macro is a function
  from forms to forms, and the shapes it needs are inferred like a
  function's parameter types.
- **App**: `τf ≤ args(τ̄) → β`, `β` fresh.
- **If**: condition `≤ Bool`; result the union of the branches.
- **IfIs** (MLstruct's T-If): `x : (#T ⊓ τ1) ⊔ (τ2 ⊓ ¬#T ⊓ #Obj)` with `τ1`,
  `τ2` fresh; the branches see `x : τ1` and `x : τ2`.
- **Let**: monomorphic. A variable assigned anywhere gets one fresh `α`
  with the bound's type below it.
- **Set**: the value's type below the variable's type.
- **While**: condition `≤ Bool`; result `#ListNil`, what the loop answers.
- **Field**: `τ ≤ {f : β}`; `car` and `cdr` and their compositions lower to
  fields.
- **Group**: a recursive group's members are fresh variables while it is
  typed, then generalised.

**Tests.** A condition that tests what a value is lowers to an `IfIs`
wrapped around the condition itself:

    if (f x) a b   ⇒   let _ = (f x) in (if x is P_f(true) a b)

so the call is still typed (its argument must be in `f`'s domain) and the
branches are narrowed in addition. `(= (f x) l)` uses `P_f(l)`, and
`(= x l)` the tag of `l` when `l` has one of its own (symbols and bools).
`not` swaps the branches. `case` on literal symbols and bools is a chain of
such tests. A call of a user predicate does not narrow.

**Departure D2: narrowing through a builtin.** In MLstruct+ the scrutinee of
T-If is the value tested. Here it is the argument of a builtin whose answer
is tested. That is sound exactly when `P_f` is faithful (O2).

**Macros.** A macro call is typed as its expansion: the evaluator expands
the call from its argument syntax at check time and the expansion is lowered
in the scope of the call (O4).

**Calls** follow the evaluator's order (`ct-semantics.md` §5): a name bound
to a macro is typed as the macro's expansion, then a builtin of that name is
applied even when the name is also bound, then the binding is called.

**eval and apply.** `eval : ⊤ → Value`, where `Value` is the type of every
value (the forms, closures, builtins, macros, and lists and arrays of
values): the form is typed, the result is whatever its code computes, and
errors raised by that code are intended errors. Core's `eval-form` is
`eval` followed by `as-form`, which rebuilds a form and raises
`macro-error` on a function; it is ordinary Carp, checked like everything
else, with type `⊤ → Form`.
`(apply f xs)` follows `ct-semantics.md` §7 case by case, `xs` a sequence of
`ε`:

- `f` a builtin, qualified or unbound name: the call form
  `#ListCons ⊓ {car : #Symbol:f} ⊓ {cdr : List(ε)}`, `ε` below the type of
  forms;
- `f` a global closure: `f : args*(ε) → ρ`, answer `ρ`;
- `f` a global macro: a form;
- `f` a local or a global variable: `f : (args*(ε) → ρ) ⊔ σ` with `σ` a form,
  answer `ρ ⊔ (#ListCons ⊓ {car : σ} ⊓ {cdr : List(ε)})`, `ε` below the type
  of forms in both cases (conservative);
- any other `f`: evaluated, `f : args*(ε) → ρ`, answer `ρ`.

## 5. Builtin facts

Two tables carry everything the checker knows about builtins.

**Arrows** (`BBuiltin.type-of`). Each builtin has one type, possibly
polymorphic, of the form `#Builtin ⊓ (A → R)`. Faithfulness, for every
instance of its variables:

> **B1.** If `f` is applied to an argument list `v̄` whose type is below `A`,
> it raises no type error, and what it answers has a type below `R`.

One arrow, never an intersection of arrows: by the merge rule,
`(Int → Int) ⊓ (Double → Double)` is `(Int ⊔ Double) → ⊥`, which `+` does
not satisfy. Overloads are given up for this reason; `+` is
`∀ξ ≤ Number. (ξ, ξ) → ξ`, where mixed operands make `ξ` their union.

**Preimages** (`BBuiltin.preimage`):

> **B2.** For every value `v` that `f` accepts, `(f v)` answers `l` exactly
> when `v`'s type is below `P_f(l)`.

Accepted values matter: `length` accepts only sequences, so `P_length(0)` is
`Nil` even though `""` has length zero in other languages. The domain itself
is enforced by B1, because the tested call is typed (§4).

Both are checked against the evaluator by `corpus/check-bas-builtins.carp`:
B1 on 78 sample calls (result type below the declared result, and a call the
evaluator rejects rejected by the type too), B2 on 22 preimages over 30
sample values of every kind. Sampling is evidence, not proof (O3).

## 6. State

Globals that hold a value are mutable: each gets one variable `γ` at level
0, shared by every definition that reads or writes it. The cell's current
value is below `γ` from the start, and every checked `set!` adds the value's
type below it. Reads instantiate nothing (level 0 is never generalised) and
never narrow. `set!` of a function binding is rejected. A local assigned
anywhere is treated the same way within its scope.

Invariant: **the value in a cell has a type below `γ`**. It holds initially,
and each checked `set!` preserves it. It is broken by a `set!` the checker
did not see: one in a definition that failed to check, or one run by `eval`.
So the claim for a definition that reads a global holds when every
definition that writes that global also checks (O5).

A group that fails is rolled back (every bound it added is removed), so a
failure does not leak into the shared variables. Which of two conflicting
groups fails depends on the order they are checked in.

## 7. Soundness sketch

The structure is MLstruct+'s: progress and preservation (paper Lemmas 3.8
and 3.9) over a consistent bounds context, with subtyping soundness (paper
Theorem 4.1) to invert subtyping on values.

**Consistency.** MLstruct+ types under a consistent bounds context. The
solver keeps Simple-sub's invariant: when a bound is added to `α`, it is
constrained against each of `α`'s opposite bounds, so every lower bound of a
variable is below each of its upper bounds once solving succeeds. A failure
is an inconsistency, and the group is rejected and rolled back. The bounds
that outlive a group are the generalised ones (copied fresh at each use) and
the level-0 ones of mutable globals, which accumulate across groups, each
added consistently with what was already there.

**Progress** by cases on the redex:

- *application*: the function's type is below `args(τ̄) → β`. By subtyping
  soundness with D1, a value with that type is a closure or builtin (a tag
  alone, a cons cell, or a literal is not below an arrow). The argument
  list's type is below the domain, so the arity matches: tuples of
  different lengths are different cell chains, and `#ArgsNil` is disjoint
  from `#ArgsCons`. A builtin then raises no type error by B1.
- *field*: the value's type is below `{car : β}`; only cons cells have
  fields, so it is a cons.
- *if, while*: the condition's type is below `Bool = #True ⊔ #False`.
- *IfIs*: the scrutinee's type is below `#Obj` (the T-If shape implies it),
  and every value has a tag, so the test answers.
- *name*: an unbound name fails the check, so it does not occur in a
  checked definition.

**Preservation** by cases:

- *IfIs on a value*: as in the paper. By B2 and the evaluator's answer, the
  value is below `#T` in the first branch and below `¬#T` in the second, so
  it is below `τ1` or `τ2` respectively.
- *IfIs on a mutable variable*: does not occur; tests on assigned variables
  do not narrow, since an assignment between the test and a use could change
  the value.
- *builtin call*: by B1.
- *read of a global*: by the invariant of §6.
- *macro call*: the term that runs is the expansion that was typed (O4).
- the remaining cases follow Simple-sub and the paper.

### 7.1 Tagged functions (D1)

Encode our types in MLstruct+'s by a map `⟦·⟧` that is the identity on
`⊤`, `⊥`, variables, tags and the fields `car` and `cdr`, commutes with
`⊔`, `⊓` and `¬`, and puts each arrow in a field of its own:

    ⟦τ → π⟧ = {apply : ⟦τ⟧ → ⟦π⟧}

`apply` is a field name no other type uses. On values, a function with tag
`T` and code `f` becomes the object `T{apply = f}`, a cons cell stays an
object with `car` and `cdr`, and a call `v(ā)` becomes `v.apply(ā)`.

**Lemma 1 (rules translate).** For each subtyping rule our system uses, the
translated judgement is derivable in MLstruct+ (Fig. 4).

- the Boolean-algebraic rules, S-TagSub, S-TagBot, S-RcdDepth on `car` and
  `cdr`: `⟦·⟧` is a homomorphism for them, so they translate to themselves;
- arrow depth: `{apply : τ1 → τ2} ≤ {apply : τ0 → τ3}` by S-RcdDepth over
  S-FunDepth, from the same premises;
- arrow merge, negative side: `{apply : τ1 → τ2} ⊓ {apply : τ3 → τ4}` is
  below `{apply : (τ1 → τ2) ⊓ (τ3 → τ4)}` by S-RcdMrg⁻, which is below
  `{apply : (τ1 ⊔ τ3) → (τ2 ⊓ τ4)}` by S-RcdDepth over S-FunMrg⁻;
- arrow merge, positive side: each of `{apply : τ1 → τ2}` and
  `{apply : τ3 → τ4}` is below `{apply : (τ1 → τ2) ⊔ (τ3 → τ4)}` by
  S-RcdDepth, so their union is (S-AndOr2⁺), and that is below
  `{apply : (τ1 ⊓ τ3) → (τ2 ⊔ τ4)}` by S-RcdDepth over S-FunMrg⁺;
- assumptions: the encoding only adds a record layer above each arrow, and
  S-RcdDepth removes the later-modality guard just as S-FunDepth does, so a
  hypothesis that was guarded stays guarded.

**Lemma 2 (typing translates).** A lambda typed `#Closure ⊓ (A → R)`
becomes `Closure{apply = λ…}`, typed `#Closure ⊓ {apply : A → R}` by T-Obj
and T-Ext. A call typed by our App becomes `v.apply(ā)`, typed by T-Proj
and T-App. A builtin becomes `Builtin{apply = δ}` with `δ` a primitive whose
behaviour is B1; adding such primitives to MLstruct+ is the usual extension
by δ-rules.

**Corollary (D1).** Let a value's type be below `A → R`. Translated, an
object `T{…}` is below `{apply : ⟦A⟧ → ⟦R⟧}`, so by case (d) of the paper's
Theorem 4.1 it has a field `apply` whose type is below `⟦A⟧ → ⟦R⟧`, and by
case (b) that field holds a function accepting `⟦A⟧`. Cons cells and
literals have no `apply` field, so case (d) rules them out: they are never
typed as functions. That is the claim of §3.

**The solver.** What remains is that `BSolve.constrain` accepts only
derivable judgements. `annoying` is a port of MLstruct's normal-form
splitting: Boolean-algebraic rules plus Simple-sub's variable bounds. The final comparison,
`BSolve.finish`, is sound case by case:

- a left tag below one of the right's tags: S-TagSub, S-AndOr;
- arrow against arrow: arrow depth (Lemma 1);
- a left arrow with none on the right: drop it, since `L ⊓ (A → R) ≤ L`;
- a left tag matching none on the right: drop it and the right's tags,
  since proving `L′ ≤ R′` with `L ≤ L′` and `R′ ≤ R` proves `L ≤ R`;
- a field against the same field: S-RcdDepth;
- anything else fails.

Unions and intersections are built as sets (`BT.union`, `BT.inter`):
flattened, each part once, in the order of the parts' ids, and memoised by
their operands. The same set of parts is then always the same hash-consed
type, which is what lets the cache of pairs in progress recognise a
constraint it has met; without it, the "rest" a variable is bounded by grows
by repetition and solving need not terminate. In `annoying`, unknowns wait
until everything else is in the normal forms, and none is bounded when the
left's tag is already below one of the right's: that bound would be implied,
and adding it costs (6.1 s against 0.9 s on `eval-form` before memoising,
with the same outcomes on all of Core).

A recursive type is a variable defined as its body (`BT.define!`), as the
paper encodes recursive types by bounds. The solver unfolds such a variable
instead of bounding it, which is the paper's S-Hyp read from the other side:
the pair in progress is cached, so a guarded cycle closes on the cache, and a
defined variable never gains bounds from the definitions that use it.
Copying a type (extrusion, instantiation) copies a definition as a
definition.

The solver is incomplete with respect to the translation: MLstruct+ derives
`⊤ ≤ (A → R) ⊔ {car : τ}` from S-RcdTop, and `finish` rejects it.
Incompleteness only loses precision.

So O1 below is discharged on paper, by reduction to the paper's theorem,
assuming the implementation matches the cases above. The solver tests
(`test/bas.carp`) check those cases on examples; nothing is mechanised.

**Obligations.**

- **O1** Subtyping soundness with tagged functions (D1): reduced to
  MLstruct+ in §7.1; what remains is that the code implements the cases
  listed there.
- **O2** Narrowing through builtins (D2): sound given B2.
- **O3** B1 and B2 hold for every builtin and preimage. Checked by sampling
  against the evaluator, which has found wrong types for `cons`,
  `cons-last`, `String.head`, `String.to-list`, `String.to-array`, `line`,
  `column` and `file` (arity), twelve builtins typed as taking anything that
  need forms, and `list`; a missing sample hides a wrong type.
- **O4** A macro's expansion at check time is the expansion that runs. True
  when the macro's expansion depends only on its argument syntax and on
  state that does not change between the check and the run. A macro that
  reads a counter, a setting changed later, or a global set at run time can
  expand differently.
- **O5** Every writer of a global a definition reads also checks.

## 8. Known gaps

- **Dynamic maps used as records.** A dynamic map is ordinary Core code over
  lists, so `(Map.get m "key")` has the type its code gives it: the union of
  every value in the map, whatever the key. Code that keeps different kinds
  of values under literal keys (`expand`'s syntax objects) fails where it
  reads one back. This is a precision limit, not a gap to close by giving
  the map functions declared types: they are library code, not builtins.
- **Invariants held by user predicates.** `Dynamic.Map.get-with-default`
  takes `cadr` of what `List.find` answers, which is safe only because
  `Map.contains?` was asked first. Most failures in the carpentry-org
  libraries cascade from it.
- **`eval` answers any value.** A macro whose expansion is the value of an
  `eval` (`unreachable` in Core, `log`'s macros, `orm`'s transaction macros)
  fails the requirement that an expansion be a form: the code `eval` runs
  could compute a function, and a function is not a form. The sound way to
  expand to what code evaluates to is `eval-form`, which checks that it got a
  form when it runs.
- Definitions that fail to check (27 of 195 in Core) are not covered, and
  through O5 they weaken the claim for definitions that read globals they
  write.
- `set!` of a function binding is rejected rather than typed.
- A closure stored in data (a list, a global) has the type `#Closure`
  without an arrow, so calling it is rejected; typing it from its code would
  fix this (`derive` fails on it).

Precision losses that are not soundness gaps: no overloads; narrowing only
on literal answers (`(= (length x) 1)` does not narrow); `cons` widens its
tail to a list of the elements, so `cxr`-style length arithmetic is lost.
