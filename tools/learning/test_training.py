"""Optional CPU tensor tests of resume, checkpoint safety and split boundaries.

Synthetic feature/target tensors are test data, not replay files or gameplay.
"""
from copy import deepcopy
import json
from pathlib import Path
import signal
import tempfile
import unittest
from unittest.mock import patch

import torch
from baseline import AXES, targets_for_frames
import manage
import train
from runtime_files import atomic_json, digest, read_json
from stream_data import WindowStore


class TrainingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(); self.root = Path(self.temporary.name)
        self.original_signals = {sig:signal.getsignal(sig) for sig in (signal.SIGTERM,signal.SIGINT)}
        self.patches = [patch.object(train,'ROOT',self.root),patch.object(manage,'ROOT',self.root)]
        for item in self.patches: item.start()
        self.config = json.loads((Path(__file__).resolve().parents[2]/'configs/vision-v100.json').read_text())
        self.config.update(data_directory='data',batch_size=2,hidden_size=16,context_frames=3,
            max_steps=12,checkpoint_every=2,evaluate_every=4,log_every=100,threads=1)
        folder = self.root/'data'; folder.mkdir(); shards = []
        for clip,split in enumerate(('train','train','validation')):
            features = torch.randn(7,3072,generator=torch.Generator().manual_seed(clip+42))
            frames = []
            for f in range(7):
                rows = []
                for p in range(2):
                    buttons = 1024 if (f+p)%2 else 0
                    rows.append({'physical':{'values':{'buttons':buttons},'mask':{'buttons':True}},
                        'physical_edges':{'pressed':buttons,'released':1024^buttons,'mask':True},
                        'effective':{'values':dict.fromkeys(AXES,0.),'mask':dict.fromkeys(AXES,True)},
                        'state':{'values':{'action':24+f%2,'airborne':bool(f%2)},'mask':{'action':True,'airborne':True}}})
                frames.append({'targets':rows})
            payload = folder/f'{clip}.pt'; replay = str(clip)*64
            torch.save({'features':features,'targets':targets_for_frames(frames),'replay_sha256':replay},payload)
            shards.append({'payload':payload.name,'payload_sha256':digest(payload),'replay_sha256':replay,
                'frames':7,'windows':5,'context_frames':3,'feature_size':3072,'group':f'day-{clip}','split':split})
        self.manifest = folder/'dataset.json'
        members = [{'replay_sha256':s['replay_sha256'],'split':s['split'],'group':s['group']} for s in shards]
        atomic_json(folder/'plan.json',{'schema':1,'matches':members})
        atomic_json(folder/'selection.json',{'matches':members})
        atomic_json(self.manifest,{'schema':1,'kind':'vision-feature-dataset','context_frames':3,
            'slot_characters':[2,20],'stage':31,'shards':shards,'split_plan':'plan.json',
            'selection':'selection.json','split_plan_sha256':digest(folder/'plan.json'),
            'selection_sha256':digest(folder/'selection.json')})

    def tearDown(self):
        for sig,handler in self.original_signals.items(): signal.signal(sig,handler)
        for item in self.patches: item.stop()
        self.temporary.cleanup()

    def checkpoint(self,run):
        pointer = read_json(run/'latest.json')
        return torch.load(run/pointer['file'],map_location='cpu',weights_only=True)

    def assert_tree_equal(self,left,right):
        if isinstance(left,torch.Tensor): torch.testing.assert_close(left,right,rtol=0,atol=0)
        elif isinstance(left,dict):
            self.assertEqual(left.keys(),right.keys())
            for key in left: self.assert_tree_equal(left[key],right[key])
        elif isinstance(left,(list,tuple)):
            self.assertEqual(len(left),len(right))
            for a,b in zip(left,right): self.assert_tree_equal(a,b)
        else: self.assertEqual(left,right)

    def test_resumed_optimizer_and_rng_match_uninterrupted_cpu_training(self):
        whole,split = self.root/'whole',self.root/'split'
        train.train(self.config,whole,'cpu',12)
        train.train(self.config,split,'cpu',6)
        train.train(self.config,split,'cpu',12)
        a,b = self.checkpoint(whole),self.checkpoint(split)
        for key in ('model','optimizer','sampler_rng','torch_rng','validation','best_score'):
            self.assert_tree_equal(a[key],b[key])
        self.assertEqual(read_json(split/'status.json')['state'],'completed')

    def test_pause_saves_before_exit_and_resume_continues(self):
        run = self.root/'pause'; atomic_json(run/'control.json',{'command':'pause'})
        train.train(self.config,run,'cpu',3)
        self.assertEqual(read_json(run/'status.json')['state'],'paused')
        self.assertEqual(self.checkpoint(run)['step'],0)
        atomic_json(run/'control.json',{'command':'run'})
        train.train(self.config,run,'cpu',3)
        self.assertEqual(self.checkpoint(run)['step'],3)
        atomic_json(run/'control.json',{'command':'stop'})
        train.train(self.config,run,'cpu',6)
        self.assertEqual(read_json(run/'status.json')['state'],'stopped')
        self.assertEqual(self.checkpoint(run)['step'],3)

    def test_checkpoint_write_failure_leaves_committed_pointer_intact(self):
        run = self.root/'safe'; train.train(self.config,run,'cpu',2)
        before = read_json(run/'latest.json')
        with patch.object(torch,'save',side_effect=OSError('simulated full disk')):
            with self.assertRaises(OSError): train.save_checkpoint(run,self.checkpoint(run))
        self.assertEqual(read_json(run/'latest.json'),before)
        self.assertEqual(self.checkpoint(run)['step'],2)

    def test_resume_rejects_changed_hyperparameters_and_damaged_checkpoints(self):
        run = self.root/'identity'; train.train(self.config,run,'cpu',2)
        changed = {**self.config,'learning_rate':.002}
        with self.assertRaisesRegex(ValueError,'changed'): train.train(changed,run,'cpu',3)
        pointer = read_json(run/'latest.json'); (run/pointer['file']).write_bytes(b'damaged checkpoint fixture')
        with self.assertRaisesRegex(ValueError,'checksum'): train.load_checkpoint(run,train.contract(self.config,self.manifest,'cpu'))

    def test_lazy_windows_cross_clip_boundaries_without_crossing_match_history(self):
        store = WindowStore(self.manifest,'train',resident_clips=1)
        features,targets = store.batch([4,5,1,8])
        first = torch.load(self.root/'data/0.pt',weights_only=True)
        second = torch.load(self.root/'data/1.pt',weights_only=True)
        torch.testing.assert_close(features[0],first['features'][4:7])
        torch.testing.assert_close(features[1],second['features'][0:3])
        torch.testing.assert_close(features[2],first['features'][1:4])
        torch.testing.assert_close(features[3],second['features'][3:6])
        torch.testing.assert_close(targets['buttons'][1],second['targets']['buttons'][1])
        self.assertEqual(len(store.cache),1)

    def test_dataset_refuses_leakage_and_content_changes(self):
        original = read_json(self.manifest)
        for change in ('test','group','duplicate'):
            doc = deepcopy(original)
            if change=='test': doc['shards'][2]['split']='test'
            if change=='group': doc['shards'][2]['group']=doc['shards'][0]['group']
            if change=='duplicate': doc['shards'][2]['replay_sha256']=doc['shards'][0]['replay_sha256']
            atomic_json(self.manifest,doc)
            with self.assertRaises(ValueError): WindowStore(self.manifest,'train')
        atomic_json(self.manifest,original); (self.root/'data/0.pt').write_bytes(b'changed feature fixture')
        with self.assertRaisesRegex(ValueError,'identity'): WindowStore(self.manifest,'train')


if __name__ == '__main__': unittest.main()
