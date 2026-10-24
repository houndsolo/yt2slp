"""Literal HUD evidence stays distinct from automatic recognition and frame IDs."""
import hashlib

import pytest

from yt2slp.timer_labels import add_manual_readings


def fixture(tmp_path,monkeypatch):
    # Bytes exercise the identity binding; no game image is synthesized.
    image=tmp_path/'unknown.png';image.write_bytes(b'identity fixture')
    monkeypatch.setattr('yt2slp.timer_labels.png_size',lambda p:[642,528])
    labels={'interval':[2400,2400],'method':'automatic HUD recognition',
        'records':[{'image':image.name,'timer_digits':None,'frame':None}],
        'missing_frames':[2400],'duplicate_frames':[],'chronological':True,'passed':False}
    readings={'schema':1,'kind':'manual-rendered-timer-readings','readings':[
        {'image':image.name,'image_sha256':hashlib.sha256(image.read_bytes()).hexdigest(),
         'timer':'07:20.00','note':'Literal visual reading of the retained image.'}]}
    return labels,readings,{'2400':'07:20.00'}


def test_literal_reading_fills_unknown_and_preserves_automatic_failure(tmp_path,monkeypatch):
    labels,readings,timers=fixture(tmp_path,monkeypatch)
    result=add_manual_readings(labels,readings,tmp_path,timers)
    assert result['passed'] and result['selected']=={2400:'unknown.png'}
    assert not result['automatic_summary']['passed'] and result['manual_reading_count']==1
    assert labels['records'][0]['frame'] is None


def test_changed_image_or_recognized_evidence_cannot_be_overridden(tmp_path,monkeypatch):
    labels,readings,timers=fixture(tmp_path,monkeypatch)
    labels['records'][0].update(timer_digits='072000',frame=2400)
    with pytest.raises(ValueError,match='override'):add_manual_readings(labels,readings,tmp_path,timers)
    labels['records'][0].update(timer_digits=None,frame=None)
    (tmp_path/'unknown.png').write_bytes(b'changed fixture')
    with pytest.raises(ValueError,match='unbound'):add_manual_readings(labels,readings,tmp_path,timers)


def test_reading_cannot_invent_an_out_of_lookup_timer(tmp_path,monkeypatch):
    labels,readings,timers=fixture(tmp_path,monkeypatch)
    readings['readings'][0]['timer']='00:00.00'
    with pytest.raises(ValueError,match='outside'):add_manual_readings(labels,readings,tmp_path,timers)
