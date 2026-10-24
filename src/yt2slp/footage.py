"""Frozen, bounded training footage selection; final-test sources stay unopened."""
import hashlib

from .learning_data import validate_split_plan


def capture_request_start(first, last):
    if type(first) is not int or type(last) is not int:
        raise ValueError('integer replay interval required')
    if -80 <= first < 0 < last <= 1800:
        return -123
    if 1 <= first <= last <= 28800 and 31 <= last-first+1 <= 1800:
        return max(-123, first-90)
    raise ValueError('bounded signed opening or positive clip of 31..1800 frames required')


def select_footage(plan, frames=600):
    """One clip per non-test replay, with date membership fixed by the old plan.

    Select positions from settings/end-frame metadata and a content hash only.
    No controls, later post states or model scores influence source selection.
    Previously audited pilot sources retain their original short intervals.
    """
    validate_split_plan(plan)
    if type(frames) is not int or not 31 <= frames <= 1800:
        raise ValueError('31..1800 frames per new clip required')
    pilots = {'c13e36c0f079200b6f00e2b3bef22ffe1165cde23797325218509718d794b40f',
              '35f1c56f2c5ac6ceeb74ff5144d923443bf34251d4404802408c28e577a48ae7'}
    result = []
    for match in sorted(plan['matches'], key=lambda m: (m['split'], m['replay_sha256'])):
        if match['split'] == 'test':
            continue
        if match['replay_sha256'] in pilots:
            first, last = -60, 180
        else:
            # Exclude the first ten seconds and leave two seconds before the end.
            latest_first = min(match['last_frame']-120, 28800)-frames+1
            if latest_first < 601:
                raise ValueError('source too short for the declared non-opening selection')
            word = hashlib.sha256(('yt2slp-footage-v2:'+match['replay_sha256']).encode()).digest()
            first = 601+int.from_bytes(word[:8], 'big') % (latest_first-601+1)
            last = first+frames-1
        capture_request_start(first, last)
        result.append({**match, 'interval': [first, last], 'reuse_pilot': match['replay_sha256'] in pilots})
    return result
