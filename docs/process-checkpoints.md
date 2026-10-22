# Session-local Linux process checkpoints

`capture()` retains one frozen native process at the current paused VS boundary.
The active continuation runs in a child created by Linux `fork()`. `restore()`
discards that child and creates another child from the retained process. This
preserves the native stack and private process memory, including game RAM, host
heap, ARAM, input state, clocks, pending callbacks and audio state. The game is
not rebooted and inputs are not replayed from boot to reconstruct a checkpoint.
Game math, emulated timing constants and the game ABI remain unchanged.

This initial implementation supports **one reusable checkpoint per session**.
Capture requires a live two-player VS match and exactly one native thread.
The runner already requires headless, unpaced control mode. The native guard
rejects a threaded process before forking. The frozen owner only supervises and
reaps children; it never advances the game. Restoring repeatedly creates fresh
branches, including after a different-input continuation.

```python
# Inside an initialized and started NativeLinuxBackend context:
checkpoint = backend.capture()
at_capture = backend.observe()
first = tuple(backend.step(pads) for pads in input_sequence)
backend.restore(checkpoint)
assert backend.observe() == at_capture
second = tuple(backend.step(pads) for pads in input_sequence)
assert first == second
```

The returned bytes are an **opaque handle**, not serialized savestate bytes.
They work only with the originating live backend session. Close, reinitialize,
restart, or a protocol failure invalidates them. Unknown/expired handles are
rejected before touching the native process. A second capture is explicitly
unsupported; start a new session to choose another checkpoint. Portable exports,
multiple retained checkpoints and renderer/device state are not implemented.
`record()` now exports genuine events from the selected live branch; see
[recording](slippi-recording.md).

## Side effects and cleanup

All control sessions now use an initially empty **in-memory memory card**.
Create/write/rename/delete/format operations update process memory; unmount and
remount retain that data inside the session. They never read or modify a disk
card. This makes card data part of the process checkpoint and prevents discarded
branches from changing future loads. Batch `run_script()` retains its original
private-directory GCI persistence. This choice is explicit: control-session
saves disappear on close and cannot be exported yet.

Disc reads use `pread` on a read-only ISO. Keep the ISO and game library unchanged
throughout the session. Diagnostics are append-only external output, not restored
game state. Native C++ digest and stdio buffers are flushed before capture and
restore so a fork cannot duplicate buffered output. `state.csv` contains retrace
rewinds after restores and is therefore not a contiguous batch digest;
`inputs.txt` records capture/restore boundaries. The CLI additionally saves four
selected-state traces in `branches.json`, one for each continuation.

The retained owner waits for each child and requires both an explicit restore
marker and the reserved exit status before branching again. A normal game exit,
EOF, or failure ends the owner too. The child receives a death signal if its
owner dies. Python starts a dedicated process group, closes the control socket on
cleanup, and kills that group if graceful shutdown times out. Use a context
manager or call `close()`; a retained checkpoint consumes memory until then.

## Validate locally with your ISO

From the repository, using the previously built Docker image:

```bash
git pull --ff-only
bash scripts/docker.sh setup
export YT2SLP_ISO=/home/houndsolo/Documents/vanilla.iso
bash scripts/docker.sh run yt2slp checkpoint-experiment \
  --script third_party/melee-unlocked/port/scripts/native_vs.txt \
  --stage 31 --p1 2 --p2 20 --warmup 240 --steps 180 \
  --seed 1 --time-base 0 --timeout 180
```

This boots once, advances 240 neutral retraces, captures, and runs four
continuations with three restores: original inputs, the same inputs again,
neutral inputs, and original inputs after the divergent branch. It checks stable
restored observations, matching selected fields for identical inputs, changed
fighter fields for different inputs, and advancing match frames. Exit status 1
means a check failed. Output is under `.docker-state/local/runs/step-*`.

Cloud tests exercise the real fork implementation against synthetic native
state and actual host services. They verify repeated restoration of fixed RAM,
ARAM, clocks, audio pointers, pending callbacks into the native stack, inputs,
and volatile card data. Protocol tests cover invalid handles/replies, thread
rejection, trace buffering, owner death and forced cleanup of a stopped branch.
These tests establish component behavior; no ISO is available in this workspace.
The CLI compares selected observations, not a full memory hash or retail parity.
The user subsequently validated the ISO experiment: capture at match frame 241,
180-step continuations to 421, stable restored state, matching identical-input
continuations, divergent changed inputs, and matching original continuation after
returning from the divergent branch across three restores. Artifacts are retained
at `.docker-state/local/runs/step-2o7rj74b/`. This remains selected-field evidence.
Recording and official playback have now also been exercised locally; see
[the separate validation record](slippi-recording.md).


Complete-match follow-up: a pre-ending checkpoint at match frame 6901 was restored
three times after completed continuations. Each restore cleared recording's
ended flag; original/identical/selected full recordings ending at frame 7200
matched byte-for-byte, and the changed-input recording differed. Post-ending
callbacks were safe and extra steps did not change recorded bytes. See
[the complete timed-match evidence](slippi-recording.md#complete-timed-match-follow-up--2026-10-22).
