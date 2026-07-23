# carp-ir

`carp-ir` defines the resolved, compiler-owned core representation shared by
resolution, inference, and specialization. `CoreRef.id` is the stable binding
identity; names remain only for diagnostics and generated symbols.

`CoreExpr` covers literals, resolved references, calls, `if`, `do`, lexical
`let`, `set!`, `while`, `break`, `match`, lambdas, array and static-array
literals, and explicit type annotations. `CoreModule` carries function
definitions, values, builtins and builtin sources, type and constructor
declarations, interface signatures, implementation registrations, and requested
system includes. It has no dependency on the reader, macro expander, or type
implementation.
