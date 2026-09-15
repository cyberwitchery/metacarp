# carp-ct-eval

`carp-ct-eval` evaluates syntax during compilation. It has no dependency on a
C backend or on generated-program values.

The evaluator supports bound macro parameters, literals, `(quote form)`,
`(quasiquote form)` with unquote and unquote-splicing, Boolean `(if ...)`,
`when`, `and`, `case`, `cond`, sequential multi-binding `let`, and `do`. It
also supports persistent compile-time `set!`. Lexical `fn` closures retain a
stable defining-frame ID; calls allocate child frames and mutations update
shared cells through `carp-ct-env`. No closure copies its environment.

The evaluator supports closures, first-class builtin functions, array
collections, and evaluated callee expressions. It provides the syntax-data and
dynamic operations Core bootstrap macros use: list construction and accessors
(`list`, `cons`, `car`, `cdr`, `cadr`, `cddr`, `last`, `cons-last`, `length`,
`empty?`, `list?`, `array?`), `array` and `append`, comparisons, Boolean
operations, small integer arithmetic, string operations (`String.length`,
`String.slice`, `String.append`, `String.prefix`/`suffix`, `String.head`/`tail`,
…), `str`, `macro-error`, and `Symbol.from`/`Symbol.concat`/`Symbol.prefix`.
Collections convert to array syntax where an evaluated macro expression requires
syntax.

## Lowering and bytecode

Syntax is compiled before it runs, in two stages, and a body that runs more
than once is compiled once: a macro body when the macro is defined, a `fn`
body when the lambda is written. There is no second evaluator — no tree
walker beside the compiler — so the language has one description, in one
place.

`CtLower.lower` produces `CtIR`. It decides three things a tree walker would
decide again on every visit: which special form a list is, whether its head
names a builtin, and whether a symbol is bound by an enclosing `fn` or `let`.
A form with its own rule about which arguments are evaluated says so with
`CtIR.Special`, and a malformed one carries the diagnostic it will raise when
it runs, because the reference reports those where the form runs rather than
where it is read.

`CtCompile.compile` turns that into `CtCode` — one instruction array plus the
tables its operands index. `if`, `when`, `and`, `or`, `cond`, `case`, `while`
and `let` become jumps and frame instructions within that array, so none of
them costs an interpreter call; `for` desugars to `let` and `while`, and a
dictionary literal to the `Map.from-array` call it means. `CtEval.run-code` is
a loop over a program counter with a value stack and a stack of the frames
`let` opens. One instruction leaves the loop and comes back, and the
reference's VM recurses at the same place: a call, which enters a body that is
not this one.

Call arguments MOVE off the value stack rather than being copied off it. A
compile-time value owns a syntax tree, so copying every argument of every call
is the one thing a stack machine here must not do; doing it cost 6% before it
was noticed.

Names are classified where they are written. A parameter or `let` binding is
found among the handful of bindings in its own frame. Every other name carries
an inline cache index: what a free name resolves to depends on the frame the
body was DEFINED in, which is fixed per body, and on the environment's binding
epoch, so a cache keyed by that pair is sound and hits on every call after the
first. `CARP_DEBUG_CT` prints the cache counters after expansion.

## What the measurements said

Against the tree walker this replaced, on this box: a Core-only compile went
from 2.01s to 0.66s and `test/map.carp` from 4.75s to 3.15s, with peak RSS on
the latter down from 183MB to 152MB (2026-09-15). Most of that is the first
stage — deciding once what a form means, making a closure a prototype index
instead of a copied syntax tree, and caching free-name resolution — plus
`carp-ct-env` indexing the frames that hold hundreds of bindings, which was
the single largest item and the one a profile had to find.

The flat instruction array itself is worth about 3% of a Core-only compile
over running `CtIR` as a tree, and 1-2% of `test/map.carp`.

Two things were tried and dropped because they measured flat. Positional
slots for locals: a local frame holds two or three bindings, so there was
nothing in the scan to remove. And lowering `for` for speed: compile-time code
rarely runs one — it is lowered anyway, because leaving one control form out
of the compiler was arbitrary.

This evaluator is explicitly unhygienic: it returns the names that the macro
body constructs. Hygiene is not part of this checkpoint. It deliberately does
not implement compiler-driver effects, module/import resolution, maps, or
general runtime evaluation. Module frames and top-level phase classification
belong to `carp-expand`.
