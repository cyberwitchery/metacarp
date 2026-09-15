# carp-surface

Source-located syntax shared by the compiler and Carp tooling. The package
converts [`carp-reader`](https://github.com/carpentry-org/carp-reader) forms
into an owned, statically shaped tree. It has no filesystem, package-loading,
code-generation, name-resolution, or type-checking API.

Load `carp-surface/carp-surface.carp` from the repository root. Each
`SurfaceNode` pairs a `SurfaceSpan` with a `SurfaceForm`. Forms retain comments,
container kinds, numeric widths, and the reader's normalized reader macros.
Rendering produces source-level syntax, not a byte-identical copy of the
original spelling and whitespace.

## Parse and render

| Operation in `Surface` | Result |
| --- | --- |
| `parse` | Parse a source string to `Result SurfaceModule ParseErr`; spans have no source ID. |
| `parse-in` | Parse with a source ID attached to spans. |
| `parse-input` | Parse a `SourceInput` to `Result SourcedSurfaceModule ParseErr`, retaining the exact input. |
| `parse-input-diagnosed` | Same input, returning a structured `Diagnostic` on failure. |
| `render` | Render one node to a string. |
| `render-module` | Render a module as newline-separated forms. |

`SurfaceNode.str` and `SurfaceModule.str` use those renderers. The diagnosed
parser reports a zero-width byte span at the reader's error position.
`SurfaceSpan.in-source` converts a reader span to a caller-visible `SourceSpan`.
See [carp-source](../carp-source/README.md) for the byte-range contract.

## Compiler boundary

The module loader parses supplied sources and orders their forms before macro
expansion. Expansion consumes this surface model; runtime resolution creates
the separate core IR afterward. The surface model therefore remains useful
for inspecting macros and building source tools without coupling them to
inferred or specialized runtime representations.

See [carp-module](../carp-module/README.md),
[carp-expand](../carp-expand/README.md), and the
[architecture guide](../docs/architecture.md) for the current package graph.

## Verification

Run from this package directory:

```sh
carp -x test/carp-surface.carp
```
