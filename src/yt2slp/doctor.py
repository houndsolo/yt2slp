"""Report development readiness separately from game and playback prerequisites."""
from pathlib import Path
import os
import platform
import shutil
import subprocess
import sys
import tempfile

from .toolchain import select_compiler


def _command(argv: list[str]) -> tuple[bool, str]:
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=15, check=False)
        return result.returncode == 0, (result.stdout or result.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)


def inspect_environment(repo: Path, iso: Path | None = None, dolphin: Path | None = None) -> dict:
    """Check versions, pinned checkout, artifacts, and actual directory writes.

    No game is started and no assets are obtained. ISO header checks only screen
    format/revision; the native host additionally checks the retail DOL hash.
    A configured Dolphin executable is not evidence of official provenance or
    successful playback. The report contains no credential values.
    """
    repo = repo.resolve()
    checks = []

    def add(name: str, ok: bool, detail: str, scope: str = "development") -> None:
        checks.append({"name": name, "ok": ok, "scope": scope, "detail": detail})

    add("platform", sys.platform == "linux" and platform.machine() in ("x86_64", "AMD64"), platform.platform())
    add("python", sys.version_info >= (3, 11), platform.python_version())
    for variable, names, language in (("CC", ("gcc-14", "gcc"), "c"), ("CXX", ("g++-14", "g++"), "c++")):
        try:
            compiler = select_compiler(variable, names, language)
            ok, version = _command([compiler, "--version"])
            add(variable, ok, f"{compiler}: {version.splitlines()[0] if version else 'no version output'}")
        except ValueError as exc:
            add(variable, False, str(exc))
    for tool in ("git", "cmake", "ninja"):
        executable = shutil.which(tool)
        ok, version = _command([executable, "--version"]) if executable else (False, "not on PATH; activate .venv")
        add(tool, ok, version.splitlines()[0] if version else "no version output")
    engine = repo / "third_party/melee-unlocked"
    ok, head = _command(["git", "-C", str(engine), "rev-parse", "HEAD"])
    pin_ok, pin = _command(["git", "-C", str(repo), "ls-files", "--stage", "third_party/melee-unlocked"])
    pinned = pin.split()[1] if pin_ok and pin.startswith("160000 ") else None
    add("engine_commit", ok and head == pinned, f"checkout={head}; parent gitlink={pinned}")
    for directory in (repo / "build", repo / ".local/runs"):
        try:
            directory.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryFile(dir=directory):
                pass
            add(f"writable:{directory.name}", True, str(directory))
        except OSError as exc:
            add(f"writable:{directory.name}", False, str(exc))
    host = repo / "build/headless/melee_headless"
    ok, detail = _command([str(host), "--memory-self-test"])
    add("native_host_low_memory", ok, detail)
    library = repo / "build/game/melee_game.so"
    add("game_library", library.is_file(), str(library) + " (presence only)", "simulation")
    if iso is None and os.environ.get("YT2SLP_ISO"):
        iso = Path(os.environ["YT2SLP_ISO"]).expanduser()
    valid_header = False
    detail = "not configured; set YT2SLP_ISO or --iso to a legally obtained uncompressed NTSC 1.02 ISO"
    if iso is not None:
        try:
            with iso.open("rb") as handle:
                header = handle.read(0x20)
            valid_header = len(header) == 0x20 and header[:6] == b"GALE01" and header[7] == 2 and header[28:32] == bytes.fromhex("c2339f3d")
            detail = str(iso) + (" (header only; DOL hash checked at startup)" if valid_header else " (not an NTSC 1.02 uncompressed disc header)")
        except OSError as exc:
            detail = str(exc)
    add("game_asset_header", valid_header, detail, "simulation")
    if dolphin is None and os.environ.get("YT2SLP_DOLPHIN"):
        dolphin = Path(os.environ["YT2SLP_DOLPHIN"]).expanduser()
    add("slippi_dolphin", dolphin is not None and dolphin.is_file() and os.access(dolphin, os.X_OK),
        str(dolphin) if dolphin else "not configured; set YT2SLP_DOLPHIN for later official playback validation", "playback")
    return {"checks": checks,
            "development_ready": all(c["ok"] for c in checks if c["scope"] == "development"),
            "simulation_prerequisites_present": all(c["ok"] for c in checks if c["scope"] != "playback"),
            "gameplay_validated": False, "playback_validated": False}
