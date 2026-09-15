# Compiler architecture

Metacarp separates source loading, compiler phases, and output backends.
[`carp-compiler.carp`](../carp-compiler.carp) composes the phases; the CLI
entry points are [`main.carp`](../main.carp) and
[`main-llvm.carp`](../main-llvm.carp). The drivers share filesystem and package
loading through [`driver-load.carp`](../driver-load.carp).

## From source to executable

```text
host supplies source text
  -> surface parsing and module loading
  -> macro expansion and compile-time evaluation
  -> name resolution and declaration validation
  -> lifecycle derivation and runtime type inference
  -> interface selection and concrete specialization
  -> ownership checking and cleanup planning
  -> shared backend lowering
       -> C rendering -> clang
       -> LLVM emission -> native object + C shim -> clang
```

The [library index](README.md#libraries) links to each phase's representation
and API. These boundaries matter when embedding the compiler:

- `carp-module` orders and deduplicates supplied `ModuleSource` values. It does
  not read files or clone packages. Filesystem paths, Git resolution, and the
  shared package cache belong to the driver's source provider.
- `carp-surface` retains source-located syntax, including comments and container
  kinds. `carp-source` defines caller-visible source IDs, byte spans, and
  diagnostics.
- `carp-expand` removes macro-time forms before runtime resolution. Its
  compile-time environment and bytecode evaluator live in `carp-ct-env` and
  `carp-ct-eval`; expansion does not build a target executable to run a macro.
- `carp-resolve` creates the identity-based core model in `carp-ir`.
  Declaration validation and lifecycle derivation occur before ordinary
  inference. `carp-infer` uses the type model in `carp-types`.
- `carp-specialize` selects interface implementations and materializes concrete
  instances. Ownership requirements can require more concrete lifecycle
  functions, so specialization and planning are not just independent passes.
- `carp-ownership` records moves, borrows, and deletes in side tables. Shared
  backend lowering inserts cleanup, prepares expression shapes, and lifts
  closures before either backend emits code.

## The shared backend boundary

`BackendLower` produces `BackendModule`. `CBackend` renders it as a C
translation unit; `LLVMBackend` emits it into LLVM objects owned by its caller.
Both use `carp-c-abi` for symbol names and consume the same ownership-planned
bodies.

The LLVM path still uses a C shim for `deftemplate` sources and native runtime
operations. Aggregate calls across that boundary use generated wrappers so
the C compiler handles the platform C ABI. See the
[LLVM backend README](../carp-llvm-backend/README.md) for layouts, initialization,
debug maps, and linking.

Managed types receive concrete or generic `delete`/`copy` implementations.
Cleanup covers scopes, unused parameters, discarded intermediates, `set!`
overwrites, and owned pattern payloads. Escaping closures use heap-allocated
environments. Cleanup placement is scope-based; see the
[limitations](../README.md#limitations) before relying on reference-compiler
memory behavior.

## Reusable compiler entry points

Load `carp-compiler.carp` to use the batch compiler without the command-line
driver. Compilation functions return `Result` with `CompileError` on failure;
errors expose a phase and message.

| Entry point in `CarpCompiler` | Input and output |
| --- | --- |
| `compile-source` | One source string to C, without an implicit Core load. |
| `compile-sources` | An in-memory `ModuleSource` registry and root key to C. |
| `compile-module` | An already-loaded `SurfaceModule` to C. |
| `infer-module-with` | A loaded surface module and expansion config to `AnnotatedModule`. |
| `plan-module-checked` | A loaded module, expansion config, and names to check to `PlannedModule`. |
| `lower-source` | One source string to `BackendModule`. |
| `lower-module-full` | A loaded module, expansion config, check names, and echo choice to `BackendModule`. |

The `-with` variants of source and module compilation accept `ExpandConfig`.
Batch compilation does not supply the CLI's filesystem or Git source provider.
Use [carp-module](../carp-module/README.md) to understand registry loading.

For repeated notebook or editor operations, use
[carp-session](carp-session.md) instead of rechecking the base with batch
entry points. Native execution is a further host layer supplied by `SessionJit`.

## Experimental checks

[carp-ct-types](../carp-ct-types/README.md) and
[carp-ct-infer](../carp-ct-infer/README.md) are opt-in research libraries for the
compile-time language. The compiler pipeline does not invoke them.
`CtCheck.modules` checks macro and dynamic-function bodies against a tag
lattice; omitting it removes only its diagnostics, not a transformation.

For internal contracts and regression histories, read
[invariants](invariants.md). For executable checks of these boundaries, read
[development](development.md).
