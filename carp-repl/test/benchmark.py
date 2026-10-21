#!/usr/bin/env python3
"""Measure optimized REPL startup, native evaluation, updates, and terminal keys."""
import json
import statistics
import time

# repl consumes the executable and Core arguments and supplies the PTY harness.
import repl


def distribution(values):
    ordered = sorted(values)
    return {
        "samples": len(values),
        "median_ms": round(statistics.median(values), 3),
        "p95_ms": round(ordered[min(len(ordered) - 1, int(len(ordered) * .95))], 3),
    }


def timed(action):
    start = time.perf_counter()
    action()
    return (time.perf_counter() - start) * 1000


def command(terminal, source, answer):
    terminal.send(source + b"\r")
    terminal.until(answer)
    terminal.until("λ> ".encode())


measurements = {key: [] for key in (
    "startup", "first_native", "warm_expression",
    "definition_addition", "definition_replacement", "key_response",
)}
for sample in range(5):
    start = time.perf_counter()
    with repl.Terminal() as terminal:
        measurements["startup"].append((time.perf_counter() - start) * 1000)
        for index in range(30):
            key = chr(0x430 + index).encode()
            measurements["key_response"].append(
                timed(lambda: (terminal.send(key), terminal.until(key)))
            )
        terminal.send(b"\x03")
        terminal.next_prompt()
        measurements["first_native"].append(
            timed(lambda: terminal.result(b"(Int.+ 20 22)", b"42"))
        )
        for iteration in range(5):
            measurements["warm_expression"].append(
                timed(lambda: terminal.result(b"(Int.+ 40 2)", b"42"))
            )
        measurements["definition_addition"].append(timed(
            lambda: command(terminal, b"(defn measured [] 17)", b"measured : (Fn [] Int)")
        ))
        measurements["definition_replacement"].append(timed(
            lambda: command(terminal, b"(defn measured [] 19)", b"measured : (Fn [] Int)")
        ))

print(json.dumps({
    "binary": repl.BINARY,
    "core": repl.CORE,
    "measurements": {key: distribution(value) for key, value in measurements.items()},
}, indent=2))
