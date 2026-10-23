"""Inference contract guards; metadata fixtures are not gameplay/replay files."""
from copy import deepcopy
import json
import pytest

from yt2slp.model_contract import image_view, slot_ports, validate_image_view
from yt2slp.training_phase import frozen_phase_reference
from yt2slp.video import sha256


def test_slots_follow_unique_character_identity_when_physical_ports_swap():
    model = {'stage':31, 'slot_characters':[2,20]}
    settings = {'stage':31, 'players':[{'port':0,'character':20},{'port':1,'character':2}]}
    assert slot_ports(model, settings) == [1,0]
    for change in ('mirror','double','port','stage'):
        bad = deepcopy(settings)
        if change == 'mirror': bad['players'][0]['character'] = 2
        if change == 'double': bad['players'] *= 2
        if change == 'port': bad['players'][0]['port'] = 1
        if change == 'stage': bad['stage'] = 32
        with pytest.raises(ValueError): slot_ports(model, bad)


def test_temporal_view_rejects_frame_gaps_and_pts_drift():
    view = {'schema':1,'kind':'image-only-known-roster-video','time_base':'1/15360',
        'frames':[{'index':i,'pts':256*i,'replay_frame':i-2} for i in range(5)]}
    validate_image_view(view,3)
    for key in ('pts','replay_frame','index'):
        bad = deepcopy(view); bad['frames'][2][key] += 1
        with pytest.raises(ValueError): validate_image_view(bad,3)
    with pytest.raises(ValueError): validate_image_view(view,31)


def test_image_projection_never_opens_target_files(tmp_path):
    folder = tmp_path/'video'; decoded = folder/'ingested'; decoded.mkdir(parents=True)
    (folder/'source.mp4').write_bytes(b'identity fixture, never decoded')
    frames = []
    for i in range(3):
        image = decoded/f'{i}.png'; image.write_bytes(f'identity-only fixture {i}'.encode())
        frames.append({'index':i,'pts':i*256,'relative_seconds':str(i/60),
            'image':image.name,'image_sha256':sha256(image)})
    video = {'width':642,'height':528,'time_base':'1/15360','source_sha256':sha256(folder/'source.mp4'),'frames':frames}
    (decoded/'video.json').write_text(json.dumps(video))
    (folder/'capture-index.json').write_text(json.dumps([{'video_frame':i,'replay_frame':i-1} for i in range(3)]))
    setup = {'stage':31,'players':[{'port':p,'character':c,'costume':0,'private':'discard'} for p,c in ((0,2),(1,20))]}
    provenance = {'kind':'supervised-replay-source-video','passed':True,'supplied_setup':setup,
        'source_replay_sha256':'a'*64,'video_sha256':video['source_sha256'],'identities':{
            'video':sha256(decoded/'video.json'),'index':sha256(folder/'capture-index.json')}}
    (folder/'source-provenance.json').write_text(json.dumps(provenance))
    # Invalid JSON must be irrelevant: projection has no reason to open labels.
    (folder/'labels.json').write_text('DO NOT READ'); (folder/'phase-audit.json').write_text('DO NOT READ')
    output = tmp_path/'images.json'; view = image_view(folder,output)
    assert 'targets' not in str(view) and 'private' not in str(view)
    assert view['frames'][0]['replay_frame'] == -1
    (decoded/'1.png').write_bytes(b'changed')
    with pytest.raises(ValueError): image_view(folder,tmp_path/'changed.json')


def test_phase_transfer_keeps_independent_review_false_and_binds_reference(tmp_path):
    phase = {'kind':'image-post-phase-audit','passed':True,'image_to_post_offset':0,'matching_diagnostic_offsets':[0]}
    (tmp_path/'phase-audit.json').write_text(json.dumps(phase))
    (tmp_path/'frame-labels.json').write_text(json.dumps({'passed':True,'dump_pipeline_delay_swaps':1}))
    setup = {'stage':31,'replay_sha256':'a'*64,'players':[{'character':2},{'character':20}]}
    reference = tmp_path/'source-provenance.json'
    reference.write_text(json.dumps({'kind':'supervised-replay-source-video','passed':True,'supplied_setup':setup,
        'identities':{'phase':sha256(tmp_path/'phase-audit.json'),'frames':sha256(tmp_path/'frame-labels.json')}}))
    result = frozen_phase_reference(reference, setup, 'b'*64)
    assert result['passed'] and result['kind'] == 'image-post-phase-reference'
    assert result['target_phase_independently_reviewed'] is False
    with pytest.raises(ValueError): frozen_phase_reference(reference, setup, 'a'*64)
    (tmp_path/'phase-audit.json').write_text('{}')
    with pytest.raises(ValueError): frozen_phase_reference(reference, setup, 'b'*64)
