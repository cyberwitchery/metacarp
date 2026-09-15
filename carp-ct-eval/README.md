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

## How a form runs

Syntax is compiled before it runs, in two stages. A body that runs more than
once is compiled once: a macro body when the macro is defined, a `fn` body
where the lambda is written. `CtEval.eval-node` compiles and runs a form that
exists only at run time — a macro expansion, the argument of `eval`, a
top-level compile-time call.

`CtLower.lower` produces `CtIR`. It settles, per form, which special form a
list is, whether its head names a builtin, and whether a symbol is bound by an
enclosing `fn` or `let`. A form with its own rule about which arguments are
evaluated carries that rule as `CtIR.Special`; a malformed form becomes
`CtIR.Fail` holding the diagnostic it raises when reached, because the
reference reports these where a form runs rather than where it is read.

`CtCompile.compile` produces `CtCode`: one instruction array plus the tables
its operands index — constants, symbols, names, spans, call sites, nodes.
`if`, `when`, `and`, `or`, `cond`, `case`, `while` and `let` are jumps and
frame instructions inside that array. `for` is lowered as `let` and `while`,
and a dictionary literal as the `Map.from-array` call it denotes.

`CtEval.run-code` runs one `CtCode`: a program counter, a value stack, and a
stack of the frames `let` opens. One instruction re-enters the loop — a call,
which runs a body that is not this one.

## Names

A parameter or `let` binding is found among the handful of bindings in its own
frame. Every other name carries an inline cache: what a free name resolves to
depends on the frame its body was defined in, which is fixed per body, and on
the environment's binding epoch. A cache keyed by that pair is sound only
while two things hold, and both are load-bearing:

- lowering classifies every name an enclosing `fn` or `let` binds, so a free
  name can never be shadowed by a local;
- `CtEnv.define-local!` does not advance the binding epoch, while `define!`
  and `add-import!` do.

`CARP_DEBUG_CT` reports cache hits and misses after expansion.

## Rules for changing this

- **Call arguments move off the value stack; they are never copied off it.**
  A compile-time value owns a syntax tree, so copying each argument of each
  call costs a tree per argument.
- **The builtin table in `CtLower.builtin-id` and the integer arms of
  `CtEval.apply-builtin` are one table written twice.** Adding a builtin means
  adding it in both.
- **`CtSpecial`'s opcodes and `CtEval.run-special`'s arms are likewise one
  table written twice.**
- **`apply`, `expand`, `eval` and `Dynamic.compose` strip comments before
  counting arity; the other special forms do not.** The asymmetry is the
  reference's.

This evaluator is explicitly unhygienic: it returns the names that the macro
body constructs. Hygiene is not part of this checkpoint. It deliberately does
not implement compiler-driver effects, module/import resolution, maps, or
general runtime evaluation. Module frames and top-level phase classification
belong to `carp-expand`.
