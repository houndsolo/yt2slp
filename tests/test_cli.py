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
