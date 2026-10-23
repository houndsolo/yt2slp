"""Strict frame-keyed scalar comparisons; never infer a best-fitting time shift."""
import math
import struct

FLOAT_FIELDS = ('x', 'y', 'facing', 'percent', 'shield', 'animation')
INTEGER_FIELDS = ('action', 'stocks', 'character')
FIELDS = FLOAT_FIELDS + INTEGER_FIELDS


def value(bits):
    return struct.unpack('!f', struct.pack('!I', bits))[0]


def _players(player_indices):
    if (type(player_indices) is not tuple or len(player_indices) != 2
            or any(type(p) is not int or not 0 <= p <= 3 for p in player_indices)
            or len(set(player_indices)) != 2):
        raise ValueError('comparison needs two distinct zero-based player ports')
    return player_indices


def index_rows(document, fields_to_compare=FIELDS, player_indices=(0,1)):
    _players(player_indices)
    if document.get('schema') != 1:
        raise ValueError('unsupported state export schema')
    result = {}
    for row in document['rows']:
        key = (row['frame'], row['player'])
        if any(type(v) is not int for v in key) or key[1] not in player_indices or key in result:
            raise ValueError('invalid or duplicate frame/player key')
        fields = row['fields']
        for name in fields_to_compare:
            bits = fields[name]
            if type(bits) is not int or not 0 <= bits <= 0xFFFFFFFF:
                raise ValueError('invalid scalar word')
            if name in FLOAT_FIELDS and not math.isfinite(value(bits)):
                raise ValueError('non-finite float not comparable under this policy')
        result[key] = fields
    if not result:
        raise ValueError('empty state export')
    return result


def compare_posts(reference, candidate, first, last, fields=FIELDS, compare_settings=True, player_indices=(0,1)):
    if type(first) is not int or type(last) is not int or first > last:
        raise ValueError('invalid comparison interval')
    if not fields or len(set(fields)) != len(fields) or any(f not in FIELDS for f in fields):
        raise ValueError("invalid field selection")
    player_indices = _players(player_indices)
    a, b = index_rows(reference, fields, player_indices), index_rows(candidate, fields, player_indices)
    expected = {(frame, player) for frame in range(first,last+1) for player in player_indices}
    missing_a, missing_b = sorted(expected-a.keys()), sorted(expected-b.keys())
    metrics = {name:{'compared':0,'bit_mismatches':0,'max_absolute_error':0.0,'squared_error':0.0} for name in fields}
    first_difference = None
    for key in sorted(expected & a.keys() & b.keys()):
        for name in fields:
            x,y = a[key][name],b[key][name]
            m = metrics[name]; m['compared'] += 1
            if x != y:
                m['bit_mismatches'] += 1
                if first_difference is None:
                    first_difference = {'frame':key[0],'player':key[1],'field':name,'reference_word':x,'candidate_word':y}
            error = abs((value(x)-value(y)) if name in FLOAT_FIELDS else x-y)
            m['max_absolute_error'] = max(m['max_absolute_error'],error)
            m['squared_error'] += error*error
    for m in metrics.values():
        m['rmse'] = math.sqrt(m.pop('squared_error')/m['compared']) if m['compared'] else None
    if compare_settings and any(not isinstance(d.get('settings'),dict) for d in (reference,candidate)):
        raise ValueError('missing match settings')
    settings_match = reference.get('settings') == candidate.get('settings') if compare_settings else None
    return {'interval':[first,last],'expected_player_frames':len(expected),
            'missing_reference':missing_a,'missing_candidate':missing_b,'settings_match':settings_match,
            'metrics':metrics,'first_difference':first_difference,
            'fields':list(fields),'settings_compared':compare_settings,
            'passed':(settings_match is True or not compare_settings) and not missing_a and not missing_b and first_difference is None,
            'policy':'exact float32 words and integers; no tolerance or fitted frame offset',
            'full_state_equality_measured':False,'image_equality_measured':False}


def observation_rows(observations, player_indices=(0,1)):
    _players(player_indices)
    rows=[]
    for o in observations:
        if o['scene_major'] != 2 or o['scene'] != 2:
            raise ValueError('observation outside supported VS scene')
        for player in player_indices:
            if len(o['fighters']) <= player:raise ValueError('missing supported fighter')
            f=o['fighters'][player]
            if len(f)!=12 or f[0]!=1:
                raise ValueError('missing supported fighter')
            rows.append({'frame':o['match_frame'],'player':player,'fields':{
                'action':f[2],'stocks':f[1],'animation':f[3],'x':f[4],'y':f[5],
                'percent':f[10],'facing':f[11]}})
    return rows
