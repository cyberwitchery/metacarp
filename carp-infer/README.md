# carp-infer

`carp-infer` performs Hindley–Milner-style inference for the resolved core
subset. It handles calls, conditionals, lexical lets, lambdas, and explicit
annotations. Top-level definitions are predeclared, inferred as one recursive
group, unified, then generalized. It records global call signatures together
with the final substitution for specialization.

Registered builtins and interface signatures seed the inference environment as
polymorphic schemes. Declaration variables use a separate identity space, so
they instantiate safely alongside inference variables.

Reference declarations retain implicit, named, or static `CoreLifetime`
syntax. Named lifetimes such as `(Ref String a)` share one quantified
`MonoLifetime` identity wherever `a` occurs; implicit references receive
distinct stable identities. Lifetime constraints pass through generalization,
instantiation, unification, and the final solver snapshot.
Local let-bound and top-level value lifetimes are not generalized, so repeated
uses retain one borrow identity. String and pattern literals carry `static`.

Ownership constraints and full Carp type syntax remain later gates.

```bash
carp -x test/carp-infer.carp
```
