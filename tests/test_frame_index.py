"""Synthetic UI cells exercise recognition/transport; no game images or SLPs."""
import pytest

from yt2slp.frame_index import ALPHABET, GEOMETRY, add_calibration, assess_step, cyan_cells, decode_index


def calibration():
    return {'schema': 1, 'geometry': dict(GEOMETRY),
            'templates': {c: f'{i:034x}' for i, c in enumerate(sorted(ALPHABET))}}


def words(text, c):
    return [c['templates'][character] for character in text.ljust(GEOMETRY['cells'])]


@pytest.mark.parametrize('frame', [-123, -40, -1, 0, 1, 180])
def test_exact_signed_indices_and_zero(frame):
    c = calibration()
    assert decode_index(words(f'Frame: {frame}', c), c) == frame


def test_calibration_rejects_conflicting_or_ambiguous_glyphs():
    c = calibration()
    observed = words('Frame: -105', c)
    learned = {}
    add_calibration(learned, observed, -105)
    with pytest.raises(ValueError, match='conflicts|ambiguous'):
        add_calibration(learned, observed, -104)
    with pytest.raises(ValueError):
        add_calibration({}, ['0'*34]*GEOMETRY['cells'], -105)


def test_missing_or_unknown_glyphs_never_guess_an_index():
    c = calibration()
    observed = words('Frame: -40', c)
    observed[8] = 'f'*34
    with pytest.raises(ValueError, match='unknown'):
        decode_index(observed, c)
    c['templates'].pop('6')
    with pytest.raises(ValueError, match='complete'):
        decode_index(observed, c)


def test_cyan_mask_uses_exact_declared_cell_geometry():
    width, height = 200, 40
    pixels = bytearray(width*height*3)
    point = (GEOMETRY['top']*width+GEOMETRY['left'])*3
    pixels[point:point+3] = bytes((0, 255, 255))
    result = cyan_cells(bytes(pixels), width, height)
    assert int(result[0], 16) == 1 << 134
    assert all(int(word, 16) == 0 for word in result[1:])


@pytest.mark.parametrize('after,osd,new', [(-39, -39, []), (-39, -39, ['a', 'b']),
    (-38, -38, ['a']), (-39, -40, ['a'])])
def test_step_rejects_gaps_duplicates_or_display_lag(after, osd, new):
    with pytest.raises(ValueError):
        assess_step(-40, after, osd, new)


def test_pbo_label_uses_previous_frame_with_independent_next_osd():
    assert assess_step(-40, -39, -39, ['framedump_99.png']) == {
        'replay_frame': -40, 'capture_image': 'framedump_99.png',
        'next_frame_log': -39, 'next_frame_osd': -39, 'dump_pipeline_delay_swaps': 1}


def test_paused_console_can_be_one_frame_ahead_but_must_keep_fixed_relation():
    row = assess_step(-40, -39, -38, ['a'], paused_log_minus_osd=1)
    assert row['replay_frame'] == -40 and row['next_frame_osd'] == -39 and row['next_frame_log'] == -38
    with pytest.raises(ValueError):
        assess_step(-40, -39, -39, ['a'], paused_log_minus_osd=1)


def test_exact_prescribed_crop_matches_full_screenshot_cells():
    width, height = 200, 40
    pixels = bytearray(width*height*3)
    point = (GEOMETRY['top']*width+GEOMETRY['left'])*3
    pixels[point:point+3] = bytes((0, 255, 255))
    cropped = b''.join(pixels[(y*width+20)*3:(y*width+182)*3] for y in range(20, 35))
    assert cyan_cells(cropped, 162, 15, cropped=True) == cyan_cells(bytes(pixels), width, height)
