"""Command-line development checks and bounded native experiments."""
import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import sys

from . import __version__
from .backend import BackendError, NativeLinuxBackend, RunConfig
from .doctor import inspect_environment


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
