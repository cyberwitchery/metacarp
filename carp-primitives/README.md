# carp-primitives

`carp-primitives` is the declarative registry of the compiler's builtins: one
table assigning each primitive a stable ID, name, phase, generic signature,
and lowering — intrinsic C, a runtime call, or a parameterized template
(array/box copy, delete, and str, which demand their element-type
dependencies at specialization). It also registers the builtin interface
implementations (`copy`, `delete`, `str`/`prn`) so dispatch and derivation
find containers without special cases. Every phase that needs to recognize a
builtin resolves it here by identity, never by name string.

```bash
carp -x test/carp-primitives.carp
```
