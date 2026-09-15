# carp-ct-env

`carp-ct-env` is a generic frame-and-cell environment for compile-time
interpreters.

Frames and cells have stable integer IDs. Closures retain a `FrameId`, child
calls allocate a frame whose parent is that defining frame, and `set!` updates
the resolved cell. Extending a scope therefore does not copy captured values.

A frame answers by scanning its bindings until it outgrows `index-threshold`,
at which point it builds a name index and keeps it up to date. The frames
created per call and per `let` hold a handful of bindings and never build one;
a module frame holding all of Core would otherwise be scanned, name by name,
by every reference that has to walk out to it.

Two kinds of binding are distinguished, because callers cache resolutions:

- `define!` binds a name a free reference elsewhere can see, and advances the
  store's `epoch`.
- `define-local!` binds a parameter, a `let` value or a loop variable. A
  caller that has already classified its local names cannot have a cached
  resolution invalidated by one, so the epoch stays where it is. Binding
  locals through `define!` instead would invalidate every cached resolution on
  every call.

`add-import!` also advances the epoch: an import changes what every name in
the importing frame can mean.

The library contains no syntax or evaluator policy. Its value type is generic,
so other interpreters can reuse it.
