"""CLI failure reporting must not imply a game has run."""
import json

from yt2slp.cli import main
from yt2slp.doctor import inspect_environment


def test_capabilities(capsys):
    assert main(["capabilities"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["run_script"] and not report["restore"] and not report["record"]


def test_missing_iso_is_actionable(monkeypatch, capsys):
    monkeypatch.delenv("YT2SLP_ISO", raising=False)
    assert main(["experiment", "--script", "nonexistent.txt"]) == 1
    assert "No game run attempted" in capsys.readouterr().err


def test_doctor_missing_checkout_is_not_ready(tmp_path, monkeypatch):
    monkeypatch.delenv("YT2SLP_ISO", raising=False)
    monkeypatch.delenv("YT2SLP_DOLPHIN", raising=False)
    report = inspect_environment(tmp_path)
    assert not report["development_ready"]
    assert not report["simulation_prerequisites_present"]
    assert not report["gameplay_validated"]
    assert not report["playback_validated"]
    scopes = {c["name"]: c["scope"] for c in report["checks"]}
    assert scopes["game_asset_header"] == "simulation"
    assert scopes["slippi_dolphin"] == "playback"


def test_step_experiment_with_native_protocol_fixture(tmp_path, capsys):
    from pathlib import Path
    host = Path(__file__).resolve().parents[1] / "build/headless/headless_control_fixture"
    assert host.is_file(), "run bash scripts/setup.sh first"
    (tmp_path / "build/headless").mkdir(parents=True)
    (tmp_path / "build/game").mkdir(parents=True)
    (tmp_path / "build/headless/melee_headless").symlink_to(host)
    (tmp_path / "build/game/melee_game.so").touch()
    (tmp_path / "disc.iso").touch()
    (tmp_path / "boot.txt").touch()
    assert main(["--repo", str(tmp_path), "step-experiment", "--iso", str(tmp_path / "disc.iso"),
                 "--script", str(tmp_path / "boot.txt"), "--steps", "400", "--repeat", "--check-input"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["pause_observation_stable"] and report["fresh_runs_selected_fields_match"]
    assert report["neutral_prefix_matches"] and report["input_changes_selected_fields"]
    assert report["step_unit"] == "VI retrace"
    assert len(report["run_directories"]) == 3
    assert report["requested_match"]["players"][1]["character"] == 20
    assert not report["checkpoint_restoration_tested"] and not report["recording_tested"]


def test_step_experiment_requires_iso(monkeypatch, capsys):
    monkeypatch.delenv("YT2SLP_ISO", raising=False)
    assert main(["step-experiment", "--script", "boot.txt"]) == 1
    assert "No game run attempted" in capsys.readouterr().err


def test_step_experiment_rejects_short_input_check(capsys):
    assert main(["step-experiment", "--iso", "disc.iso", "--script", "boot.txt", "--steps", "10", "--check-input"]) == 1
    assert "at least 400" in capsys.readouterr().err
