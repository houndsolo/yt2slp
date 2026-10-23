"""Exact local bitmap calibration for official Playback's cyan frame-index OSD.

This reads the emulator UI, not game sprites or the frozen Ready HUD timer.
Templates are calibrated from retained screenshots and stay outside Git.
"""
import re

GEOMETRY = {'left': 20, 'top': 20, 'cell_width': 9, 'height': 15, 'cells': 18}
ALPHABET = set('Frame: -0123456789')


def cyan_cells(rgb: bytes, width: int, height: int, *, cropped: bool = False) -> list[str]:
    g = {**GEOMETRY, 'left': 0, 'top': 0} if cropped else GEOMETRY
    if len(rgb) != width*height*3 or width < g['left']+g['cells']*g['cell_width'] or height < g['top']+g['height']:
        raise ValueError('invalid or undersized RGB screenshot')
    words = []
    for cell in range(g['cells']):
        bits = []
        for y in range(g['top'], g['top']+g['height']):
            for x in range(g['left']+cell*g['cell_width'], g['left']+(cell+1)*g['cell_width']):
                r, green, blue = rgb[(y*width+x)*3:(y*width+x)*3+3]
                bits.append('1' if r < 80 and green > 190 and blue > 190 else '0')
        words.append(format(int(''.join(bits), 2), '034x'))
    return words


def add_calibration(templates: dict[str, str], cells: list[str], declared_frame: int) -> None:
    text = f'Frame: {declared_frame}'.ljust(GEOMETRY['cells'])
    if len(text) != len(cells):
        raise ValueError('frame index does not fit calibrated UI geometry')
    for character, word in zip(text, cells):
        if character in templates and templates[character] != word:
            raise ValueError('OSD glyph conflicts with declared index; unstable/misaligned screenshot')
        if any(existing == word and symbol != character for symbol, existing in templates.items()):
            raise ValueError('ambiguous OSD glyph calibration')
        templates[character] = word


def decode_index(cells: list[str], calibration: dict) -> int:
    templates = calibration.get('templates', {})
    if (calibration.get('schema') != 1 or calibration.get('geometry') != GEOMETRY
            or set(templates) != ALPHABET or len(set(templates.values())) != len(ALPHABET)
            or len(cells) != GEOMETRY['cells']):
        raise ValueError('complete exact frame-index calibration required')
    inverse = {word: symbol for symbol, word in templates.items()}
    if any(word not in inverse for word in cells):
        raise ValueError('unknown OSD glyph; frame remains unlabelled')
    text = ''.join(inverse[word] for word in cells).rstrip()
    if not re.fullmatch(r'Frame: -?(0|[1-9][0-9]*)', text):
        raise ValueError('invalid rendered frame-index text')
    return int(text.split(': ')[1])


def assess_step(before: int, after: int, next_log: int, new_images: list[str], *, paused_log_minus_osd: int = 0) -> dict:
    """OGL's PBO flush exports the *previous* rendered frame on the next swap.

    Require a real single-step transition. Positive-clock HUD anchors must
    independently validate this fixed source-audited one-swap association.
    """
    if (any(type(v) is not int for v in (before, after, next_log, paused_log_minus_osd))
            or paused_log_minus_osd not in (0, 1) or after != before+1
            or next_log != after+paused_log_minus_osd or len(new_images) != 1):
        raise ValueError('single-step log/OSD/PNG transition failed')
    return {'replay_frame': before, 'capture_image': new_images[0],
            'next_frame_log': next_log, 'next_frame_osd': after,
            'dump_pipeline_delay_swaps': 1}
