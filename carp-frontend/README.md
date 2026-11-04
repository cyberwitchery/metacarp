# carp-frontend

`CompilerFrontend.infer-module-with` expands, resolves, validates, derives,
and infers a loaded surface module. It returns `AnnotatedModule`, pairing the
derived Core IR with its inference result. It loads no backend or C renderer.
`CarpCompiler` keeps the existing facade and shares this path across batch,
library, and ownership-tooling entry points.

Warm sessions use the same derivation entry points with caller-owned identity
allocation and provenance. Derivation keeps its identity policy and generated
string-function provenance in one `DeriveContext` per invocation.

Owned handoffs let predecessor modules die before later phases begin.
`CoreIR.index-call-sites` consumes a module and retains its declaration storage
when reindexing bodies. See [the architecture](../docs/compiler-architecture.md)
for the preparation, planning, and emission boundaries.

```sh
carp -x test/carp-frontend.carp
```
