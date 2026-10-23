"""Real FFmpeg synthetic frames; no game footage or fabricated replay files."""
from pathlib import Path
import subprocess

import pytest

from yt2slp.video import ingest_video, resize_view, sha256, window_view
from yt2slp.timer_labels import png_size


@pytest.fixture
def decoded(tmp_path):
    source=tmp_path/'synthetic.mp4'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=red:size=16x16:rate=30',
        '-frames:v','5','-c:v','libx264',str(source)],check=True)
    folder=tmp_path/'decoded'
    return folder,ingest_video(source,folder)


def test_window_views_preserve_source_pts_epoch_and_images(decoded,tmp_path):
    source,parent=decoded
    view=window_view(source,tmp_path/'view',2,4)
    assert view['source_sha256']==parent['source_sha256']
    assert view['view']['parent_video_json_sha256']==sha256(source/'video.json')
    for i,row in enumerate(view['frames']):
        original=parent['frames'][i+2]
        assert row['index']==i and row['source_decode_index']==i+2
        assert [row[k] for k in ('pts','time_seconds','relative_seconds','image_sha256')]==[original[k] for k in ('pts','time_seconds','relative_seconds','image_sha256')]
        assert (tmp_path/'view'/row['image']).is_symlink()
        assert sha256(tmp_path/'view'/row['image'])==row['image_sha256']
    assert view['frames'][0]['relative_seconds']=='1/15'
    assert not view['frames'][0]['identical_previous_decoded_png']
    with pytest.raises(FileExistsError):window_view(source,tmp_path/'view',2,4)


@pytest.mark.parametrize('first,last',[(-1,2),(2,5),(3,1),(True,2)])
def test_invalid_view_ranges_fail_before_creating_output(decoded,tmp_path,first,last):
    source,_=decoded
    with pytest.raises(ValueError):window_view(source,tmp_path/'view',first,last)
    assert not (tmp_path/'view').exists()


def test_view_refuses_corrupted_source_images(decoded,tmp_path):
    source,parent=decoded
    (source/parent['frames'][2]['image']).write_bytes(b'corrupted fixture')
    with pytest.raises(ValueError,match='identity'):window_view(source,tmp_path/'view',2,4)
    assert not (tmp_path/'view').exists()


def test_spatial_view_preserves_window_pts_and_source_identity(decoded, tmp_path):
    source, _ = decoded
    window = tmp_path/'window'
    parent = window_view(source, window, 2, 4)
    output = tmp_path/'resized'
    view = resize_view(window, output, 8, 12)
    assert (view['width'], view['height']) == (8, 12)
    assert view['source_sha256'] == parent['source_sha256']
    assert view['spatial_view']['parent_video_json_sha256'] == sha256(window/'video.json')
    assert view['spatial_view']['scale_xy'] == ['1/2', '3/4']
    assert view['frames'][0]['relative_seconds'] == '1/15'
    assert len(view['frames']) == 3
    for row, original in zip(view['frames'], parent['frames']):
        for key in ('index', 'pts', 'time_seconds', 'relative_seconds', 'source_decode_index'):
            assert row[key] == original[key]
        assert row['parent_image_sha256'] == original['image_sha256']
        assert png_size(output/row['image']) == [8, 12]
        assert sha256(output/row['image']) == row['image_sha256']
    assert [row['identical_previous_decoded_png'] for row in view['frames']] == [False, True, True]
    with pytest.raises(FileExistsError):resize_view(window, output, 8, 12)


@pytest.mark.parametrize('width,height', [(0, 8), (8, 4097), (True, 8)])
def test_invalid_spatial_view_fails_before_creating_output(decoded, tmp_path, width, height):
    source, _ = decoded
    with pytest.raises(ValueError):resize_view(source, tmp_path/'resized', width, height)
    assert not (tmp_path/'resized').exists()


def test_spatial_view_rejects_changed_source_pixels(decoded, tmp_path):
    source, parent = decoded
    (source/parent['frames'][0]['image']).write_bytes(b'changed')
    with pytest.raises(ValueError, match='identity'):resize_view(source, tmp_path/'resized', 8, 8)
    assert not (tmp_path/'resized').exists()
