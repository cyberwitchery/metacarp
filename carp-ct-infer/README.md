# carp-ct-infer

> **Experimental, and opt-in.** Nothing in the compiler calls this. It is a
> sixteenth phase that a caller invokes deliberately, kept unwired while its
> coverage is still partial. See [Status](#status) for what it does not do
> yet.

`carp-ct-infer` checks the bodies of `defmacro` and `defndynamic` definitions
against the tag lattice in [`carp-ct-types`](../carp-ct-types/README.md). It
reports only provable impossibilities: an operation is rejected when the
intersection of what it requires and what it may receive is `⊥`.

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

**Shapes.** Literals and quoted forms have the shape the reader gave them.
`(quote (a b))` is a `List` whatever `a` and `b` are, and that is where most of
the pass's precision comes from. Quasiquotation is tracked by depth: inside a
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

Argument shapes only, never field types or function domains: those need the
component homomorphisms, which are not implemented. Nothing about whether the
syntax a macro produces will resolve or type check — this is a claim about the
macro as a program, not about its expansion. Nothing about effects, `set!`
through shared cells, or symbol identity, which is dynamic because expansion is
unhygienic.

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

## Running it over a standard library

```bash
CARP_CORE=$CARP_DIR/core carp -x corpus/run.carp
```

The corpus is the Core.carp load order, so the set checked is the set the
compiler would load. The runner reports rejections and also its own coverage,
because a pass that reports nothing because it examined nothing is otherwise
indistinguishable from a clean result.

Against the pinned reference Core (`8e190f2c`): 289 compile-time definitions,
2167 argument positions walked, 950 of them constrained, 388 with a shape
precise enough for a contradiction to be possible, spread over 129 of the 289
definitions, and 31 narrowings applied. **0 definitions rejected.** The same
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
- **Validation gaps.** The oracle covers 39 of the roughly 91 names the
  evaluator answers to. Dictionary, Macro and Collection cannot be
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
