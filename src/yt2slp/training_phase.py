"""Bounded image/post phase audit using explicit, manually reviewed evidence."""


def audit_phase(observations: dict, labels: dict, image_index: list[dict]) -> dict:
    if (observations.get('schema') != 1 or observations.get('kind') != 'manual-image-phase-observations'
            or observations.get('source_replay_sha256') != labels.get('replay_sha256')
            or observations.get('fixed_post_offset') != 0):
        raise ValueError('identity-bound manual phase evidence with predeclared zero offset required')
    images = {r['replay_frame']: r for r in image_index}
    targets = {(r['frame'], r['port']): r for r in labels['rows']}
    seen = set(); events = observations.get('observations', [])
    if len(events) < 6: raise ValueError('insufficient independently reviewed phase observations')
    for event in events:
        frame, port = event['replay_frame'], event['port']
        image = images.get(frame)
        if (type(frame) is not int or type(port) is not int or (frame, port) in seen
                or type(event.get('airborne')) is not bool or not event.get('note', '').strip()
                or image is None or event.get('capture_image') != image['capture_image']
                or event.get('image_sha256') != image['capture_image_sha256']):
            raise ValueError('invalid, duplicate or unbound manual image observation')
        seen.add((frame, port))
    if len({p for _, p in seen}) != 2 or not any(f < 0 for f, _ in seen) or not any(f > 0 for f, _ in seen):
        raise ValueError('both players and pre/post-clock phase evidence required')
    diagnostics = {}
    for offset in (-2, -1, 0, 1, 2):
        mismatches = []
        for event in events:
            row = targets.get((event['replay_frame']+offset, event['port']))
            if row is None or not row['state']['mask']['airborne']:
                raise ValueError('missing phase comparison label; do not invent a ground/air target')
            if row['state']['values']['airborne'] != event['airborne']:
                mismatches.append({'image_frame': event['replay_frame'], 'port': event['port']})
        diagnostics[str(offset)] = {'compared': len(events), 'mismatches': mismatches}
    alternatives = [int(offset) for offset, d in diagnostics.items() if not d['mismatches']]
    passed = alternatives == [0]
    return {'schema': 1, 'kind': 'image-post-phase-audit', 'passed': passed,
        'source_replay_sha256': labels['replay_sha256'], 'image_to_post_offset': 0,
        'matching_diagnostic_offsets': alternatives, 'diagnostics': diagnostics,
        'observation_count': len(events),
        'scope': 'visually reviewed ground/air observations for both players before/after the clock, including visible takeoff/landing boundaries in this capture',
        'native_vi_adapter_verified': False, 'full_state_image_equality_established': False}
