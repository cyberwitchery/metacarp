# carp-derive

`Derive` generates Core declarations before inference: record accessors,
`Pair.init-from-refs`, copies, deletes, string functions, and concrete generic
instances. `foreign-types.carp` supplies C representations and accessor bodies
for registered external types.

Every derivation that generates declarations takes a `DeriveContext` followed
by its borrowed Core module. The context belongs to one preparation invocation;
its identity policy and derived string-function provenance are shared across
that invocation’s passes. `CompilerFrontend` owns the semantic ordering:
typedefs, accessors, pair-refs, copies, deletes, strs, then close-generics.

Reindexing consumes the newly constructed module. Provenanced derivation keeps
its existing IDs without making a second full-module copy; the session’s
allocator identifies generated nodes afterwards.
