"""Carry selected controller history between sessions; checkpoints remain local.

Only selected inputs, native identities and reproduced state/replay history are
used. No source-replay controls or known-source player state is read here.
"""
from dataclasses import asdict
import json
import re

from .match import NEUTRAL_PADS
from .search import HorizontalSequence, PadSequence, TwoPlayerSequence, run_schedule, schedule_from_dict
from .video import sha256


def observation_document(state):
    return json.loads(json.dumps(asdict(state)))


def native_identities(config, boot):
    return {name:sha256(path) for name,path in (
        ('host',config.host),('game',config.game_library),('iso',config.iso),('boot',boot))}


def validate_segments(segments):
    if not isinstance(segments,list) or not 1 <= len(segments) <= 32:
        raise ValueError('trajectory requires 1..32 consecutive windows')
    previous=None
    for segment in segments:
        if not isinstance(segment,dict) or set(segment)!={'first','last','schedule'}:
            raise ValueError('each trajectory segment needs first, last and schedule')
        first,last=segment['first'],segment['last']
        if (type(first) is not int or type(last) is not int or not 1 <= first < last <= 10000
                or last-first > 600 or previous is not None and first!=previous):
            raise ValueError('trajectory windows must be contiguous, ordered and bounded')
        schedule=schedule_from_dict(segment['schedule'])
        if isinstance(schedule,(HorizontalSequence,PadSequence)) and schedule.phases[-1].start_after>=last-first:
            raise ValueError('trajectory phase is outside its declared window')
        if isinstance(schedule,TwoPlayerSequence) and any(p.program.phases[-1].start_after>=last-first for p in schedule.port_programs):
            raise ValueError('player trajectory phase is outside its declared window')
        previous=last


def validate_prefix(prefix, spec, source_video_sha256, identities):
    if (prefix.get('schema')!=1 or prefix.get('kind')!='selected-trajectory-prefix'
            or prefix.get('source_video_sha256')!=source_video_sha256
            or prefix.get('native_identities')!=identities
            or prefix.get('start_recipe')!={k:spec[k] for k in ('rng_seed','time_base','known_match')}):
        raise ValueError('prefix source/start/native identities differ')
    validate_segments(prefix['segments'])
    if (prefix['segments'][-1]['last']!=spec['checkpoint_frame']
            or prefix['last_observation']['match_frame']!=spec['checkpoint_frame']
            or not re.fullmatch('[0-9a-f]{64}',prefix.get('replay_sha256',''))):
        raise ValueError('prefix does not end at the requested continuation boundary')


def advance_neutral(backend, frame):
    while backend.observe().match_frame < frame:
        previous=backend.observe().match_frame
        if backend.step(NEUTRAL_PADS).match_frame!=previous+1:
            raise ValueError('known prefix did not advance one match frame per VI')
    if backend.observe().match_frame!=frame:
        raise ValueError('prefix checkpoint precedes the match start')


def reproduce_prefix(backend, prefix, output):
    """Reboot/replay selected history; verify both boundary observation and .slp bytes."""
    validate_segments(prefix['segments'])
    advance_neutral(backend,prefix['segments'][0]['first'])
    for segment in prefix['segments']:
        if backend.observe().match_frame!=segment['first']:
            raise ValueError('prefix segment starts at a different boundary')
        run_schedule(backend,schedule_from_dict(segment['schedule']),segment['last']-segment['first'])
    if observation_document(backend.observe())!=prefix['last_observation']:
        raise ValueError('reproduced prefix boundary state differs')
    backend.record(output)
    if sha256(output)!=prefix['replay_sha256']:
        raise ValueError('reproduced prefix recording bytes differ')


def render_interval(spec):
    interval=spec.get('render_interval',[240,300])
    if (not isinstance(interval,list) or len(interval)!=2 or any(type(x) is not int for x in interval)
            or not spec['checkpoint_frame']<=interval[0]<=interval[1]<spec['end_frame']):
        raise ValueError('render interval must fit the search window, with a recorded end boundary')
    return interval
