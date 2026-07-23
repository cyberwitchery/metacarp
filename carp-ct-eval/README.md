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

This evaluator is explicitly unhygienic: it returns the names that the macro
body constructs. Hygiene is not part of this checkpoint. It deliberately does
not implement compiler-driver effects, module/import resolution, maps, or
general runtime evaluation. Module frames and top-level phase classification
belong to `carp-expand`.
