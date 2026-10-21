#!/usr/bin/env python3
"""Measure repeated navigation of one live result, excluding evaluation time."""
import json
import statistics
import time

import repl

samples = []
for _ in range(5):
    with repl.Terminal() as terminal:
        terminal.result(b"[[10 20] [30 40]]", b"[[10 20] [30 40]]")
        for _ in range(10):
            start = time.perf_counter()
            terminal.send(b":inspect 1 1 0\r")
            terminal.until(b"_1 1 0 : (Ref Int)\r\n30")
            terminal.until("λ> ".encode())
            samples.append((time.perf_counter() - start) * 1000)
ordered = sorted(samples)
print(json.dumps({
    "binary": repl.BINARY,
    "samples": len(samples),
    "median_ms": round(statistics.median(samples), 3),
    "p95_ms": round(ordered[int(len(samples) * .95)], 3),
}, indent=2))
