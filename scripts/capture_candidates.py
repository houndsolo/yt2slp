"""Capture every exported candidate on the host with official Playback.

Run under xvfb-run. Completed identity-bound captures may be reused; incomplete
ones fail explicitly. The population is never reduced to whichever jobs finish.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--dolphin", type=Path, required=True)
    parser.add_argument("--iso", type=Path, required=True)
    args = parser.parse_args()
    root = args.candidates.resolve()
    manifest = json.loads((root / "candidates.json").read_text())
    if (manifest.get("kind") != "rendered-candidate-population" or not manifest["export_passed"]
            or not 1 <= len(manifest["candidates"]) <= 32 or digest(args.iso) != manifest["iso_sha256"]):
        raise ValueError("unsupported candidate population or ISO identity mismatch")
    completed = []
    for candidate in manifest["candidates"]:
        replay = root / candidate["replay"]
        out = replay.parent / "official"
        if digest(replay) != candidate["replay_sha256"]:
            raise ValueError("candidate replay identity mismatch")
        first, last = manifest["capture_interval"]
        if not out.exists():
            subprocess.run(["python", str(Path(__file__).with_name("capture_benchmark.py")), "--dolphin", str(args.dolphin),
                            "--iso", str(args.iso), "--replay", str(replay), "--output", str(out),
                            "--first", str(first), "--last", str(last), "--padding", str(manifest["capture_padding"])], check=True)
        report = json.loads((out / "capture.json").read_text())
        if (not report["capture_passed"] or report["should_resync"] is not False
                or report["source_replay_sha256"] != candidate["replay_sha256"]
                or report["wanted_interval"] != [first, last]):
            raise ValueError("incomplete or incompatible capture; preserve it and use a new export directory")
        completed.append(candidate["index"])
    if completed != manifest["expected_indices"]:
        raise ValueError("candidate capture population mismatch")
    print(json.dumps({"capture_jobs_complete": completed}))


if __name__ == "__main__":
    main()
