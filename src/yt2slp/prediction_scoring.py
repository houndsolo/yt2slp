"""Post-prediction scoring at exact signed frame/physical-port keys. No fitting."""
import math

BUTTONS = {'dleft': 1, 'dright': 2, 'ddown': 4, 'dup': 8, 'z': 16, 'r': 32,
           'l': 64, 'a': 256, 'b': 512, 'x': 1024, 'y': 2048, 'start': 4096}
AXES = ('stick_x', 'stick_y', 'cstick_x', 'cstick_y', 'trigger')


def score_predictions(predictions: dict, labels: dict) -> dict:
    if (predictions.get('kind') != 'frozen-image-controller-predictions'
            or labels.get('kind') != 'supervised-replay-labels'
            or predictions['replay_sha256'] != labels['replay_sha256']):
        raise ValueError('same replay identity required for post-prediction scoring')
    settings = lambda s: (s['stage'], sorted((p['port'], p['character']) for p in s['players']))
    if settings(predictions['settings']) != settings(labels['settings']):
        raise ValueError('roster/physical port mismatch')
    targets = {(r['frame'], r['port']): r for r in labels['rows']}
    if len(targets) != len(labels['rows']): raise ValueError('duplicate target key')
    rows = predictions['rows']; first, last = predictions['prediction_interval']
    keys = [(r['frame'], r['port']) for r in rows]
    expected = {(f, p) for f in range(first, last+1) for p in predictions['slot_ports']}
    if len(set(keys)) != len(keys) or set(keys) != expected or not set(keys) <= targets.keys():
        raise ValueError('missing/duplicate prediction or exact-frame target key')
    buttons = {h: dict(tp=0, fp=0, fn=0, compared=0) for h in ('hold', 'press', 'release')}
    axes = {a: dict(compared=0, correct=0, absolute_error=0., squared_error=0., neutral_correct=0) for a in AXES}
    state = {s: dict(compared=0, correct=0) for s in ('action', 'airborne')}
    for row in rows:
        target = targets[row['frame'], row['port']]
        for h, value, valid in (
                ('hold', target['physical']['values']['buttons'], target['physical']['mask']['buttons']),
                ('press', target['physical_edges']['pressed'], target['physical_edges']['mask']),
                ('release', target['physical_edges']['released'], target['physical_edges']['mask'])):
            if not valid: continue
            for bit in BUTTONS.values():
                actual, guess = bool(value & bit), bool(row['buttons'][h] & bit)
                b = buttons[h]; b['tp'] += actual and guess; b['fp'] += guess and not actual
                b['fn'] += actual and not guess; b['compared'] += 1
        for a in AXES:
            if not target['effective']['mask'][a]: continue
            actual = target['effective']['values'][a]; low = 0 if a == 'trigger' else -1
            if not math.isfinite(actual) or not low-.001 <= actual <= 1.001: raise ValueError('invalid axis label')
            index = min(16, max(0, round((actual-low)/(1-low)*16)))
            guess = row['axis_bins'][a]
            if type(guess) is not int or not 0 <= guess <= 16: raise ValueError('invalid predicted axis bin')
            value = low+guess/16*(1-low); error = value-actual
            metric = axes[a]; metric['compared'] += 1; metric['correct'] += index == guess
            metric['absolute_error'] += abs(error); metric['squared_error'] += error*error
            metric['neutral_correct'] += index == (0 if a == 'trigger' else 8)
        for s in state:
            if target['state']['mask'][s]:
                state[s]['compared'] += 1; state[s]['correct'] += target['state']['values'][s] == row[s]
    for b in buttons.values():
        tp, fp, fn = (b[k] for k in ('tp', 'fp', 'fn'))
        b.update(positive_labels=tp+fn, f1=2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None,
            precision=tp/(tp+fp) if tp+fp else None, recall=tp/(tp+fn) if tp+fn else None,
            all_released_baseline_f1=0. if tp+fn else None)
    for a in axes.values():
        n = a['compared']; a['accuracy'] = a['correct']/n if n else None
        a['mae'] = a.pop('absolute_error')/n if n else None
        a['rmse'] = math.sqrt(a.pop('squared_error')/n) if n else None
        a['neutral_baseline_accuracy'] = a.pop('neutral_correct')/n if n else None
    for s in state.values(): s['accuracy'] = s['correct']/s['compared'] if s['compared'] else None
    return {'schema': 1, 'kind': 'exact-frame-controller-prediction-score',
        'replay_sha256': labels['replay_sha256'], 'checkpoint_sha256': predictions['checkpoint_sha256'],
        'training_regression': predictions['training_regression'], 'player_frames': len(rows),
        'prediction_interval': [first, last], 'slot_ports': predictions['slot_ports'],
        'button_metrics': buttons, 'axis_metrics': axes, 'state_metrics': state,
        'policy': 'post-prediction labels only; exact signed frame and physical port; masks exclude unknowns; fixed zero-logit threshold and phase; no lag search or retraining',
        'native_vi_adapter_verified': False, 'generated_replay_validated': False,
        'generalization_established': False}
