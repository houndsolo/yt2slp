import pytest

from yt2slp.footage import capture_request_start, select_footage


def test_opening_and_midgame_capture_boundaries():
    assert capture_request_start(-60, 600) == -123
    assert capture_request_start(2400, 2999) == 2310
    assert capture_request_start(1, 600) == -89
    for first,last in ((0,600), (-90,600), (2400,5000), (28000,29000), (2,3), (True,600)):
        with pytest.raises(ValueError): capture_request_start(first,last)


def test_expanded_footage_keeps_frozen_splits_and_samples_beyond_openings():
    import json
    from pathlib import Path
    plan = json.loads((Path(__file__).parents[1]/'configs/learning-corpus-split-v1.json').read_text())
    selection = select_footage(plan)
    assert selection == select_footage(plan)
    assert len(selection) == 48
    assert {m['replay_sha256'] for m in selection}.isdisjoint(
        m['replay_sha256'] for m in plan['matches'] if m['split']=='test')
    for match in selection:
        first,last = match['interval']
        if match['reuse_pilot']:
            assert [first,last] == [-60,180]
        else:
            assert first >= 601 and last-first+1 == 600 and last <= match['last_frame']-120
    # Several matches may share a date; they retain the same split.
    groups = {}
    for match in selection:
        assert groups.setdefault(match['group'],match['split']) == match['split']
