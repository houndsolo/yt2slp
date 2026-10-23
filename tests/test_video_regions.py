"""Explicit video selection/cropping; synthetic pixels and real FFmpeg only."""
import subprocess

import pytest

from yt2slp.render_evidence import crop_rgb, decode_rgb
from yt2slp.video import ingest_video


@pytest.fixture
def source(tmp_path):
    path=tmp_path/'synthetic.mp4'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc=size=24x16:rate=30',
        '-frames:v','5','-pix_fmt','yuv420p','-c:v','libx264',str(path)],check=True)
    return path


def test_odd_crop_and_decode_selection_keep_exact_pixels_and_original_timestamps(source,tmp_path):
    original=ingest_video(source,tmp_path/'original')
    selected=ingest_video(source,tmp_path/'selected',3,decode_interval=(1,3),crop=(1,3,11,7))
    assert [selected['width'],selected['height']]==[11,7]
    assert selected['source_sha256']==original['source_sha256']
    assert selected['gameplay_crop']==[1,3,11,7]
    assert selected['source_view']['original_geometry']==[24,16]
    assert selected['source_view']['decode_interval']==[1,3]
    assert selected['game_frame_alignment'] is None
    for i,row in enumerate(selected['frames']):
        parent=original['frames'][i+1]
        assert row['source_decode_index']==i+1 and row['index']==i
        assert [row[k] for k in ('pts','time_seconds','relative_seconds')]==[parent[k] for k in ('pts','time_seconds','relative_seconds')]
        full=decode_rgb(tmp_path/'original'/parent['image'],24,16)
        actual=decode_rgb(tmp_path/'selected'/row['image'],11,7)
        assert actual==crop_rgb(full,24,16,(1,3,11,7))
    assert selected['frames'][0]['relative_seconds']=='1/30'
    assert not selected['frames'][0]['identical_previous_decoded_png']


def test_region_selection_preserves_a_real_missing_video_frame(tmp_path):
    path=tmp_path/'variable.mp4'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc=size=24x16:rate=30',
        '-vf',"select='not(eq(n,2))'",'-fps_mode','vfr','-frames:v','4',
        '-c:v','libx264',str(path)],check=True)
    result=ingest_video(path,tmp_path/'selected',3,decode_interval=(1,3),crop=(1,1,11,7))
    assert [r['relative_seconds'] for r in result['frames']]==['1/30','1/10','2/15']
    assert result['variable_timestamp_spacing']
    assert not result['dropped_game_frames_assessed']


@pytest.mark.parametrize('interval,crop,limit',[
    ((-1,2),None,5),((1,5),None,5),((3,2),None,5),((True,2),None,5),
    ((1,3),None,2),((0,2),(-1,0,4,4),5),((0,2),(0,0,25,16),5),
    ((0,2),(0,0,0,4),5),((0,2),(False,0,4,4),5),((0,2),(0,0,4),5),
])
def test_invalid_region_fails_before_creating_outputs(source,tmp_path,interval,crop,limit):
    output=tmp_path/'rejected'
    with pytest.raises(ValueError):ingest_video(source,output,limit,decode_interval=interval,crop=crop)
    assert not output.exists()
