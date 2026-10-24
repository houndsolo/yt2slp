"""Tensor fixtures verify corpus boundaries and durable resume, not gameplay."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import signal
import tempfile
import unittest
from unittest.mock import patch

import torch
from baseline import AXES, targets_for_frames
from corpus_data import CorpusStore
import manage
from runtime_files import atomic_json, digest, read_json
import train_corpus


class CorpusTrainingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
        self.signals={s:signal.getsignal(s) for s in (signal.SIGTERM,signal.SIGINT)}
        self.patches=[patch.object(train_corpus,'ROOT',self.root),patch.object(manage,'ROOT',self.root)]
        for p in self.patches:p.start()
        original=Path(__file__).resolve().parents[2]
        code=self.root/'src/yt2slp';code.mkdir(parents=True);shutil.copy2(original/'src/yt2slp/corpus.py',code/'corpus.py')
        self.config=read_json(original/'configs/vision-v100-corpus.json')
        self.config.update(data_directory='data',run_directory='run',threads=1,context_frames=3,hidden_size=16,
            batch_size=2,evaluate_every=4,checkpoint_every=2,log_every=100,max_steps=8)
        data=self.root/'data';data.mkdir();shards=[];matches=[];selected=[]
        for source,split in enumerate(('train','validation')):
            replay=str(source)*64
            players=[{'port':1,'character':2,'costume':0},{'port':3,'character':2 if source==0 else 20,'costume':1}]
            match={'replay_sha256':replay,'group':f'date-{source}','split':split,'stage':31,'players':players,'clips':[]}
            for number in range(2):
                first=1+number*20;clip={'clip_id':f'{replay}-{first}-{first+6}','interval':[first,first+6]}
                match['clips'].append(clip);selected.append({**clip,'replay_sha256':replay,'split':split,'group':match['group']})
                frames=[]
                for frame in range(7):
                    targets=[]
                    for p in range(2):
                        bit=1024 if (frame+p)%2 else 0
                        targets.append({'physical':{'values':{'buttons':bit},'mask':{'buttons':True}},
                            'physical_edges':{'pressed':bit,'released':1024^bit,'mask':True},
                            'effective':{'values':dict.fromkeys(AXES,0.),'mask':dict.fromkeys(AXES,True)},
                            'state':{'values':{'action':24,'airborne':bool(frame%2)},'mask':{'action':True,'airborne':True}}})
                    frames.append({'targets':targets})
                payload=data/f'{source}-{number}.pt'
                features=torch.randn(7,3072,generator=torch.Generator().manual_seed(source*10+number))
                torch.save({'features':features,'targets':targets_for_frames(frames),'replay_sha256':replay},payload)
                shards.append({**selected[-1],'frames':7,'first_frame':first,'windows':5,'context_frames':3,
                    'feature_size':3072,'payload':payload.name,'payload_sha256':digest(payload),
                    'slot_ports':[1,3],'slot_characters':[p['character'] for p in players]})
            matches.append(match)
        atomic_json(data/'plan.json',{'schema':1,'matches':matches})
        atomic_json(data/'selection.json',{'clips':selected})
        self.manifest=data/'dataset.json'
        atomic_json(self.manifest,{'schema':1,'kind':'vision-corpus-feature-dataset','stage':31,
            'slot_mapping':'ascending-physical-ports','context_frames':3,'split_plan':'plan.json','selection':'selection.json',
            'split_plan_sha256':digest(data/'plan.json'),'selection_sha256':digest(data/'selection.json'),'shards':shards})

    def tearDown(self):
        for sig,handler in self.signals.items():signal.signal(sig,handler)
        for p in self.patches:p.stop()
        self.temp.cleanup()

    def payload(self,run):
        return torch.load(run/read_json(run/'latest.json')['file'],map_location='cpu',weights_only=True)

    def equal(self,a,b):
        if isinstance(a,torch.Tensor):torch.testing.assert_close(a,b,rtol=0,atol=0)
        elif isinstance(a,dict):
            self.assertEqual(a.keys(),b.keys())
            for key in a:self.equal(a[key],b[key])
        elif isinstance(a,(list,tuple)):
            self.assertEqual(len(a),len(b))
            for x,y in zip(a,b):self.equal(x,y)
        else:self.assertEqual(a,b)

    def test_multiple_clips_keep_gaps_out_of_windows_and_preserve_mirror_slots(self):
        store=CorpusStore(self.manifest,'train',resident_clips=1)
        features,targets=store.batch([4,5,0,9])
        a=torch.load(self.root/'data/0-0.pt',weights_only=True);b=torch.load(self.root/'data/0-1.pt',weights_only=True)
        torch.testing.assert_close(features[0],a['features'][4:7])
        torch.testing.assert_close(features[1],b['features'][:3])
        self.assertEqual(store.shards[0]['slot_ports'],[1,3]);self.assertEqual(store.shards[0]['slot_characters'],[2,2])

    def test_resumed_cpu_model_optimizer_and_rng_are_exact(self):
        whole=self.root/'whole';split=self.root/'split'
        train_corpus.train(self.config,whole,'cpu',8)
        train_corpus.train(self.config,split,'cpu',3);train_corpus.train(self.config,split,'cpu',8)
        a,b=self.payload(whole),self.payload(split)
        for key in ('model','optimizer','sampler_rng','torch_rng','validation','best_score'):self.equal(a[key],b[key])

    def test_pause_stop_and_contract_change_guards(self):
        run=self.root/'pause';atomic_json(run/'control.json',{'command':'pause'})
        train_corpus.train(self.config,run,'cpu',4)
        self.assertEqual(self.payload(run)['step'],0)
        self.assertEqual(read_json(run/'status.json')['state'],'paused')
        atomic_json(run/'control.json',{'command':'run'});train_corpus.train(self.config,run,'cpu',4)
        atomic_json(run/'control.json',{'command':'stop'});train_corpus.train(self.config,run,'cpu',8)
        self.assertEqual(self.payload(run)['step'],4)
        self.assertEqual(read_json(run/'status.json')['state'],'stopped')
        with self.assertRaisesRegex(ValueError,'changed'):
            train_corpus.train({**self.config,'batch_size':3},run,'cpu',8)

    def test_test_membership_and_changed_physical_slots_are_rejected(self):
        original=read_json(self.manifest)
        for change in ('test','ports','roster','duplicate'):
            doc=deepcopy(original)
            if change=='test':doc['shards'][0]['split']='test'
            if change=='ports':doc['shards'][0]['slot_ports']=[3,1]
            if change=='roster':doc['shards'][0]['slot_characters']=[2,20]
            if change=='duplicate':doc['shards'][1]['clip_id']=doc['shards'][0]['clip_id']
            atomic_json(self.manifest,doc)
            with self.assertRaises(ValueError):CorpusStore(self.manifest,'train')


if __name__=='__main__':unittest.main()
