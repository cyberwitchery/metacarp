# Metacarp CLAP

This is a deliberately small programmable audio effect. The UI is one Carp
function, a Compile button, and compiler status. The initial function is an
identity effect:

```clojure
(sig process (Fn [Float] Float))
(defn process [x]
  x)
```

Change the body to `(Float.* x 0.5f)` and press Compile. A failed compilation
leaves the last successful function active.

This is an unsupported experiment, not a security boundary. Submitted Carp is
compiled to unsandboxed native code and executed inside the DAW process. Use
trusted code only: unsafe or invalid programs can crash the host, corrupt its
state, or access anything available to the host process.

## Architecture

The plugin shell is primarily Carp. `engine.carp` owns the warm
`CompilerSession`, the persistent LLVM `JitSession`, diagnostics, and compile
timing. Each edit is a transient cell compiled against that shared context.
Metacarp gives each cell a native symbol namespace, so a new `process` can be
published without unloading an older implementation.

`shell.m` is the platform boundary. It implements the CLAP ABI and a plain
Cocoa `NSTextView`, runs compilation on a worker thread, and stores the active
`float (*)(float)` in an atomic. The audio callback loads that pointer once at
the start of a block and calls it for each sample. It does not compile,
allocate, lock, log, perform I/O, wait, or unload code.

CLAP was chosen because its official C ABI is enough for this experiment and
does not require a plugin framework. The build pins the official CLAP 1.2.10
headers. Cocoa is the only platform UI implemented in this slice.

## Build

Requirements are macOS, Carp on `PATH`, Clang, Git, and Homebrew LLVM at
`/opt/homebrew/opt/llvm`. From the `carp-compiler` repository:

```sh
./experiments/metacarp-clap/build.sh
```

The result is:

```text
experiments/metacarp-clap/out/Metacarp.clap
```

The bundle includes the Carp Core sources because a Metacarp session needs
them while the plugin is running.

## Test without a DAW

The Metacarp JIT test covers identity, gain, failed compilation, repeated
replacement, and old-generation lifetime:

```sh
carp -b --optimize carp-llvm-backend/test/carp-session-jit.carp
./out/Untitled
```

The small CLAP host checks discovery, construction, activation, identity audio,
and destruction:

```sh
clang -I experiments/metacarp-clap/.deps/clap/include \
  experiments/metacarp-clap/smoke-host.c \
  -o experiments/metacarp-clap/out/smoke-host
./experiments/metacarp-clap/out/smoke-host \
  experiments/metacarp-clap/out/Metacarp.clap/Contents/MacOS/Metacarp
```

## Load in REAPER

Copy `Metacarp.clap` to `~/Library/Audio/Plug-Ins/CLAP/`, start a
[current REAPER](https://www.reaper.fm/) installation, and insert Metacarp from
the track FX browser as a stereo audio effect. If it is not listed, use
REAPER's Preferences > Plug-ins rescan action. Open the plugin editor, change
the function, and press Compile. Playback does not need to stop.

On the development machine, the bundle smoke test measured 806.2 ms for the
cold identity compilation, 63.3 ms for the warm gain replacement, and 3.49 ns
per scalar JIT call. The numbers are printed on every smoke run rather than
treated as stable benchmarks.

## Prototype compromises

- The user ABI is only `(Fn [Float] Float)`. An indirect call occurs per sample.
- The native UI is macOS-only and compilation is button-triggered.
- Plugin project state is not saved yet.
- Successful native generations remain resident until the plugin instance is
  destroyed. This is safe for realtime replacement but grows memory over a
  long editing session.
- Compiler work is serialized across plugin instances because some Metacarp
  caches are process-global.
- Scratch files are left in `/tmp` for inspection.

## Next steps

- Add a block ABI after measuring the scalar call overhead.
- Add CLAP state for the source buffer.
- Replace permanent generation retention with epoch-based retirement.
- Add optional debounced compilation and Cmd+Enter.
- Design explicit state allocation and migration for stateful DSP.

Persistent DSP state can later live beside the function address in an
immutable generation object. A new generation would create its state off the
audio thread; explicit user hooks could migrate state before the same atomic
block-boundary swap.
