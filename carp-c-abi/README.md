# carp-c-abi

`carp-c-abi` is the C identity layer the later phases share: deterministic
name mangling from a Carp path plus a concrete signature to a C symbol,
sanitization of raw identifiers, and the canonical `type-key` string for a
concrete type — the key the ownership plan, deleter tables, and instance
deduplication all agree on. Keeping it in one library means a symbol or key
computed in specialization always matches the one the backend renders.

`symbol-for-key` and `symbol-for-type` look up selected native symbols in these
tables. Exact keys use the last matching entry and retain the symbol's spelling;
renderers apply their own identifier normalization afterward.

```bash
carp -x test/carp-c-abi.carp
```
