# carp-module

`carp-module` resolves a supplied graph of Carp source text into one ordered
`SurfaceModule`. It replaces top-level `(load "path")` and `(load-once "path")`
forms with their transitive source forms, detects cycles, and includes each
file once — deduplicated by the `ModuleSource`'s canonical `file`, so two load
spellings of the same file collapse. Each file's forms are bracketed with
load-stack markers the expander consumes, keeping the compile-time
`current-file` stack accurate. Macro expansion can therefore run over a
deterministic source stream.

The package intentionally does not read files, clone repositories, or manage a
cache. Those are driver concerns. A CLI, language server, test fixture, or
package resolver supplies `ModuleSource` values, then calls `ModuleLoader.load`.
Paths are registry keys at this stage; relative-path normalization, git/package
resolution, and filesystem caching belong in the driver-side source provider.

## Verification

```bash
carp -x test/execute.carp
```
