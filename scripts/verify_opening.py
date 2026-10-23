"""Compare a genuine opening recording with its actual official playback.

This checks selected state fields, not likeness to the tournament footage.
The raw native match counter and separately observed signed frame keys remain
separate. No tolerated float errors, frame fitting or resync.
"""
import argparse
import json
from pathlib import Path

from yt2slp.benchmark import compare_posts, observation_rows
from yt2slp.match import match_from_document
from yt2slp.video import sha256
from probe_tournament_start import export


def read(path):
    return json.loads(path.read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    args = parser.parse_args()
    root = args.run.resolve()
    search = read(root/'search-result.json')
    spec = read(root/'search-spec.json')
    capture = read(root/'official/capture.json')
    match = match_from_document(spec['match'])
    interval = [-39, spec['end_frame']]
    if (spec.get('kind') != 'manual-replay-frame-search'
            or not all(search.get(k) for k in ('passed', 'parser_validated',
                'fresh_selected_observations_match', 'fresh_recording_keys_match', 'fresh_recording_bytes_match'))
            or search['frame_clock'] != 'slippi-replay'
            or not capture['capture_passed'] or capture['should_resync'] is not False
            or capture['playback_version'] != '3.5.2' or capture['wanted_interval'] != interval
            or capture['include_preroll'] is not True or len(capture['regenerated_replays']) != 1
            or search['identities']['/assets/melee.iso'] not in capture['identities'].values()
            or sha256(root/'selected.slp') != search['selected_replay_sha256']
            or capture['source_replay_sha256'] != search['selected_replay_sha256']):
        raise ValueError('missing identity-bound fresh/parser/official opening evidence')
    out = root/'official-analysis'
    out.mkdir(exist_ok=False)
    native = export(root/'selected.slp', out/'native-state.json')
    official = export(root/'official'/capture['regenerated_replays'][0], out/'official-state.json')
    states = compare_posts(native, official, *interval, player_indices=match.ports)
    trial = read(root/'trials'/f"{search['selected_index']:03d}.json")
    if len(trial['states']) != len(trial['replay_frame_keys']):
        raise ValueError('raw observations lack recorded keys')
    observed = []
    for key, state in zip(trial['replay_frame_keys'], trial['states']):
        for row in observation_rows([state], match.ports):
            row['frame'] = key
            observed.append(row)
    phase = compare_posts(native, {'schema': 1, 'rows': observed}, *interval,
        fields=('action', 'stocks', 'animation', 'x', 'y', 'percent', 'facing'),
        compare_settings=False, player_indices=match.ports)
    report = {'schema': 1, 'passed': states['passed'] and phase['passed'],
        'interval': interval, 'player_ports': list(match.ports),
        'native_vs_official_postframes': states, 'native_observation_phase_check': phase,
        'source_replay_sha256': sha256(root/'selected.slp'),
        'source_video_similarity_accepted': False, 'original_inputs_identified': False,
        'full_state_equality_measured': False,
        'scope': 'requested playable interval; excludes Ready and does not supersede its retained strict audit failure',
        'identities': {str(p): sha256(p) for p in (Path(__file__), root/'search-result.json',
            root/'search-spec.json', root/'official/capture.json', out/'native-state.json',
            out/'official-state.json', root/'trials'/f"{search['selected_index']:03d}.json",
            Path('src/yt2slp/benchmark.py'), Path('tools/slippi-parser/export-state.cjs'))}}
    (out/'result.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
