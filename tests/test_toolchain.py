"""Compiler selection must work on Arch and diagnose setup failures visibly."""
from pathlib import Path
import shutil
import subprocess

import pytest

from yt2slp.toolchain import select_compiler


@pytest.mark.parametrize("version", [14, 15, 16])
def test_unversioned_gcc_fallback(monkeypatch, version):
    monkeypatch.delenv("CC", raising=False)
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/gcc" if name == "gcc" else None)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a[0], 0, f"#define __GNUC__ {version}\n"))
    assert select_compiler("CC", ("gcc-14", "gcc"), "c") == "/usr/bin/gcc"


@pytest.mark.parametrize("macros", ["#define __GNUC__ 13\n", "#define __GNUC__ 14\n#define __clang__ 1\n"])
def test_invalid_compiler_is_rejected(monkeypatch, macros):
    monkeypatch.delenv("CC", raising=False)
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/gcc")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a[0], 0, macros))
    with pytest.raises(ValueError, match="GNU GCC 14"):
        select_compiler("CC", ("gcc",), "c")


def test_explicit_missing_override_does_not_fall_back(monkeypatch):
    monkeypatch.setenv("CC", "missing-gcc")
    monkeypatch.setattr(shutil, "which", lambda name: None if name == "missing-gcc" else "/usr/bin/gcc")
    with pytest.raises(ValueError, match="missing-gcc: not found"):
        select_compiler("CC", ("gcc",), "c")


def test_setup_reports_missing_uv(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    tools = tmp_path / "bin"
    tools.mkdir()
    for name in ("dirname", "git"):
        (tools / name).symlink_to(shutil.which(name))
    result = subprocess.run(["/bin/bash", str(repo / "scripts/setup.sh")],
                            env={"PATH": str(tools)}, capture_output=True, text=True)
    assert result.returncode == 1
    assert "missing uv" in result.stderr


def test_game_build_without_setup_is_actionable(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    shutil.copy2(repo / "scripts/build_game.sh", scripts)
    result = subprocess.run(["bash", str(scripts / "build_game.sh")], capture_output=True, text=True)
    assert result.returncode == 1
    assert "run bash scripts/setup.sh successfully first" in result.stderr
    assert "pathspec" not in result.stderr
