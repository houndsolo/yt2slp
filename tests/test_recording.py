"""Synthetic transport validation, not simulation or Slippi format evidence."""
from pathlib import Path

import pytest

from yt2slp.backend import BackendError, NativeLinuxBackend, RecordingStatus, UnsupportedOperation


class Peer:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.sent = []
        self.closed = False

    def send(self, command):
        self.sent.append(command)

    def receive(self):
        return next(self.replies)

    def close(self):
        self.closed = True


def test_export_complete_transport_exclusive_output_and_no_resume(tmp_path):
    backend = NativeLinuxBackend()
    data = bytes(range(256)) * 9
    peer = Peer([f'REPLAY {len(data)}', *(data[i:i+1024].hex() for i in range(0,len(data),1024)), 'RECORDED'])
    backend._session = peer
    output = tmp_path / 'synthetic.bin'
    backend.record(output)
    assert output.read_bytes() == data
    assert peer.sent == ['record'] and not peer.closed
    with pytest.raises(BackendError, match='already exists'):
        backend.record(output)
    assert output.read_bytes() == data and peer.sent == ['record']
    assert list(tmp_path.iterdir()) == [output]


@pytest.mark.parametrize('replies', [
    ['wrong'], ['REPLAY 0'], ['REPLAY 999999999'], ['REPLAY -1'],
    ['REPLAY 2', 'ff'], ['REPLAY 1', 'ffff'], ['REPLAY 1', 'zz'],
    ['REPLAY 1', '0'], ['REPLAY 1', 'ff', 'bad terminator'],
])
def test_invalid_export_never_publishes(tmp_path, replies):
    # Pad the short-data case with an invalid terminator, as a truncated peer would fail.
    peer = Peer([*replies, 'truncated'])
    backend = NativeLinuxBackend()
    backend._session = peer
    backend.last_run_dir = tmp_path
    with pytest.raises(BackendError, match='native control failed'):
        backend.record(tmp_path / 'never.bin')
    assert not list(tmp_path.iterdir()) and peer.closed
    assert backend._session is None


def test_unavailable_recorder_keeps_session_and_creates_no_file(tmp_path):
    backend = NativeLinuxBackend()
    peer = Peer(['UNSUPPORTED no game events'])
    backend._session = peer
    with pytest.raises(UnsupportedOperation, match='no game events'):
        backend.record(tmp_path / 'never.bin')
    assert not peer.closed and not list(tmp_path.iterdir())


def test_publish_failure_removes_temporary_file_and_keeps_session(tmp_path, monkeypatch):
    import yt2slp.backend as module
    backend = NativeLinuxBackend()
    peer = Peer(['REPLAY 1', 'ab', 'RECORDED'])
    backend._session = peer
    def fail(*args):
        raise OSError('disk publication failed')
    monkeypatch.setattr(module.os, 'link', fail)
    with pytest.raises(BackendError, match='cannot write replay'):
        backend.record(tmp_path / 'never.bin')
    assert not peer.closed and not list(tmp_path.iterdir())


@pytest.mark.parametrize('reply, expected', [
    ('RECORDING -123 0', RecordingStatus(-123, False)),
    ('RECORDING 7200 1', RecordingStatus(7200, True)),
])
def test_recording_status_does_not_resume_or_export(reply, expected):
    backend = NativeLinuxBackend()
    peer = Peer([reply])
    backend._session = peer
    assert backend.recording_status() == expected
    assert peer.sent == ['record-status'] and not peer.closed


@pytest.mark.parametrize('reply', [
    'wrong', 'RECORDING 7200 2', 'RECORDING -124 0',
    'RECORDING 2147483648 1', 'RECORDING 1 0 extra',
])
def test_invalid_status_closes_session(reply, tmp_path):
    backend = NativeLinuxBackend()
    peer = Peer([reply])
    backend._session = peer
    backend.last_run_dir = tmp_path
    with pytest.raises(BackendError, match='native control failed'):
        backend.recording_status()
    assert peer.closed and not list(tmp_path.iterdir())


def test_unavailable_recording_status_is_explicit():
    backend = NativeLinuxBackend()
    with pytest.raises(UnsupportedOperation, match='live control session'):
        backend.recording_status()
    peer = Peer(['UNSUPPORTED no recording status provider'])
    backend._session = peer
    with pytest.raises(UnsupportedOperation, match='no recording status provider'):
        backend.recording_status()
    assert not peer.closed
