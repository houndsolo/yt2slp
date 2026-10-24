"""Measured native PAD calibration helpers, not a universal controller inverse.

Profiles are tied to the tested native binaries/setup. Exact single-axis lookup
preserves observed effective values; missing/unreachable values fail explicitly.
Compound stick/trigger/button behavior needs its own validation before use.
"""
from dataclasses import asdict
import math
import struct

from .match import PadInput

BUTTON_BITS = (1,2,4,8,16,32,64,256,512,1024,2048)
BUTTON_MASK = sum(BUTTON_BITS)  # Start intentionally excluded: it changes pause state.
AXIS_FIELDS = {'stick_x':'stick_x','stick_y':'stick_y','cstick_x':'sub_x','cstick_y':'sub_y',
               'trigger_l':'trigger_l','trigger_r':'trigger_r'}


def infer_lag(requests, rows, ports, actual, expected, candidates=range(5)):
    """Diagnose request-boundary -> replay-key lag over a common comparison window."""
    requested = {r['boundary_frame']:r for r in requests}
    first,last = min(requested)+max(candidates),max(requested)+min(candidates)
    keyed = {(r['frame'],r['port']):r for r in rows}
    diagnostics = {}
    for lag in candidates:
        mismatches = []; compared = 0
        for frame in range(first,last+1):
            for slot,port in enumerate(ports):
                row = keyed.get((frame,port))
                if row is None: raise ValueError('missing exact replay key during lag measurement')
                value = actual(row); wanted = expected(requested[frame-lag]['pads'][slot])
                if value is None: raise ValueError('masked/unknown calibration channel')
                compared += 1
                if value!=wanted: mismatches.append([frame,port])
        diagnostics[str(lag)] = {'compared':compared,'mismatches':mismatches}
    matches = [int(k) for k,v in diagnostics.items() if not v['mismatches']]
    if len(matches)!=1: raise ValueError(f'lag is ambiguous/unsupported: {matches}')
    return {'boundary_to_replay_lag':matches[0],'diagnostics':diagnostics}


def axis_bin(axis,value):
    low = 0 if axis.startswith('trigger') else -1
    if not math.isfinite(value) or not low-.001<=value<=1.001: raise ValueError('axis outside declared normalization')
    return min(16,max(0,round((value-low)/(1-low)*16)))


def axis_candidates(profile,axis,index):
    if axis not in AXIS_FIELDS or type(index) is not int or not 0<=index<=16:
        raise ValueError('known axis and 17-bin index required')
    samples = [s for s in profile['axis_samples'] if s['axis']==axis and axis_bin(axis,s['effective'])==index]
    if not samples: raise ValueError(f'{axis} bin {index} has no measured native realization')
    low = 0 if axis.startswith('trigger') else -1; center = low+index/16*(1-low)
    return sorted(samples,key=lambda s:(abs(s['effective']-center),abs(s['raw']),s['raw']))


def exact_single_axis_pad(profile,axis,value):
    """A tested scalar lookup, including its ordinary neutral counterpart axis."""
    samples = [s for s in profile['axis_samples'] if s['axis']==axis and s['effective']==value]
    if not samples: raise ValueError(f'{axis} effective value {value} not measured exactly')
    chosen = min(samples,key=lambda s:(abs(s['raw']),s['raw']))
    return PadInput(**{AXIS_FIELDS[axis]:chosen['raw']})


def decode_controlled_row(profile,row):
    """Restricted known-input roundtrip: A/B/X/Y plus one cardinal main axis.

    Refuses C-stick/trigger/compound axes and unsupported buttons. It is not yet
    the learned-proposal decoder. Source values/edges remain distinct targets.
    """
    physical,effective = row['physical'],row['effective']
    if not physical['mask']['buttons']: raise ValueError('physical buttons unknown')
    buttons = physical['values']['buttons']
    if buttons & ~(256|512|1024|2048): raise ValueError('buttons outside controlled adapter scope')
    if any(not effective['mask'][k] for k in ('stick_x','stick_y','cstick_x','cstick_y','trigger')):
        raise ValueError('effective controls unknown')
    values = effective['values']
    if values['cstick_x'] or values['cstick_y'] or values['trigger']:
        raise ValueError('C-stick/trigger combinations unvalidated by this roundtrip')
    if values['stick_x'] and values['stick_y']: raise ValueError('diagonal composition not validated')
    active = 'stick_x' if values['stick_x'] else 'stick_y'
    pad = exact_single_axis_pad(profile,active,values[active])
    return PadInput(**{**asdict(pad),'button':buttons})


def compare_control_labels(reference,candidate,first,last):
    """Compare independently parsed replay controls at exact frame/port keys.

    Effective fields are the playback gate. Physical fields are reported
    separately because replay playback need not reproduce a live PAD poll.
    """
    if type(first) is not int or type(last) is not int or first>last:
        raise ValueError('nonempty integer comparison interval required')
    ports=sorted(p['port'] for p in reference['settings']['players'])
    if len(ports)!=2 or ports!=sorted(p['port'] for p in candidate['settings']['players']):
        raise ValueError('same two physical replay ports required')
    left={(r['frame'],r['port']):r for r in reference['rows']}
    right={(r['frame'],r['port']):r for r in candidate['rows']}
    groups={}
    for group,names in (('effective',('buttons','stick_x','stick_y','cstick_x','cstick_y','trigger')),
                        ('physical',('buttons','trigger_l','trigger_r','raw_stick_x'))):
        fields={name:{'compared':0,'mismatches':0,'missing':0} for name in names}
        first_difference=None
        for frame in range(first,last+1):
            for port in ports:
                a,b=left.get((frame,port)),right.get((frame,port))
                for name in names:
                    metric=fields[name]
                    if (a is None or b is None or not a[group]['mask'][name] or not b[group]['mask'][name]):
                        metric['missing']+=1;continue
                    x,y=a[group]['values'][name],b[group]['values'][name]
                    same=x==y if name in ('buttons','raw_stick_x') else struct.pack('>f',x)==struct.pack('>f',y)
                    metric['compared']+=1;metric['mismatches']+=not same
                    if not same and first_difference is None:first_difference={'frame':frame,'port':port,'field':name,'reference':x,'candidate':y}
        groups[group]={'passed':all(not f['missing'] and not f['mismatches'] for f in fields.values()),
            'fields':fields,'first_difference':first_difference}
    return {'schema':1,'interval':[first,last],'player_frames':(last-first+1)*len(ports),
        'passed':groups['effective']['passed'],'groups':groups,
        'policy':'exact keys, float32 words and integers; physical diagnostics separate from effective playback gate'}
