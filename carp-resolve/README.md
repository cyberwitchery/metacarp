# carp-resolve

`carp-resolve` lowers expanded `SurfaceModule` syntax into `carp-ir`. It
collects top-level declarations first, assigns stable IDs (globals positive and
sequential, locals lexical), resolves references, and rejects unknown names
with a `SurfaceSpan`. Unsupported syntax is a phase-tagged error rather than
something passed on to later phases.

## Resolved surface

Literals: `Int`, `Long`, `Float`, `Double`, `Byte`, `Char`, `String`,
`Pattern`, `Bool`, and array / static-array literals.

Expressions and control flow: symbol references (local, global, imported),
calls, `do`, `if`, `set!`, `while`/`while-do`, `break`, `when`/`when-do`,
`unless`/`unless-do`, `cond`, `for`, `and`, `or`, `case`, `fmt`/`str*`,
multi-binding `let`/`let-do`, `fn`, `match`/`match-ref`, and `(the TYPE EXPR)`.
The higher-level forms are desugared here into core `if`/`let`/`while`/`set!`.

Top-level declarations: `defn`/`defn-`, `def`/`def-`, `defmodule` (nested and
scoped), `with`, spliced top-level `do`, `sig`, `definterface`, `register`,
`deftemplate`, `register-type`, `implements`, `use`/`use-all`,
`system-include`, and `deftype` (generating constructors and field accessors).
Directives without runtime meaning here (`doc`, `private`, `hidden`,
`defmacro`, `defndynamic`, `load`, …) are accepted and ignored.

Type syntax: scalar and `Unit` types, type variables, `Named` types with
arguments, `Ref`/`ref` reference types with lifetimes, and `Fn` function types.

```bash
carp -x test/carp-resolve.carp
```
