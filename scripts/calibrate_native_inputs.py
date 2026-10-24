"""Measure native request/replay phase and scalar PAD response using real games.

Known controls are calibration oracles, never a blind reconstruction result.
Run in GCC 14 Docker with the user's ISO; all artifacts remain local/ignored.
"""
import argparse
from dataclasses import asdict,replace
import json
import os
from pathlib import Path
import subprocess

from yt2slp.backend import NativeLinuxBackend,RunConfig
from yt2slp.match import MatchConfig,PadInput
from yt2slp.pad_adapter import BUTTON_BITS,BUTTON_MASK,AXIS_FIELDS,infer_lag,axis_bin,decode_controlled_row
from yt2slp.video import sha256
from measure_fox_jumps import jump_metrics


def neutral(): return PadInput()


def case_pads(case,index):
    if case['kind']=='clock':
        buttons=(0,256,0,1024,1024,0,512,0,2048,0,0,256)
        values=(0,80,0,0,-80,0,80,80,0,-80,0,0)
        return tuple(PadInput(button=buttons[(index-6+slot*3)%12],stick_x=values[(index-6+slot*5)%12])
            if 6<=index<30 else neutral() for slot in (0,1))
    if case['kind']=='hop':
        return (PadInput(button=1024 if 6<=index<6+case['held'] else 0),neutral())
    value = case['raw'] if 6<=index<12 else 0
    return (PadInput(**{case['field']:value}),)*2


def run_case(backend,case,folder,ports):
    folder.mkdir(); requests=[]; observations=[backend.observe()]
    for index in range(case['steps']):
        active = case_pads(case,index); pads = [PadInput(err=-1) for _ in range(4)]
        for port,pad in zip(ports,active): pads[port]=pad
        before = backend.recording_status().last_frame; observation = backend.step(tuple(pads))
        after = backend.recording_status().last_frame
        if after!=before+1: raise ValueError('calibration requires one signed replay key per VI')
        requests.append({'boundary_frame':before,'after_frame':after,'pads':[asdict(p) for p in active]})
        observations.append(observation)
    backend.record(folder/'native.slp')
    (folder/'requests.json').write_text(json.dumps(requests,indent=2)+'\n')
    result = {**case,'replay':str((folder/'native.slp').name),'first':requests[0]['boundary_frame'],
        'last':requests[-1]['after_frame'],'requests':requests,'ports':list(ports)}
    if case['kind']=='hop': result['jump']=jump_metrics(observations)
    return result


def clock_lags(case,labels):
    def physical(row):return row['physical']['values']['buttons'] if row['physical']['mask']['buttons'] else None
    channels = {
        'physical_buttons':(physical,lambda p:p['button']),
        'effective_buttons':(lambda r:r['effective']['values']['buttons'] & BUTTON_MASK,lambda p:p['button']),
        'raw_stick_x':(lambda r:r['physical']['values']['raw_stick_x'],lambda p:p['stick_x']),
        'stick_x':(lambda r:r['effective']['values']['stick_x'],lambda p:p['stick_x']/80),
    }
    return {name:infer_lag(case['requests'],labels['rows'],case['ports'],actual,wanted)
        for name,(actual,wanted) in channels.items()}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    iso=Path(os.environ.get('YT2SLP_ISO','/assets/melee.iso'))
    config=RunConfig(Path('build/headless/melee_headless'),Path('build/game/melee_game.so'),iso,Path('.local/runs'),match=MatchConfig())
    boot=Path('third_party/melee-unlocked/port/scripts/native_vs.txt')
    levels=sorted(set(range(-80,81,10))|{-128,-127,-100,-81,-79,-25,-24,-23,-16,-15,-8,-1,1,8,15,16,23,24,25,79,81,100,127})
    triggers=sorted({0,1,15,29,30,31,41,42,43,44,60,80,100,128,139,140,141,180,200,255}
        | {round(140*i/16) for i in range(17)})
    cases=[{'name':'clock','kind':'clock','steps':40}]
    for field in ('stick_x','stick_y','sub_x','sub_y'):
        cases += [{'name':f'{field}-{value:+04d}','kind':'axis','field':field,'raw':value,'steps':20} for value in levels]
    for field in ('trigger_l','trigger_r'):
        cases += [{'name':f'{field}-{value:03d}','kind':'axis','field':field,'raw':value,'steps':20} for value in triggers]
    cases += [{'name':f'button-{bit:04x}','kind':'button','field':'button','raw':bit,'steps':20} for bit in BUTTON_BITS]
    cases += [{'name':f'hop-{held}','kind':'hop','held':held,'steps':100} for held in (1,2,3)]
    probes=[]
    try:
        with NativeLinuxBackend() as backend:
            backend.initialize(config);backend.start(boot,timeout=180)
            while backend.recording_status().last_frame<239: backend.step(config.match.neutral_pads())
            checkpoint=backend.capture(); initial=backend.observe()
            for number,case in enumerate(cases):
                backend.restore(checkpoint)
                if backend.observe()!=initial: raise ValueError('restored calibration start differs')
                folder=out/case['name'];result=run_case(backend,case,folder,config.match.ports)
                result['replay']=str((folder/'native.slp').relative_to(out));probes.append(result)
                if number%25==0:print(f'Generated {number+1}/{len(cases)} real probe recordings',flush=True)
            backend.restore(checkpoint); repeat=run_case(backend,cases[0],out/'repeat-clock',config.match.ports)
            if sha256(out/'clock/native.slp')!=sha256(out/'repeat-clock/native.slp'):
                raise ValueError('discarded probe branches changed the original recording')
        alternate=replace(config,match=replace(config.match,ports=(1,3)))
        with NativeLinuxBackend() as backend:
            backend.initialize(alternate);backend.start(boot,timeout=180)
            while backend.recording_status().last_frame<239:backend.step(alternate.match.neutral_pads())
            case={**cases[0],'name':'clock-ports-1-3'}
            result=run_case(backend,case,out/case['name'],alternate.match.ports)
            result['replay']=str((out/case['name']/'native.slp').relative_to(out));probes.append(result)
        with NativeLinuxBackend() as backend:
            backend.initialize(config);backend.start(boot,timeout=180,include_preroll=True)
            while backend.recording_status().last_frame < -40:backend.step(config.match.neutral_pads())
            case={**cases[0],'name':'clock-preroll'}
            result=run_case(backend,case,out/case['name'],config.match.ports)
            result['replay']=str((out/case['name']/'native.slp').relative_to(out));probes.append(result)
        manifest={'schema':1,'kind':'native-pad-probe-manifest','probes':probes}
        (out/'probes.json').write_text(json.dumps(manifest)+'\n')
        with (out/'labels.json').open('x') as handle:
            subprocess.run(['node','tools/slippi-parser/export-control-probes.cjs',str(out/'probes.json')],stdout=handle,check=True)
        labels=json.loads((out/'labels.json').read_text())['probes']; lags=clock_lags(probes[0],labels['clock'])
        for probe in probes:
            if probe['name'] not in ('clock-ports-1-3','clock-preroll'):continue
            lags.update({probe['name']+'.'+name:value for name,value in clock_lags(probe,labels[probe['name']]).items()})
        for probe in probes:
            if probe['kind']!='axis' or probe['raw']!=(255 if probe['field'].startswith('trigger') else 80):continue
            axis={'sub_x':'cstick_x','sub_y':'cstick_y'}.get(probe['field'],probe['field'])
            field='trigger' if axis.startswith('trigger') else axis
            actual=lambda r,name=field:bool(r['effective']['values'][name])
            expected=lambda p,name=probe['field']:bool(p[name])
            lags[axis]=infer_lag(probe['requests'],labels[probe['name']]['rows'],probe['ports'],actual,expected)
            if axis.startswith('trigger'):
                physical='trigger_l' if axis=='trigger_l' else 'trigger_r'
                lags['physical_'+physical]=infer_lag(probe['requests'],labels[probe['name']]['rows'],probe['ports'],
                    lambda r,name=physical:bool(r['physical']['values'][name]),expected)
        offsets={r['boundary_to_replay_lag'] for r in lags.values()}
        if len(offsets)!=1:raise ValueError('measured channels have different lag; no universal offset assumed')
        lag=next(iter(offsets));samples=[];button_effects=[]
        for probe in probes[1:]:
            rows={(r['frame'],r['port']):r for r in labels[probe['name']]['rows']}
            first=probe['first']
            if probe['kind']=='axis':
                field=probe['field'];axis={'sub_x':'cstick_x','sub_y':'cstick_y'}.get(field,field)
                name='trigger' if axis.startswith('trigger') else axis
                values=[rows[first+i+lag,p]['effective']['values'][name] for i in (8,9,10) for p in probe['ports']]
                if any(v is None for v in values) or len(set(values))!=1:raise ValueError('axis response is unknown/unstable or differs by port')
                samples.append({'axis':axis,'raw':probe['raw'],'effective':values[0],'probe':probe['name']})
            if probe['kind']=='button':
                for request in probe['requests']:
                    frame=request['boundary_frame']+lag
                    if frame>probe['last']:continue
                    for slot,port in enumerate(probe['ports']):
                        if rows[frame,port]['physical']['values']['buttons']!=request['pads'][slot]['button']:
                            raise ValueError('physical button stream differs from request at measured lag')
                values=[rows[first+i+lag,p]['effective']['values'] for i in (8,9,10) for p in probe['ports']]
                signatures={(v['buttons'],v['trigger']) for v in values}
                if len(signatures)!=1:raise ValueError('button effect differs within steady sample or by port')
                held,trigger=next(iter(signatures))
                button_effects.append({'physical_button':probe['raw'],'effective_buttons':held,'effective_trigger':trigger})
        profile={'schema':1,'kind':'measured-native-pad-profile','passed':True,'request_boundary_to_replay_lag':lag,
            'lags':lags,'axis_samples':samples,'button_effects':button_effects,'ports':list(config.match.ports),'match':asdict(config.match),
            'timing_ports_tested':[[0,1],[1,3]],
            'timing_intervals_tested':{'positive_boundary':239,'playable_preroll_boundary':-40},
            'scope':'ordinary positive VS and playable Go preroll; Fox/Falco Battlefield; no hitlag/respawn/pause/code-set generalization',
            'unsupported':['Start/pause','simultaneous diagonal composition','digital shoulder/analog composition','source UCF parity','learned proposals'],
            'identities':{name:sha256(path) for name,path in (('host',config.host),('game',config.game_library),('iso',iso),('boot',boot),
                ('script',Path(__file__)),('adapter',Path('src/yt2slp/pad_adapter.py')),('parser',Path('tools/slippi-parser/export-control-probes.cjs')))}}
        profile['bin_coverage']={axis:{str(i):any(s['axis']==axis and axis_bin(axis,s['effective'])==i for s in samples)
            for i in range(17)} for axis in AXIS_FIELDS}
        (out/'profile.json').write_text(json.dumps(profile,indent=2)+'\n')
        roundtrips=[]
        for source in (p for p in probes if p['name'] in ('clock','clock-preroll') or p['kind']=='hop'):
            keyed={(r['frame'],r['port']):r for r in labels[source['name']]['rows']}
            with NativeLinuxBackend() as backend:
                backend.initialize(config);backend.start(boot,timeout=180,include_preroll=source['first']<0)
                while backend.recording_status().last_frame<source['first']:backend.step(config.match.neutral_pads())
                for request in source['requests']:
                    pads=list(config.match.neutral_pads());frame=request['boundary_frame']+lag
                    for port in source['ports']:
                        # Two explicit neutral drain requests at the controlled source tail;
                        # missing real/model controls are never generally filled this way.
                        pads[port]=decode_controlled_row(profile,keyed[frame,port]) if frame<=source['last'] else neutral()
                    backend.step(tuple(pads))
                target=out/f'roundtrip-{source["name"]}.slp';backend.record(target)
            same=sha256(target)==sha256(out/source['replay'])
            roundtrips.append({'source':source['name'],'replay':target.name,'byte_identical':same})
            if not same:raise ValueError('known-input replay-control -> PAD roundtrip differs')
        report={'schema':1,'kind':'native-pad-calibration-result','passed':True,'probes':len(probes),
            'profile_sha256':sha256(out/'profile.json'),'checkpoint_branch_recording_matches':True,
            'roundtrips':roundtrips,'hop_metrics':[p['jump'] for p in probes if p['kind']=='hop'],
            'official_playback_validated':False,'model_inputs_used':False,'training_modified':False}
        (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(out/'result.json',flush=True)
    except Exception as error:
        (out/'failure.json').write_text(json.dumps({'passed':False,'error':str(error),'completed_probes':len(probes)},indent=2)+'\n');raise


if __name__=='__main__':main()
