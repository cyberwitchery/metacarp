# carp-source

Stable source identities and byte spans shared by the parser, compiler IR, and
tooling APIs.

- `SourceInput` pairs caller-provided identity with exact UTF-8 source text.
- `SourceSpan` is a half-open byte range into that identified source.

The package deliberately has no reader or compiler-phase dependency. Surface
syntax converts reader positions into these spans, and later phases retain them
through provenance tables.
