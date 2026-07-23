# carp-backend

`carp-backend` lowers the specialized module and its ownership plan to one C
translation unit. It is two stages in one library:

`BackendLower` rewrites specialized bodies into emission shape: array literals
are hoisted out of value positions (ANF-style, freed after use unless
consumed), the ownership plan's deletes are inserted at the expression that
consumes each one — let scopes, `set!` sites (evaluate the new value, delete
the old, assign), by-value match branch exits, function exits for parameters —
wildcard pattern slots with a deleter are bound to fresh locals so their
payloads can be freed, capturing lambdas are lifted into closure functions
with heap-allocated environments, and top-level results are echoed through
their `str` implementations when the driver asks.

`CBackend` renders the result: struct/sum-type layouts with unit members
elided, pattern-binding extraction, the parameterized primitive templates
(array/box copy, delete, and str loops over their element dependency), and the
final translation unit with `carp_init_globals` and `main`. C names come from
`carp-c-abi`'s mangling.

Deletes name their concrete deleter symbol (resolved from the ownership
plan's requirements) — the shallow `__carp_array_free` sentinel is only a
fallback for arrays whose element type is unmanaged.

```bash
carp -x test/carp-backend.carp
```
