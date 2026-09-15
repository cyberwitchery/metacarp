# Metacarp documentation

Start with the [repository README](../README.md) to build the compiler and run
an example. This index covers the compiler libraries and development guides.

## Guides

- [Compiler architecture](architecture.md): phase boundaries, shared lowering,
  and reusable compilation entry points.
- [Session integration](carp-session.md): current API, source spans,
  transactions, committed inputs, queries, and code generation.
- [Development and verification](development.md): phase tests, reference-suite
  checks, fixed points, and benchmarks.
- [Compiler invariants](invariants.md): internal contracts and regression
  histories for compiler contributors.
- [LLVM backend](../carp-llvm-backend/README.md): lowering, C ABI shims, native
  linking, debug information, and persistent session JIT.

## Libraries

The directories contain Carp libraries and package-specific READMEs. The
compiler entry point that composes them is [`carp-compiler.carp`](../carp-compiler.carp).

| Library | Responsibility |
| --- | --- |
| [carp-source](../carp-source/README.md) | Source IDs, UTF-8 byte spans, structured diagnostics. |
| [carp-module](../carp-module/README.md) | Order and deduplicate a caller-supplied source graph. |
| [carp-surface](../carp-surface/README.md) | Parse and retain surface syntax. |
| [carp-expand](../carp-expand/README.md) | Expand macros and compile-time forms. |
| [carp-ct-env](../carp-ct-env/README.md) | Compile-time bindings and values. |
| [carp-ct-eval](../carp-ct-eval/README.md) | Compile-time evaluation and bytecode execution. |
| [carp-ir](../carp-ir/README.md) | Resolved core intermediate representation. |
| [carp-resolve](../carp-resolve/README.md) | Resolve globals, lexical bindings, and declarations. |
| [carp-types](../carp-types/README.md) | Runtime types, schemes, and substitutions. |
| [carp-infer](../carp-infer/README.md) | Runtime type inference. |
| [carp-specialize](../carp-specialize/README.md) | Interface selection and monomorphization. |
| [carp-ownership](../carp-ownership/README.md) | Moves, borrows, and cleanup planning. |
| [carp-backend](../carp-backend/README.md) | Shared lowering and C rendering. |
| [carp-c-abi](../carp-c-abi/README.md) | Symbol mangling shared by the backends. |
| [carp-primitives](../carp-primitives/README.md) | Declarative primitive registry. |
| [carp-graph](../carp-graph/README.md) | Dependency ordering and strongly connected components. |
| [carp-session](../carp-session/README.md) | Warm transactional compiler state for hosts. |
| [carp-llvm-backend](../carp-llvm-backend/README.md) | LLVM emission and session JIT. |

[carp-ct-types](../carp-ct-types/README.md) and
[carp-ct-infer](../carp-ct-infer/README.md) are experimental, opt-in checks for
the compile-time language. They are not invoked by the compiler pipeline.

The [CLAP experiment](../experiments/metacarp-clap/README.md) shows a native
host consuming a compiled float-to-float function through the session JIT.
