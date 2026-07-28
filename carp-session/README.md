# carp-session

Warm, transport-independent compiler sessions for notebook and editor hosts.

The initial API provides `Session.api-version`, `Session.create-from-module`,
and transactional `Session.infer-cell`. A host still owns filesystem loading;
the session owns the expensive expansion, resolution, and inference snapshot.
See [`docs/carp-session.md`](../docs/carp-session.md) for the complete API plan.
