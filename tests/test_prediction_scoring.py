"""Exact frame/port scoring and unknown-label masks, with synthetic metadata."""
from copy import deepcopy
import pytest
from yt2slp.prediction_scoring import AXES, score_predictions


@pytest.fixture
def artifacts():
    settings = {'stage':31,'players':[{'port':0,'character':20},{'port':1,'character':2}]}
    labels = {'kind':'supervised-replay-labels','replay_sha256':'a'*64,'settings':settings,'rows':[]}
    predictions = {'kind':'frozen-image-controller-predictions','replay_sha256':'a'*64,
        'checkpoint_sha256':'b'*64,'settings':settings,'slot_ports':[1,0],
        'prediction_interval':[-1,1],'training_regression':False,'rows':[]}
    for f in range(-1,2):
        for p in (1,0):
            labels['rows'].append({'frame':f,'port':p,
                'physical':{'values':{'buttons':1024},'mask':{'buttons':True}},
                'physical_edges':{'pressed':1024,'released':512,'mask':True},
                'effective':{'values':{a:0. for a in AXES},'mask':dict.fromkeys(AXES,True)},
                'state':{'values':{'action':24,'airborne':False},'mask':{'action':True,'airborne':True}}})
            predictions['rows'].append({'frame':f,'port':p,'buttons':{'hold':1024,'press':1024,'release':512},
                'axis_bins':{a:0 if a=='trigger' else 8 for a in AXES},'action':24,'airborne':False})
    return predictions, labels


def test_scores_exact_keys_events_and_axes(artifacts):
    report = score_predictions(*artifacts)
    assert report['player_frames'] == 6 and report['slot_ports'] == [1,0]
    assert all(m['f1']==1 and m['all_released_baseline_f1']==0 for m in report['button_metrics'].values())
    assert all(m['mae']==0 and m['accuracy']==1 for m in report['axis_metrics'].values())
    assert not report['generated_replay_validated']


def test_unknowns_are_excluded_and_neutral_predictions_miss_events(artifacts):
    predictions, labels = deepcopy(artifacts)
    labels['rows'][0]['physical']['mask']['buttons'] = False
    labels['rows'][0]['physical']['values']['buttons'] = None
    labels['rows'][0]['effective']['mask']['stick_y'] = False
    labels['rows'][0]['effective']['values']['stick_y'] = None
    for row in predictions['rows']: row['buttons'] = dict.fromkeys(('hold','press','release'),0)
    report = score_predictions(predictions, labels)
    assert report['button_metrics']['hold']['compared'] == 60
    assert report['button_metrics']['hold']['f1'] == 0
    assert report['axis_metrics']['stick_y']['compared'] == 5


@pytest.mark.parametrize('change',['identity','duplicate','missing','shift','port'])
def test_scoring_refuses_alignment_repair(artifacts,change):
    predictions, labels = deepcopy(artifacts)
    if change == 'identity': labels['replay_sha256'] = 'c'*64
    if change == 'duplicate': predictions['rows'].append(predictions['rows'][0])
    if change == 'missing': labels['rows'].pop()
    if change == 'shift': predictions['rows'][0]['frame'] -= 1
    if change == 'port': labels['settings']['players'][0]['character'] = 2; predictions['settings'] = deepcopy(artifacts[0]['settings'])
    with pytest.raises(ValueError): score_predictions(predictions, labels)
