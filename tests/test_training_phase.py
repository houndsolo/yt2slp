"""Synthetic phase-audit metadata; no game images, events or replay files."""
from copy import deepcopy

import pytest

from yt2slp.training_phase import audit_phase


@pytest.fixture
def evidence():
    index = [{'replay_frame': f, 'capture_image': f'{f+8}.png', 'capture_image_sha256': str(f)} for f in range(-8, 11)]
    labels = {'replay_sha256': 'a'*64, 'rows': [
        {'frame': f, 'port': p, 'state': {'values': {'airborne': (-2 <= f < 3) if p else f < 6},
            'mask': {'airborne': True}}} for f in range(-8, 11) for p in (0, 1)]}
    selected = [(-3, 1, False), (-2, 1, True), (2, 1, True), (3, 1, False), (5, 0, True), (6, 0, False)]
    observations = {'schema': 1, 'kind': 'manual-image-phase-observations',
        'source_replay_sha256': 'a'*64, 'fixed_post_offset': 0,
        'observations': [{'replay_frame': f, 'port': p, 'airborne': air,
            'capture_image': f'{f+8}.png', 'image_sha256': str(f), 'note': 'synthetic boundary observation'}
            for f, p, air in selected]}
    return observations, labels, index


def test_phase_audit_distinguishes_adjacent_offsets_and_retains_scope(evidence):
    report = audit_phase(*evidence)
    assert report['passed'] and report['matching_diagnostic_offsets'] == [0]
    assert report['observation_count'] == 6
    assert not report['native_vi_adapter_verified']
    assert not report['full_state_image_equality_established']
    assert all(report['diagnostics'][str(offset)]['mismatches'] for offset in (-2, -1, 1, 2))


@pytest.mark.parametrize('mutation', ['image', 'duplicate', 'missing', 'masked', 'offset', 'replay'])
def test_invalid_or_unbound_phase_evidence_fails(evidence, mutation):
    observations, labels, index = deepcopy(evidence)
    if mutation == 'image': observations['observations'][0]['image_sha256'] = 'changed'
    if mutation == 'duplicate': observations['observations'].append(observations['observations'][0])
    if mutation == 'missing': observations['observations'].pop()
    if mutation == 'masked': labels['rows'][0]['state']['mask']['airborne'] = False; labels['rows'] = labels['rows'][:2]
    if mutation == 'offset': observations['fixed_post_offset'] = 1
    if mutation == 'replay': observations['source_replay_sha256'] = 'b'*64
    with pytest.raises(ValueError): audit_phase(observations, labels, index)


def test_disagreement_is_a_reported_failure_without_fitting_an_offset(evidence):
    observations, labels, index = deepcopy(evidence)
    observations['observations'][0]['airborne'] = True
    result = audit_phase(observations, labels, index)
    assert not result['passed'] and result['diagnostics']['0']['mismatches']
