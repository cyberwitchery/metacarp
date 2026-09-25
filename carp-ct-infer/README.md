# carp-ct-infer

> **Experimental, and opt-in.** Nothing in the compiler calls this. It is a
> sixteenth phase that a caller invokes deliberately, kept unwired while its
> coverage is still partial. See [Status](#status) for what it does not do
> yet.

`carp-ct-infer` checks the bodies of `defmacro` and `defndynamic` definitions
against a type algebra, and reports only provable impossibilities: an operation
is rejected when the intersection of what it requires and what it may receive is
`⊥`.

Two algebras implement the same interface. [`carp-ct-types`](../carp-ct-types/README.md)
is the tag lattice — the shape homomorphism alone, a shape is a bitmask.
[`carp-ct-sub`](../carp-ct-sub/README.md) is the set-theoretic one, with products
and arrows, and it is what this pass loads. The difference is one `load` line,
which is what lets the two be compared: everything a tag can say comes out
identical, and what a tag cannot say — what a function takes, what a container
holds — the lattice answers "nothing known" to.

It is a *checking* phase, like the borrow check rather than like inference. It
produces no type and changes no representation, so a caller that ignores it
loses only the diagnostics. That is what makes it safe to leave unwired.

## The phase

```clojure
(match (CtCheck.modules &parsed-surface-modules)
  (Result.Success _)      ;; nothing to say
  (Result.Error findings) (IO.println &(CtCheck.render-all &findings)))
```

`CtCheck.modules` registers every definition across the set before checking
any of them, so a call from one file into another resolves; `CtCheck.module`
checks one module alone. Both answer in the shape the other phase libraries
use — a `Result` whose error carries a message and the `SurfaceSpan` it
belongs to:

```
ct-shape:cell:one:1: f: car argument 0 is Symbol, which can never be Seq ⊔ Collection
```

Give the parse an identity with `Surface.parse-in` and the span names the file.
`CtCheck.name` returns the phase name for a driver that tags diagnostics by
phase.

## What it knows

**Shapes.** Literals and quoted forms have the shape the reader gave them, and
so does everything inside them: `(quote (a b))` is a list of two symbols, and
`(list x 2)` is a two-element list holding whatever `x` is and an Int. That is
where most of the pass's precision comes from.

**Functions.** A lambda is a function from the shapes its body forces on its
parameters to the shape its body answers with, so `(let [head (fn [xs] (car xs))]
(head 3))` is a contradiction across the binding. The domains are read off the
spine, the same rule a definition's summary uses.

**Elements.** A domain can constrain what a container holds, not only that it is
one: `Symbol.concat` wants a sequence of symbols, and `(Symbol.concat (list
(quote a) 2))` is rejected for the `2`. On the tag-lattice backend both of these
say nothing at all. Quasiquotation is tracked by depth: inside a
quasiquote a form is data, and `unquote` and `unquote-splicing` return to code.

**Narrowing.** `T-If`: the matched branch of a conditional intersects the
subject with the predicate's tag, the default branch intersects it with the
complement. `list?`, `array?`, `string?` and `number?` narrow; `not` flips the
polarity; `and` narrows on the true branch and `or` on the false one, because
neither can say which operand decided the other. `cond` narrows each clause
against the failure of every clause before it.

**Bottom.** `macro-error` has shape `⊥`, so a branch that raises contradicts
nothing. This is Lemma 4.12 case (a) doing real work: without it, every
correctly guarded `(if bad (macro-error …) (car x))` would be rejected.

**Resolution.** A builtin is a name the evaluator answers to, which means `car`
and `Dynamic.car` and nothing else, so a qualified `Map.length` is not
`length`. A bare name that *is* a builtin stays one no matter what the program
defines: `carp-ct-eval` tries `apply-builtin` on a call's head before it looks
the head up in the environment, so inside `(defmodule Map …)` a bare
`(length m)` is the builtin. That is the evaluator's rule, read off its
dispatch order rather than guessed.

## What it does not know

Nothing about whether the syntax a macro produces will *resolve* or type check.
What it says about output is narrower and is the only part that cannot drift from
the expander: a form that starts with a known special form, whose length is fixed
— a splice makes it unknown and nothing is claimed — and which is shorter than
that form can ever be. Everything past the minimum is `carp-expand`'s business.

Nothing about effects, `set!` through shared cells, or symbol identity, which is
dynamic because expansion is unhygienic. Nothing about polymorphism: a dynamic
function is summarised monomorphically, so a generic helper is summarised at the
join of its uses.

The builtin table is the pass's entire soundness surface. Every name it does
not mention is unconstrained, which is deliberate: a checker that guesses at
the parts of the dynamic language it does not model invents findings about
correct code.

## Checking the table against the evaluator

```bash
carp -x corpus/oracle.carp
```

The domains above were first written by reading `carp-ct-eval`. That is the
wrong direction of evidence: running the checker over correct code exposes a
domain that is too strict, never one that is too permissive, and a domain that
is too permissive is exactly what lets a checker miss bugs while reporting a
clean result.

So the oracle runs the evaluator instead. For 39 builtins it evaluates a
baseline call, then substitutes each of 16 constructible shapes into each
argument position in turn, and compares what the evaluator accepted against
what the table declares — in both directions, plus the result shape.

It currently reports **0 too permissive, 0 too strict, 0 wrong result
shapes**, with 11 documented divergences. Writing it found that compile-time
arithmetic is Int arithmetic rather than numeric, that no String operation
accepts a Symbol, that `not` had never had its domain applied at all, and that
a builtin beats a same-named definition. Every one of those is a hole the
corpus run could not have shown.

The 11 divergences are one evaluator quirk: `collection-values` returns a
one-element collection for a `CharLit`, while the Symbol, Int, String and Bool
cases beside it all raise. So `(car \a)` answers `\a` and `(length \a)`
answers 1. The table refuses it on purpose, which is recorded in the oracle
with the reason.

Two constraints are deliberately outside the oracle's reach. `Symbol.concat`,
`caadr` and `cdadr` restrict the *elements* of their argument rather than its
tag, and an element constraint needs the component homomorphisms this library
does not implement.

## Mutation testing

```bash
CARP_CORE=$CARP_DIR/core carp -x corpus/mutate.carp
```

Seven operators inject one shape error at a time into every `defmacro` and
`defndynamic` body in the corpus: a sequence operation's subject becomes a
String or a Symbol, an arithmetic operand becomes a String, a String
operation's subject becomes a List, an index becomes a String, `not` receives
an Int, and the branches of an `(if (list? v) …)` are swapped so that the
guarded branch lands where the guard does not hold.

Mutations edit the parsed tree and render it back, so a site is always a real
argument position rather than a coincidence of spelling, and quotations are
skipped because syntax a macro emits is not code it runs. Rendering without
mutating must leave the file clean, or a finding on a mutant would only be an
artifact of re-rendering.

Currently **874 sites, 874 caught, 0 missed, 0 dirty controls.**

## The case corpus

```bash
carp -x corpus/cases.carp
```

The corpora above each answer a narrower question than the one that matters. The
oracle checks the table against the evaluator. Mutation testing seeds errors and
counts how many come back, but its operators write the errors they already know
how to write, so it measures sensitivity to the failures it was designed around.
The Core sweep shows that correct code stays clean, which is the absence of false
positives and nothing more. None of them contains a mistake somebody would
actually make, and there is a reason for that: a shape error in a macro body
fails the first time the macro is used, so it rarely survives to a commit.

So this corpus is written by hand, one defect or one correct idiom per file, each
file stating the verdict it expects in its header:

| verdict | meaning |
| --- | --- |
| `reject` | a finding is the right answer; its absence is a miss |
| `accept` | a finding would be a false positive |
| `gap` | a complete checker would reject this, and this one cannot see it yet |

A case is checked on its own, so the only names the pass knows in it are the
builtins and the definitions the file itself makes — Core's dynamic library is
not loaded, and a case that wants `caar` writes it out. Spelling the chain out is
what makes an interprocedural case legible anyway.

Currently **21 cases: 21 matched, 0 false positives, 0 missed rejections, 0 gaps
open.** Twelve must be rejected (a String operation on a symbol, arithmetic on a
string, `not` on a number, `car` of a quoted symbol, a domain crossing one call,
a result crossing one call, a domain that only appears after a round of the
fixpoint, a wrong arity, an uncallable head, a lambda handed what it cannot take,
an element that breaks a container's element constraint, a macro emitting a form
too short to be well formed) and nine must be accepted (a use
guarded by a branch, a local shadowing a parameter, a bare name inside a module
meaning the global definition, a builtin beating a same-named definition, a macro
receiving syntax, a quasiquoted body, a guarded `macro-error`, a rest parameter, a macro emitting a form
written around a splice).

The corpus discriminates, which is the point of it: with summaries switched off,
the three interprocedural cases go from caught to **missed**, and the other
fourteen are unchanged. No other corpus here can show that — a mutation operator
cannot write an error that lives in the gap between two definitions.

The `module-bare-name` case is in it because the pass got that wrong: it read a
bare name inside a module as that module's own definition, and rejected correct
code in `carpentry-org/match-utils` for it.

### The gaps

All three original gaps have closed, each one when the algebra underneath grew
the dimension its case named, and the runner said so on the run that closed it:

- `closure-domain` — a lambda that forces a sequence and is handed an Int. Closed
  by **arrows**: a lambda now has a domain and a codomain instead of being an
  opaque leaf.
- `element-constraint` — `Symbol.concat` constrains the *elements* of its
  argument. Closed by **products**: a container carries what it holds, and the
  builtin table can say so.
- `macro-output-shape` — a macro emitting an `if` with a test and nothing else.
  Closed by **singleton types and chains**: a quoted symbol is now that symbol
  rather than merely a symbol, so an emitted form has a recognisable head, and a
  container written around a splice keeps the prefix it was written with.

The last of those is a claim about produced syntax, which is the one that could
overreach, so it makes the narrowest claim available and `spliced-output` guards
it: a form written around a splice has no known length and nothing is said about
it. The minimum arities are the part of a form's grammar that cannot drift —
a form with too few children is malformed in any version of the expander —
and `carp-expand` stays the one place that knows the rest.

A gap closing is the corpus doing its job rather than the end of it. The next
ones to write are the constraints the algebra can now hold but the builtin table
does not yet state: `caadr` wants its second element to be a sequence, and
`String.append` wants two strings rather than any two values.

## Running it over a standard library

```bash
CARP_CORE=$CARP_DIR/core carp -x corpus/run.carp
```

The corpus is the Core.carp load order, so the set checked is the set the
compiler would load. The runner reports rejections and also its own coverage,
because a pass that reports nothing because it examined nothing is otherwise
indistinguishable from a clean result.

Against the pinned reference Core (`8e190f2c`): 289 compile-time definitions,
2167 argument positions walked, 1002 of them constrained, **466** with a shape
precise enough for a contradiction to be possible, spread over 170 of the 289
definitions, and 31 narrowings applied. **0 definitions rejected.** The same
sweep over every `.carp` in `carpentry-org` — 516 files, 557 compile-time
definitions the pass had never seen — also rejects nothing, with 1158 of 2592
constrained positions decided. The same
holds with macro parameters tightened from `Obj` to `Syntax`, which decides 17
more positions and still rejects nothing.

The coverage line matters as much as the rejection count. Before the oracle
corrected the table the same clean result came from 607 constrained positions
and 176 decided ones, across 79 definitions — so most of Core was being
approved by a pass that had nothing to say about it.

## Status

Done and validated for what it claims; roughly a third of the way to what the
paper describes. What is missing, in the order it matters:

- **Four of the five characteristic homomorphism families.** Only `H` exists.
  Without `I`, `J`, `D` and `C` there is no reasoning about a field's type, a
  function's domain, or its codomain: every closure is opaque, and element
  constraints like `Symbol.concat`'s are inexpressible. The paper's
  completeness result does not apply to one family alone.
- **No interprocedural inference.** Every `defndynamic` and `defmacro` returns
  `⊤`. There are no schemes and no fixpoint over the definition graph, which
  is most of why 160 of Core's 289 definitions have nothing decidable in them.
- **Walker gaps.** `case` returns `⊤` and does not narrow; `when`, `unless`
  and `while` return `⊤`; `apply`, `eval`, `expand`, `parse`, `s-expr`,
  `members` and `hash` are unconstrained; `use` imports are not followed, so
  module-relative resolution is approximate; `defdynamic` values are
  registered but their shapes are not tracked; lambda parameters are always
  `⊤`.
- **Not integrated.** No `carp-expand` or `carp-session` hook, not in
  `scripts/run-assurance.sh`, and no performance measurement.
- **Validation gaps.** No corpus yet contains a defect taken from real history;
  the hand-written cases are ours, not anybody's mistake. The oracle covers 39 of
  the roughly 91 names the evaluator answers to. Dictionary, Macro and Collection cannot be
  constructed by the probe set. The short-circuit domains and the narrowing
  predicates are not oracle-checked.

## Tests

```bash
carp -x test/carp-ct-infer.carp
```

53 assertions: the phase API and its rendered diagnostics, the lattice laws,
the broken macros that must be rejected, and
the correct ones that must not be. Every defect found while building this is a
regression test in it: `String.concat` typed as though it took two strings,
comments treated as ordinary positional children, `not` never having its
domain applied, arithmetic admitting non-Int numbers, String operations
admitting Symbols, a definition wrongly shadowing a builtin, and `and`/`or`
typed as answering with a Bool when they answer with an operand.
