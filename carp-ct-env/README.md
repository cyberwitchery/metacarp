# carp-ct-env

`carp-ct-env` is a generic frame-and-cell environment for compile-time
interpreters.

Frames and cells have stable integer IDs. Closures retain a `FrameId`, child
calls allocate a frame whose parent is that defining frame, and `set!` updates
the resolved cell. Extending a scope therefore does not copy captured values.

The library contains no syntax or evaluator policy. Its value type is generic,
so other interpreters can reuse it.
