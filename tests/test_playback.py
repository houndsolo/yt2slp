"""Report verification using synthetic stdout, never Dolphin/gameplay evidence."""
from copy import deepcopy
import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/validate_playback.py'
spec = importlib.util.spec_from_file_location('validate_playback', SCRIPT)
playback = importlib.util.module_from_spec(spec)
spec.loader.exec_module(playback)


def complete_report():
    return {'completeMatchValidated': True, 'replaySha256': 'a' * 64,
            'lastFrame': 1, 'metadata': {'lastFrame': 1},
            'gameEnd': {'gameEndMethod': 1, 'placements': []}}


def test_completion_report_matches_exact_file_and_final_frame():
    report = complete_report()
    assert playback.verify_complete_report(report, 'a' * 64, 1) == report['gameEnd']


@pytest.mark.parametrize('change', [
    {'completeMatchValidated': False}, {'replaySha256': 'b' * 64},
    {'lastFrame': 2}, {'metadata': {'lastFrame': 2}},
    {'gameEnd': {'gameEndMethod': 0}}, {'gameEnd': None}, {'metadata': None}, {},
])
def test_wrong_or_partial_completion_evidence_is_rejected(change):
    report = {} if not change else {**deepcopy(complete_report()), **change}
    with pytest.raises(ValueError, match='does not match'):
        playback.verify_complete_report(report, 'a' * 64, 1)


def stdout(frames=range(-123, 2), path='/replay.slp', end=1):
    return (f'[FILE_PATH] {path}\n[GAME_END_FRAME] {end}\n' +
            ''.join(f'[CURRENT_FRAME] {frame}\n' for frame in frames))


def test_official_reports_match_path_and_complete_interval():
    result = playback.assess_reports(stdout(), 1, Path('/replay.slp'), True)
    assert result['playbackPassed'] and result['gameEndFrameMatched']
    assert result['firstReportedFrame'] == -123 and result['lastReportedFrame'] == 1


@pytest.mark.parametrize('text', [
    stdout(frames=range(-122, 2)), stdout(frames=range(-123, 1)),
    stdout(frames=[*range(-123, 0), 1]), stdout(path='/different.slp'),
    stdout(end=2), stdout().replace('[GAME_END_FRAME] 1\n', ''),
    stdout() + '[CURRENT_FRAME] 1\n',
])
def test_wrong_incomplete_or_discontinuous_reports_cannot_pass(text):
    assert not playback.assess_reports(text, 1, Path('/replay.slp'), True)['playbackPassed']


def test_partial_playback_does_not_require_complete_match_end_frame():
    assert playback.assess_reports(stdout(end=1000), 1, Path('/replay.slp'))['playbackPassed']
