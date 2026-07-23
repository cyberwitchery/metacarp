# carp-expand

`carp-expand` is the macro-expansion phase between `carp-surface` and runtime
name resolution. It processes forms in source order: `(defmacro ...)` adds a
compile-time binding, while calls to that binding are evaluated by
`carp-ct-eval`, then recursively expanded. Macro definitions are omitted from
the resulting `SurfaceModule`.

The current vertical slice supports fixed-arity and rest-parameter,
unhygienic macros, plus top-level and module-scoped `(defndynamic ...)` and
`(defdynamic ...)` compile-time bindings. Dynamic definitions are evaluated in
source order and are omitted from the resulting `SurfaceModule`, just like
macro definitions. Reopened modules share one compile-time frame, and
`(use Module)` imports that frame without copying its values.

Prelude modules are driver policy:

```clojure
(let [config (ExpandConfig.init [@"Dynamic"])]
  (MacroExpand.expand-module-with &module &config))
```

`MacroExpand.expand-module` uses an empty prelude configuration. Quasiquote,
`gensym`, and the dynamic list helpers are ordinary Core code, so a module
that uses backtick macros must include `Quasiquote.carp` (and its `Dynamic`/
`List` helpers) among its sources — the driver's implicit Core load does this;
standalone callers load them explicitly (see `test/execute.carp`).

The loader's load-stack markers (`Unsafe.load-stack-push!`/`-pop!`) are
consumed here: they maintain the compile-time `current-file` stack and vanish
from the expanded stream.

```clojure
(defmacro when [condition body]
  `(if %condition %body ()))
```

Macro bodies may return a parameter directly, use `(quote ...)`, or use
`(quasiquote ...)` with unquote and unquote-splicing. They may also use
Boolean `if`, sequential multi-binding `let`, `do`, lexical `fn` closures,
and syntax-list operations supplied by `carp-ct-eval`. Variadic macros use
Carp's familiar `[fixed :rest rest]` parameter form.

Quoted forms remain opaque to the expander. Macro output is deliberately
unhygienic, matching Carp's default semantics: generated identifiers are
resolved exactly as written.

## Core bootstrap gate

`test/core.carp` supplies the real `Core.carp` source registry to
`carp-module`, expands its complete transitive graph, and then expands the
source form supplied as its first program argument. The driver supplies the
three host bindings that Core expects before loading: `host-arch`, `host-os`,
and `Project.get-config`.

Core bootstrap preserves runtime declarations such as `defn`, `def`,
`implements`, and `register` while registering compile-time definitions. This
avoids requiring the compile-time evaluator to execute the entire runtime
standard library merely to make Core macros available. A later declaration
lowering phase can expand the preserved runtime bodies once its compiler
callbacks are available.

Top-level compile-time function calls are resolved through the same frame
store, evaluated for effect, and omitted from emitted runtime syntax.

## Verification

The regular `Test` suite is checked with:

```bash
carp -b --generate-only test/carp-expand.carp
```

`test/execute.carp` is a no-framework executable integration check for nested
expansion, quotation, multi-binding `let`, rest parameters and splicing,
returned closures, computed collections, dynamic helpers, Core bootstrap
macros, and arity diagnostics. It is useful when the host compiler's
`Test`/color code generation is unavailable:

```bash
carp -b --generate-only test/execute.carp
```

The complete Core registry gate is:

```bash
carp -b test/core.carp
out/Untitled '(Debug.memory-logged (println "ok"))'
```

For a quick no-argument smoke check, `carp -x test/core.carp` expands the
default probe `(println "ok")`.

It prints the expanded final form using `SurfaceNode.str`; spans and internal
AST wrappers are omitted. Compile-time closures retain stable frame IDs and
bindings live in shared cells, avoiding whole-environment copies at each
definition and call.
