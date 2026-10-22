# Engine evaluation

Inspected on 2026-10-22. Conclusions below refer to these commits, not to project
marketing or an assumption that Linux is unsupported.

| Project | Inspected commit | Role in yt2slp |
| --- | --- | --- |
| [Melee Unlocked](https://github.com/Hero88go/melee-unlocked) | `6177fd31acf250fe733089cd4471ce9c87969cf3` | Pinned submodule; native Linux game/host foundation |
| [slippi-js](https://github.com/project-slippi/slippi-js) | `ff815345e641836a331191320c0f6eae21542a5f` | Future independent replay parser, not a simulator |
| [slp2mp4](https://github.com/davisdude/slp2mp4) | `e290df4d7f25ac80f1211fb2560bd40be8e868a5` | Future official Dolphin playback/frame-dump orchestration reference |
| [libmelee](https://github.com/altf4/libmelee) | `1da979657122facd0750ea99cf6858255e198326` | Alternative Python controller/state interface through Slippi Dolphin |
| [doldecomp/melee](https://github.com/doldecomp/melee) | `039c4bf4ca33338c35d21901ad19b7ede19d19ad` | MU's pinned upstream game source, with MU's released native patch |

MU also pins `encounter/aurora` at
`d0c931da2ed3f41d0e42736c2ab52a78c7cf1a9d` in its `.gitmodules`. The selected
Linux game and host CMake targets do not consume Aurora; it was not initialized.
The three reference projects were inspected outside the yt2slp checkout. They
are not installed dependencies because this milestone neither produces a real
replay nor launches Dolphin.

## Decision

Use MU's **existing native Linux source game plus minimal Linux host**, in a
separate process. Add an independent CMake entry point for that host and its
portable component tests. Do not port the entire Windows application or use the
static recompiler as the first backend. Actual gameplay needs a user-provided
retail disc, but the source library and useful tests build without one.

This is a practical foundation for experiments, not yet a complete inverse
simulation backend. The shortest unblocked experiment here is to compile/load
the real game library and exercise real input, snapshot and recording components
without assets. The bounded script runner is ready for an asset-backed startup
experiment; that experiment remains unrun. A process owns the fixed game address
space, and process isolation lets failures and restarts leave Python intact.

## Three engine routes

| Route | Verified source evidence | Tradeoff and status |
| --- | --- | --- |
| Native source engine | [`sourceport/game/CMakeLists.txt`](../third_party/melee-unlocked/sourceport/game/CMakeLists.txt), `shim/mu_entry.c`, `port/linux/{main,host_services}.cpp` | Compiles decompiled C and hardware shims into `melee_game.so`; no translated PPC game code or retail DOL needed at compile time. Built and ELF-load checked here. Native execution fidelity still requires gameplay comparison. |
| Static recompilation | [`port/recomp/recomp.py`](../third_party/melee-unlocked/port/recomp/recomp.py), `port/runtime/ppc`, `port/CMakeLists.txt` | Verifies the retail DOL hash, translates PPC into C++ TUs and symbol/HLE headers, runs on the shared host. Root `MELEE_BUILD_EXPERIMENTAL_PORT` still requires Windows x64/MSVC. Not built here; needs disc-derived input and is a larger route. |
| Dolphin | libmelee `melee/console.py`, `controller.py`; slp2mp4 `dolphin/runner.py` | Slippi Dolphin provides the console/emulator behavior and is the final playback oracle. libmelee supplies controller flushing and next-state reception. No generic capture/restore API was found in that Python interface. Requires a Dolphin installation and disc. Not run here. |

MU has more Linux support than its minimal host: root `MELEE_BUILD_NATIVE_LINUX`
dispatches to [`port/linux/CMakeLists.txt`](../third_party/melee-unlocked/port/linux/CMakeLists.txt).
`MELEE_LINUX_GRAPHICS=OFF` already exists, but that CMake entry still requires
libusb. `port/linux/tests/build_headless_host.sh` is an isolated compiler command,
but does not define the `MELEE_LINUX_CPU_BASELINE` now required by `main.cpp`.
Our standalone `port/linux/headless/CMakeLists.txt` packages those existing
sources with the correct definitions and tests, without hardware dependencies.

The fuller [`port/linux/full/CMakeLists.txt`](../third_party/melee-unlocked/port/linux/full/CMakeLists.txt)
builds `melee_source` using shared source-host code and `port/linux/compat`.
It needs SDL2, OpenGL/GLEW, libusb, CURL, OpenSSL, FFmpeg libraries, shader tools,
and generated `hle_decls.h`/`guest_symbols.h`. These headers normally come from
the verified DOL via the recompiler. The Linux launcher also uses ImGui. The full
graphics/online application is outside this milestone; its existence is not
evidence that all its features work here.

## Toolchain, ABI and math

The game CMake explicitly requires GCC 14+ and x86-64. GCC's
`scalar_storage_order` supports console big-endian structs. Linux is LP64,
while Windows is LLP64: MU's `sourceport/tools/console_long_overlay.py` rewrites
console-sized `long` fields in a build overlay. It preserves explicit 64-bit
types and host shim declarations. The source checkout is not that overlay.

`tools/prepare_native_sources.py` expects the pinned doldecomp revision and
applies `sourceport/patches/melee-native.patch`. We run it in an ignored local
build checkout, keeping the actual nested submodule pristine. This patch is
required: the unpatched upstream tree does not contain all the SDK sources
referenced by native tests. One test used a hard-coded path into the unpatched
checkout; our include-path fix makes it use the same selected SDK overlay as
the game, without changing its assertions or tested routine.

[`port/runtime/abi/mu_host.h`](../third_party/melee-unlocked/port/runtime/abi/mu_host.h)
defines C function tables, currently host API **18**, game API **6**. The exported
entry point is `mu_game_entry(host, game)`. `MuGameApi.run()` owns the blocking
game loop. `retrace()` delivers a VI interrupt within that loop: it is **not** a
standalone function to advance one full game frame. Host polling delivers disc,
alarm, audio and VI work. Python must not simply call `retrace` through ctypes
and label it stepping.

The game uses 32-bit disc pointer slots (`sourceport/game/include/mu_disc.h`),
even in a 64-bit process. Low addresses are structural requirements:

- MEM1 is 40 MiB at `0x80000000`.
- The ELF game starts at `0x82800000`, immediately after MEM1, and must end below
  `0x84000000`, inside the 64 MiB GX address window.
- The Linux host also reserves locked-cache memory at `0xE0000000`.
- The host is PIE. Memory reservation uses `MAP_FIXED_NOREPLACE`, with a checked
  non-fixed hint fallback; it refuses collisions rather than replacing mappings.
- The host uses `dlopen(RTLD_NOW | RTLD_LOCAL)` / `dlsym`, inspects ELF segments,
  and checks both API versions and required callbacks.
- ELF symbols use hidden visibility plus `-Bsymbolic`/`-z defs` so host libc does
  not interpose on the game's simulation math. The game has a fixed linker layout.

We retained game flags `-O2`, `-fno-strict-aliasing`, `-fwrapv`,
`-fno-aggressive-loop-optimizations`, `-fno-builtin`, `-ffp-contract=on`,
`-mno-ms-bitfields`, CP932 execution charset, and Linux `-fno-tree-sra`.
The SDK math objects explicitly keep `-ffp-contract=off`. AVX2/FMA remains the
default, matching the inspected release build. No fast-math, checksum override,
or timing change was introduced. The host's `--fast` skips wall-clock sleep;
its console timebase still advances at 40.5 MHz with 60 Hz retraces.

## Platform audit

| Area | Existing Windows/shared path | Existing Linux path and selected scope |
| --- | --- | --- |
| File/disc/card I/O | Win32 APIs in `port/app/source_host.cpp` and runtime | `port/linux/host_services.cpp`: POSIX open/read, filesystem, native GCI persistence; tested without proprietary disc data |
| Timing | QueryPerformanceCounter / shared timebase | `std::chrono::steady_clock`, deterministic ticks and explicit boot epoch in minimal host |
| Threads | Win32 helpers in shared runtime | Standard C++ threads in snapshot engine; full app compatibility implementations; no global guard removal |
| Memory/loading | VirtualAlloc, LoadLibrary, write-watch optimization | mmap/dlopen/ELF checks; snapshot engine already falls back to byte comparisons outside `_WIN32` |
| Input | XInput, Win32 HID, adapter support | `input_script.cpp`, optional SDL and libusb; scripts are sufficient for headless experiment |
| Audio | WASAPI/ASIO in shared runtime | Real AX/DSP emulation in minimal host; optional SDL output, no output device in our target |
| Graphics | D3D11/12 and Windows GPU components | Linux OpenGL/SDL renderer and full-host substitutions already exist; not built here |
| Networking | Winsock/WinHTTP, ENet/Slippi | `compat` and full-host CURL/OpenSSL/ENet paths; minimal host has no connected Slippi command transport |
| Replay metadata time | `gmtime_s` | Small `_WIN32`/POSIX `gmtime_r` branch added so the real stream compiles independently of compatibility headers |

The Windows target definitions and guards remain in place. Windows compilation
was not available and is not claimed as validated.

## What is callable now

| Operation | Native source | yt2slp interface / evidence |
| --- | --- | --- |
| Initialize | `linux_host::initialize(Config)`, ABI negotiation, disc/header/DOL hash checks | `initialize(RunConfig)` binds paths; actual loading occurs in the run child. Native service and ELF load tests pass; real disc startup unrun. |
| Bounded scripted run | `linux_host::run`, `Config.max_frames`, `InputScript::apply`, `set_pad_override` | `run_script` invokes the existing executable, with timeout, isolated card/log files, seed and timebase. Python transport tested; gameplay unrun. |
| Observe | `MuGameApi.state_snapshot`, `set_frame_observer`, `main.cpp::observe` | Strict 77-column CSV parser; six fighters, raw IEEE-754 bits retained. Output is inferred relative to video. No selected-field digest is a full state hash. |
| Single-frame step | Blocking `game.run`, VI callback inside poll | Clear unsupported error. Needs a cooperative pause boundary that retains the live game stack. |
| Capture / restore | `snapshot_ranges`, `state_exclusions`; `native_savestate::Engine` | Components tested, including repeated `load_keep` and differential byte comparisons. Minimal host does not integrate them. Unsupported through Python. |
| Record | `shim/mu_replay.c`, `shim/mu_record_start.inc`; full host `h_replay_event`, `write_replay_recording` | Game recording code compiled. Minimal host leaves replay callbacks null and returns -1 for `slippi_command`; no `.slp` recording adapter yet. Unsupported through Python. |

`MuStateRegion` explicitly excludes live native stack, host timing, ARAM and
process allocations. Copying the declared regions at an arbitrary Python call
is not a safe checkpoint. Snapshot exclusions and the matching build's
`melee_game.snapexcl` must be understood, and the pause point must coordinate
pending disc callbacks, input-script phase, host ticks/alarms and recording.
MU's full host `begin_native_savestates` is the implementation reference, not an
already exported Python API.

`MU_NO_SLIPPI` is a **game-library** option: it removes replay playback/recording,
Slippi menus, practice and online-rule sources. It remains **OFF**. The separate
host-side `MELEE_NO_SLIPPI` macro/option is not equivalent; it excludes host
Slippi components in other builds. Our headless target does not use either
switch to remove features. Its existing minimal host simply lacks recorder
integration. Linking a replay-stream test does not change that capability.

## Recording after trying another branch

The full host already has a relevant transaction in
[`port/app/source_host.cpp`](../third_party/melee-unlocked/port/app/source_host.cpp):
`replay_keep` pairs `Engine::capture(frame)` with `NativeReplayStream::mark()`;
`replay_restore` calls `load_keep`, rewinds the stream, removes newer marks and
marks a graphics discontinuity. This is a replay-viewer path. It does not prove
arbitrary offline controller-search branches can safely be restored.

The stream mark contains event length, last frame, ended flag and character-usage
metadata. Our additional component regression appends a rejected branch, rewinds,
appends a selected branch and compares **encoded bytes** with a clean selected
stream. It repeats the rewind. The native savestate suite separately checks
repeatable loads and randomized differential restore against full buffer copies.
These are substantive component checks, not a joined game/recording experiment.

`rewind` cannot retract events already delivered to an external `EventSink`.
Trial branches must not be published to spectators or append-only output files.
For future reconstruction, search with transactional in-memory recording or no
output; then replay the chosen input sequence from a validated initial state
and record exactly that run. A valid `.slp` must contain the game-generated
events and matching settings/codes, not invented observations.

## Reference project findings

**slippi-js 9.1.3**: `src/common/SlippiGameBase.ts` reads game settings, frames,
metadata and statistics. `src/common/utils/slpParser.ts` handles rollback frame
replacement. `src/node/utils/slpFile{,Writer}.ts` wraps incoming Slippi events
in the file format; it is not a physics engine or a way to infer missing inputs.
Use it later to independently parse an actual selected-run `.slp`. No parser
validation was run in this milestone, because no gameplay recording exists.

**slp2mp4**: `src/slp2mp4/dolphin/runner.py` launches Slippi Playback with
`--exec`, `--slippi-input`, a private `--user` directory and frame-dump output.
It reads current/game-end frame reports; `ffmpeg.py` handles conversion. It
requires Python 3.11+, FFmpeg, the playback executable and an ISO. It is useful
for the final video comparison stage, not inverse simulation or checkpointing.

**libmelee 0.41.1**: `melee/console.py::run` handles Linux Dolphin executables,
`Console.step` flushes controllers and consumes Slippi events until frame end,
and `controller.py` supplies button/analog/pipeline input. `save_replays` writes
the Dolphin configuration's Slippi replay setting. Dependencies include pyenet,
py-ubjson, numpy, packaging and pyserial (pywin32 only on Windows). This is a
credible alternate simulation/control route if native integration proves too
costly; it still needs emulator/disc setup and a separate supported checkpoint
protocol. It was inspected, not installed or tested here.

## Next experiment and acceptance boundary

1. Make a retail NTSC 1.02 image accessible locally; run the bounded script and
   inspect real `match_frame`/fighter output. Wire the existing `MuMatchOverride`
   into a tested headless option to fix characters/stage; its minimal CLI does
   not currently expose it. Menu scripts alone do not guarantee that selection.
2. At a verified in-match boundary, add a cooperative native control protocol.
   Capture game ranges/exclusions and required host state, with a replay mark.
3. Capture C, apply sequence A, restore C, apply A, compare selected fields and
   covered memory bytes; restore C, apply B and verify the expected difference.
   State explicitly which bytes/host state are excluded from the comparison.
4. Record only the selected branch, parse with a pinned slippi-js version, then
   play it with official Slippi Dolphin and compare frame progression/end state.

Neither a successful build, passing synthetic event tests, matching selected
fields nor parser acceptance substitutes for this final gameplay/playback check.
