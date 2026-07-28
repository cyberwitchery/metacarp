# carp-session

Warm, transport-independent compiler sessions for notebook and editor hosts.

The initial API provides `Session.api-version`, `Session.create`,
`Session.create-from-module`, `Session.reset`, and transactional
`Session.infer-cell`. `Session.create` loads and checks Core once; subsequent
cells reuse the warm expansion, resolution, and inference snapshots.

On an Apple arm64 host, the real-Core benchmark in `test/benchmark.carp`
currently creates a session in about 1.88 seconds and checks 100 43-byte cells
in about 3.81 seconds: 38.1 ms per cell, with zero failures. The measured peak
memory footprint is about 117 MB (`/usr/bin/time -l`; max RSS about 236 MB).
See [`docs/carp-session.md`](../docs/carp-session.md) for the complete API plan.
