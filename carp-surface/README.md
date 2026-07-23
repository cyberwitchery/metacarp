# carp-surface

`carp-surface` is the lossless syntax boundary for tools built around Carp.
It converts the concrete, source-located forms returned by
[`carp-reader`](https://github.com/carpentry-org/carp-reader) into a small,
standalone AST with a uniform `SurfaceNode` shape:

```clojure
(load "git@github.com:carpentry-org/carp-surface@0.1.0")

(match (Surface.parse "; a note\n(defn id [x] x)")
  (Result.Success module) module
  (Result.Error error)    (panic (Parser.format-error &error)))
```

Each `SurfaceNode` has a `SurfaceSpan`; comments, container kinds, number widths, and the
reader's normalized reader-macro forms are retained. The library has no file,
subprocess, code-generation, name-resolution, or type-checking API.

`Surface.render` renders a node back to source-level Carp without its span or
implementation boxes. It is also installed as `str` for `SurfaceNode`, so an
expanded form can be inspected directly with `(str &node)`.

## Why this is separate from the compiler

The reader is reusable by formatters and linters. The compiler needs a tree it
can own without coupling later phases to parser implementation details. This
package is that boundary: the formatter, linter, language server, and compiler
can all use it, while each can make its own semantic decisions.

`Surface.parse` returns the reader's `ParseErr` unchanged. Semantic errors are
not invented here; a later validation library will define compiler diagnostics.

## Intended compiler package graph

```
parsec + strbuf
       │
  carp-reader
       │
  carp-surface ── carp-module ── carp-expand ── carp-resolve ── carp-infer ── carp-specialize ── carp-c
       │                 │               │               │
  formatter/linter   source graph  carp-ct-eval   carp-names      carp-types
                                                               │
                                                        carp-compiler (CLI/driver)
```

The bottom row contains reusable libraries. `carp-compiler` will only load
files, select options, compose phases, write generated C, and invoke a C
compiler. It must not become the home for ASTs, type algorithms, or C lowering.

The existing `ast` package remains useful for macro-time source rewriting, but
does not replace this package: it uses dynamic maps and quoted values rather
than a source-located, statically shaped AST.

## Macro expansion

`carp-module` runs after reading and before expansion. It resolves a supplied
source graph and flattens top-level load directives into deterministic source
order without performing filesystem, package-cache, or network work.

`carp-expand` runs after loading and before ordinary runtime name resolution
and type inference.
It processes top-level forms in source order: a `defmacro` registers a
compile-time binding; a later macro call receives syntax objects,
`carp-ct-eval` evaluates its body to syntax, and that result is expanded
recursively. The resulting module no longer contains macro definitions or
macro calls.

`carp-ct-eval` is an interpreter/VM for the compile-time subset of Carp. It is
separate from the generated program and from `carp-c`: no target C executable
is compiled or run merely to expand a macro. Macro output is deliberately
unhygienic, matching Carp's default: generated identifiers can capture, and be
captured by, surrounding names. Runtime resolution then operates only on fully
expanded forms; it can share basic name types with the expander, but not the
expander's environment.

## Development

```bash
carp -x test/carp-surface.carp
```
