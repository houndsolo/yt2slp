"""Create a declared controlled source case in Docker: Fox/Falco, Battlefield.

The default preserves the original right-moving case. The second source moves
left later. Source controllers are never read by reconstruction/refinement.
No checkpoints/pauses in gameplay time, no Start inputs.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import subprocess

from yt2slp.backend import NativeLinuxBackend, RunConfig
from yt2slp.match import MatchConfig
from yt2slp.reference_cases import REFERENCE_CASES


def sha256(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', choices=REFERENCE_CASES, default='fox-falco-battlefield-horizontal-v1')
    args = parser.parse_args()
    case = REFERENCE_CASES[args.case]
    iso = Path(os.environ.get('YT2SLP_ISO', '/assets/melee.iso'))
    with NativeLinuxBackend() as b:
        b.initialize(RunConfig(Path('build/headless/melee_headless'), Path('build/game/melee_game.so'),
                               iso, Path('.local/runs'), match=MatchConfig()))
        observations = [b.start(Path('third_party/melee-unlocked/port/scripts/native_vs.txt'), timeout=180)]
        for i in range(case.total_steps):
            observations.append(b.step(case.pads(i)))
            if b.recording_status().last_frame != observations[-1].match_frame:
                raise RuntimeError('native observation and replay counters disagree; no frame offset will be guessed')
        directory = b.last_run_dir
        replay = directory / 'native.slp'
        b.record(replay)
        (directory / 'observations.json').write_text(json.dumps([asdict(o) for o in observations])+'\n')
        config = b.config
        manifest = {'schema': 1, 'case': args.case,
            'clip': {'first':240,'last':300,'fps':60,'timer_pauses_allowed':False},
            'native_observation_frames':[o.match_frame for o in observations],
            'input_policy':case.input_policy,
            'seed':config.rng_seed,'time_base':config.time_base,'requested_match':asdict(config.match),
            'identities':{str(p):sha256(p) for p in [config.host,config.game_library,iso,Path('uv.lock'),Path(__file__),Path('src/yt2slp/reference_cases.py')]},
            'replay_sha256':sha256(replay),
            'git_head':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
            'engine_head':subprocess.check_output(['git','-C','third_party/melee-unlocked','rev-parse','HEAD'],text=True).strip(),
            'native_recording_status':asdict(b.recording_status()),
            'alignment':'native match counter equals recording last post-frame at every step; no fitted shift',
            'state_policy':'bit-exact integers and float32 words for declared fields; no ULP exceptions',
            'reconstruction_quality_thresholds_established':False}
        (directory / 'benchmark.json').write_text(json.dumps(manifest,indent=2)+'\n')
        print(directory)


if __name__ == '__main__':
    main()
