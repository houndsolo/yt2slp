"""Command-line development checks and bounded native experiments."""
import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import sys
import time

from . import __version__
from .backend import BackendError, NativeLinuxBackend, RunConfig
from .doctor import inspect_environment
from .match import MatchConfig, PlayerConfig, PadInput, NEUTRAL_PADS


def _path(value: str) -> Path:
    return Path(value).expanduser().resolve()


def main(argv: list[str] | None = None) -> int:
    """Run the CLI; return 0 on success, 1 for failed checks/runs, 2 for usage."""
    parser = argparse.ArgumentParser(description="Approximate Melee replay reconstruction: development foundation")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--repo", type=_path, default=Path.cwd(), help="yt2slp checkout (default: current directory)")
    commands = parser.add_subparsers(dest="command", required=True)
    doctor = commands.add_parser("doctor", help="check development and optional game prerequisites separately")
    doctor.add_argument("--iso", type=_path)
    doctor.add_argument("--dolphin", type=_path)
    doctor.add_argument("--json", action="store_true")
    doctor.add_argument("--require-game", action="store_true", help="fail if simulation prerequisites are missing")
    commands.add_parser("capabilities", help="show implemented backend operations")
    run = commands.add_parser("experiment", help="fresh native scripted run; requires your own ISO")
    run.add_argument("--iso", type=_path, default=_path(os.environ["YT2SLP_ISO"]) if os.environ.get("YT2SLP_ISO") else None)
    run.add_argument("--script", type=_path, required=True)
    run.add_argument("--retraces", type=int, default=3000)
    run.add_argument("--timeout", type=float, default=120)
    run.add_argument("--seed", type=int, default=1)
    run.add_argument("--time-base", type=int, default=0)
    run.add_argument("--repeat", action="store_true", help="compare two fresh runs' selected fields, not checkpoint determinism")
    stepping = commands.add_parser("step-experiment", help="fixed match with resumable VI stepping; requires your own ISO")
    stepping.add_argument("--iso", type=_path, default=_path(os.environ["YT2SLP_ISO"]) if os.environ.get("YT2SLP_ISO") else None)
    stepping.add_argument("--script", type=_path, required=True)
    stepping.add_argument("--steps", type=int, default=600)
    stepping.add_argument("--boot-limit", type=int, default=6000)
    stepping.add_argument("--timeout", type=float, default=180)
    stepping.add_argument("--seed", type=int, default=1)
    stepping.add_argument("--time-base", type=int, default=0)
    stepping.add_argument("--stage", type=int, choices=(31, 32), default=31, help="external StKind: 31 Battlefield, 32 Final Destination")
    stepping.add_argument("--p1", type=int, choices=range(26), default=2, help="external CharacterKind (2 Fox)")
    stepping.add_argument("--p2", type=int, choices=range(26), default=20, help="external CharacterKind (20 Falco)")
    stepping.add_argument("--repeat", action="store_true")
    stepping.add_argument("--check-input", action="store_true", help="also compare against a fresh neutral-input run (requires at least 400 steps)")
    checkpoint = commands.add_parser("checkpoint-experiment", help="capture and repeatedly restore a Linux process checkpoint; requires your ISO")
    checkpoint.add_argument("--iso", type=_path, default=_path(os.environ["YT2SLP_ISO"]) if os.environ.get("YT2SLP_ISO") else None)
    checkpoint.add_argument("--script", type=_path, required=True)
    checkpoint.add_argument("--warmup", type=int, default=240)
    checkpoint.add_argument("--steps", type=int, default=180)
    checkpoint.add_argument("--boot-limit", type=int, default=6000)
    checkpoint.add_argument("--timeout", type=float, default=180)
    checkpoint.add_argument("--seed", type=int, default=1)
    checkpoint.add_argument("--time-base", type=int, default=0)
    checkpoint.add_argument("--stage", type=int, choices=(31, 32), default=31)
    checkpoint.add_argument("--p1", type=int, choices=range(26), default=2)
    checkpoint.add_argument("--p2", type=int, choices=range(26), default=20)
    args = parser.parse_args(argv)
    try:
        if args.command == "doctor":
            report = inspect_environment(args.repo, args.iso, args.dolphin)
            if args.json:
                print(json.dumps(report, indent=2))
            else:
                for check in report["checks"]:
                    print(f"{'OK' if check['ok'] else 'MISSING'} [{check['scope']}] {check['name']}: {check['detail']}")
                print("Game startup, simulation and playback are not validated by doctor.")
            return 0 if report["simulation_prerequisites_present" if args.require_game else "development_ready"] else 1
        if args.command == "capabilities":
            print(json.dumps(NativeLinuxBackend.capabilities, indent=2))
            return 0
        if args.iso is None:
            raise BackendError("Melee ISO is not configured; set YT2SLP_ISO or --iso. No game run attempted.")
        if args.command == "checkpoint-experiment":
            return checkpoint_experiment(args)
        if args.command == "step-experiment":
            return step_experiment(args)
        backend = NativeLinuxBackend()
        backend.initialize(RunConfig(args.repo / "build/headless/melee_headless", args.repo / "build/game/melee_game.so",
                                     args.iso, args.repo / ".local/runs", args.seed, args.time_base))
        first = backend.run_script(args.script, args.retraces, args.timeout)
        directories = [str(backend.last_run_dir)]
        matched = None
        if args.repeat:
            second = backend.run_script(args.script, args.retraces, args.timeout)
            directories.append(str(backend.last_run_dir))
            matched = first == second
        report = {"run_directories": directories, "retraces": len(first),
                  "match_observations": sum(o.match_frame > 0 for o in first),
                  "final_state": asdict(first[-1].as_evidence()), "fresh_runs_selected_fields_match": matched,
                  "checkpoint_restoration_tested": False, "recording_tested": False, "playback_tested": False}
        print(json.dumps(report, indent=2))
        # A menu-only run is useful diagnostics but not a successful match experiment.
        if not report["match_observations"]:
            raise BackendError("run never produced an in-match observation; inspect the script and logs")
        return 1 if matched is False else 0
    except (BackendError, OSError) as exc:
        print(f"yt2slp: {exc}", file=sys.stderr)
        return 1


def step_experiment(args: argparse.Namespace) -> int:
    """Retain all traces and compare selected fields, without claiming parity."""
    if not 1 <= args.steps <= 100000 or (args.check_input and args.steps < 400):
        raise BackendError("steps must be 1..100000, and at least 400 for --check-input")
    match = MatchConfig(args.stage, (PlayerConfig(args.p1), PlayerConfig(args.p2)))
    directories = []

    def run(neutral: bool = False):
        with NativeLinuxBackend() as backend:
            backend.initialize(RunConfig(args.repo / "build/headless/melee_headless", args.repo / "build/game/melee_game.so",
                                         args.iso, args.repo / ".local/runs", args.seed, args.time_base, match))
            first = backend.start(args.script, args.timeout, args.boot_limit)
            directories.append(str(backend.last_run_dir))
            time.sleep(0.05)
            if backend.observe() != first:
                raise BackendError("state changed during pause")
            for i in range(args.steps):
                pads = NEUTRAL_PADS
                # Leave the countdown alone, then move/jump/attack using ordinary PAD input.
                if not neutral:
                    p1 = (PadInput(stick_x=80) if 240 <= i < 300 else
                          PadInput(button=0x400) if 300 <= i < 304 else
                          PadInput(button=0x100) if 320 <= i < 324 else PadInput())
                    pads = (p1, *NEUTRAL_PADS[1:])
                backend.step(pads)
            backend.observe()
            return backend.observations

    first = run()
    matched = first == run() if args.repeat else None
    baseline = run(neutral=True) if args.check_input else None
    # Attribute divergence to input only when the preceding neutral segment agrees.
    prefix_matches = first[:241] == baseline[:241] if baseline else None
    input_changed = (prefix_matches and any(a.fighters != b.fighters for a, b in zip(first[241:], baseline[241:]))) if baseline else None
    advanced = first[-1].match_frame > first[0].match_frame
    report = {"run_directories": directories, "requested_match": asdict(match),
              "step_unit": "VI retrace", "steps": args.steps,
              "initial_match_frame": first[0].match_frame, "final_match_frame": first[-1].match_frame,
              "pause_observation_stable": True, "match_frame_advanced": advanced,
              "fresh_runs_selected_fields_match": matched, "neutral_prefix_matches": prefix_matches,
              "input_changes_selected_fields": input_changed,
              "final_state": asdict(first[-1].as_evidence()),
              "checkpoint_restoration_tested": False, "recording_tested": False, "playback_tested": False}
    print(json.dumps(report, indent=2))
    return 1 if not advanced or matched is False or input_changed is False else 0


def checkpoint_experiment(args: argparse.Namespace) -> int:
    """One boot, one frozen checkpoint, four continuations and three restores."""
    if not 0 <= args.warmup <= 10000 or not 60 <= args.steps <= 10000:
        raise BackendError("warmup must be 0..10000 and steps must be 60..10000")
    match = MatchConfig(args.stage, (PlayerConfig(args.p1), PlayerConfig(args.p2)))
    with NativeLinuxBackend() as backend:
        backend.initialize(RunConfig(args.repo / "build/headless/melee_headless", args.repo / "build/game/melee_game.so",
                                     args.iso, args.repo / ".local/runs", args.seed, args.time_base, match))
        backend.start(args.script, args.timeout, args.boot_limit)
        for _ in range(args.warmup):
            backend.step(NEUTRAL_PADS)
        captured = backend.observe()
        handle = backend.capture()

        def continuation(neutral: bool = False):
            trace = []
            for i in range(args.steps):
                p1 = (PadInput(stick_x=80) if i < 30 else PadInput(button=0x400) if i < 34 else
                      PadInput(button=0x100) if 50 <= i < 54 else PadInput())
                trace.append(backend.step(NEUTRAL_PADS if neutral else (p1, *NEUTRAL_PADS[1:])))
            return tuple(trace)

        first = continuation()
        backend.restore(handle)
        time.sleep(0.05)
        stable = backend.observe() == captured
        repeated = continuation()
        backend.restore(handle)
        neutral = continuation(neutral=True)
        backend.restore(handle)
        after_divergence = continuation()
        # Preserve selected branch observations separately; state.csv is a native
        # diagnostic chronology containing rewinds, not a contiguous batch digest.
        traces = {"original": first, "restored_same_input": repeated,
                  "restored_neutral": neutral, "restored_after_divergence": after_divergence}
        with (backend.last_run_dir / "branches.json").open("w") as output:
            json.dump({name: [asdict(o) for o in trace] for name, trace in traces.items()}, output)
        report = {"run_directory": str(backend.last_run_dir), "requested_match": asdict(match),
                  "checkpoint_kind": "session-local Linux process fork", "step_unit": "VI retrace",
                  "warmup_steps": args.warmup, "continuation_steps": args.steps,
                  "captured_match_frame": captured.match_frame, "final_match_frame": first[-1].match_frame,
                  "restores": 3, "restored_pause_stable": stable,
                  "same_input_selected_fields_match": first == repeated,
                  "different_input_changes_fighter_fields": any(a.fighters != b.fighters for a, b in zip(first, neutral)),
                  "restore_after_divergence_matches": first == after_divergence,
                  "match_frame_advanced": first[-1].match_frame > captured.match_frame,
                  "checkpoint_restoration_tested": True, "full_state_equality_measured": False,
                  "recording_tested": False, "playback_tested": False}
        print(json.dumps(report, indent=2))
        return 0 if all(report[key] for key in ("restored_pause_stable", "same_input_selected_fields_match",
                        "different_input_changes_fighter_fields", "restore_after_divergence_matches", "match_frame_advanced")) else 1
