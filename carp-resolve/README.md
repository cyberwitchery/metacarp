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
calls, `do`, `if`, `set!`, `while`, `break`, multi-binding `let`, `fn`,
`match`/`match-ref`, and `(the TYPE EXPR)`.

That is the whole list. `when`, `unless`, `cond`, `for`, `and`, `or`, `case`,
`fmt`/`str*` and the `-do` variants are Core macros: they are gone by the time
resolution runs, and this phase never sees them. There is no sugar table
here.

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
