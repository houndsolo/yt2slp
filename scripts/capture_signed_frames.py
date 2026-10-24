"""Audit signed-frame PNG labels using unmodified official Playback on X11.

Run under an isolated xvfb-run display on the host (Pillow, xdotool and
ImageMagick import required). Clean game dumps never contain the frame-index
OSD; separately retained UI screenshots verify every paused frame.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time

from PIL import Image, ImageGrab, features

from capture_benchmark import sha256
from yt2slp.frame_index import assess_step, cyan_cells, decode_index, complete_png_digest
from yt2slp.footage import capture_request_start


def current_frame(log):
    values = re.findall(r'^\[CURRENT_FRAME\] (-?\d+)$', log.read_text(errors='replace'), re.M)
    return int(values[-1]) if values else None


def dump_files(folder):
    files = sorted(folder.glob('framedump_*.png'), key=lambda p: int(p.stem.split('_')[-1]))
    if [int(p.stem.split('_')[-1]) for p in files] != list(range(1, len(files)+1)):
        raise ValueError('dump sequence has missing or duplicate files')
    return files


def press(key):
    subprocess.run(['xdotool', 'keydown', key], check=True)
    time.sleep(.045)
    subprocess.run(['xdotool', 'keyup', key], check=True)


def screenshot(path, full=False):
    # Preserve original screen coordinates but encode only the UI corner needed
    # for exact glyph verification. Full-screen PNG compression dominated remote
    # stepping; clean game dumps retain the whole gameplay image separately.
    if features.check_feature('xcb'):
        ImageGrab.grab(bbox=None if full else (0,0,182,35),xdisplay=os.environ.get('DISPLAY')).convert('RGB').save(path)
    else:
        crop = [] if full else ['-crop','182x35+0+0','+repage']
        subprocess.run(['import', '-window', 'root', *crop, str(path)], check=True, timeout=10)
    with Image.open(path) as image:
        image = image.convert('RGB')
        return cyan_cells(image.tobytes(), *image.size)


def wait_png(path,deadline):
    while time.monotonic()<deadline:
        value = complete_png_digest(path)
        if value is not None: return value
        time.sleep(.01)
    raise TimeoutError('frame dump did not finish writing its PNG IEND chunk')


def capture(args):
    request_start = capture_request_start(args.first, args.last)
    exe, iso, replay = (p.resolve() for p in (args.dolphin, args.iso, args.replay))
    version = subprocess.run([str(exe), '--version'], capture_output=True, text=True, timeout=20)
    if version.stdout.strip() != '3.5.2':
        raise ValueError('this pipeline audit supports official Playback 3.5.2 only')
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    user = out/'user'; dumps = user/'Dump/Frames'; screens = out/'screens'
    for path in (user/'Config', dumps, user/'GameSettings', screens): path.mkdir(parents=True)
    (user/'GameSettings/GALE01r2.ini').write_text(
        '[Gecko_Enabled]\n$Required: General Codes\n$Required: Slippi Playback\n$Recommended: Slippi Recording\n')
    (user/'Config/Dolphin.ini').write_text(
        '[Core]\nCPUThread = False\nDSPHLE = True\nGFXBackend = OGL\nEmulationSpeed = 0.5\n'
        'SlippiPlaybackDisplayFrameIndex = True\nSlippiRegenerateReplays = True\n'
        f'SlippiReplayRegenerateDir = {out/"regenerated"}\n'
        '[Interface]\nConfirmStop = False\nOnScreenDisplayMessages = True\n'
        '[Display]\nRenderWindowWidth = 642\nRenderWindowHeight = 528\n'
        'RenderWindowXPos = 0\nRenderWindowYPos = 0\n'
        '[Movie]\nDumpFrames = True\nDumpFramesSilent = True\n[DSP]\nBackend = No audio output\n')
    (user/'Config/GFX.ini').write_text(
        '[Hardware]\nVSync = False\n[Settings]\nDumpFramesAsImages = True\nEFBScale = 2\n'
        'AspectRatio = 3\nInternalResolutionFrameDumps = True\nShowFPS = False\n')
    request = out/'request.json'
    request.write_text(json.dumps({'mode': 'normal', 'replay': str(replay), 'commandId': 'yt2slp-signed-labels-v1',
        'startFrame': request_start, 'endFrame': args.last+3, 'shouldResync': False,
        'rollbackDisplayMethod': 'off'}, indent=2)+'\n')
    command = [str(exe), '--exec='+str(iso), '--slippi-input='+str(request), '--user='+str(user), '--batch', '--cout']
    log_path = out/'stdout.log'; steps = []; selected = []
    calibration = json.loads(args.osd_calibration.read_text()) if args.osd_calibration else None
    (out/'calibration-sources').mkdir()
    for i, source in enumerate(calibration['sources'] if calibration else []):
        original = args.osd_calibration.parent/source['image']
        if sha256(original) != source['sha256']: raise ValueError('calibration source identity differs')
        destination = out/'calibration-sources'/f'{i:06d}.png'
        shutil.copy2(original, destination)
        source['image'] = str(destination.relative_to(out))
    if calibration: (out/'osd-calibration.json').write_text(json.dumps(calibration, indent=2)+'\n')
    identities = {name: sha256(path) for name, path in (
        ('executable', exe), ('replay', replay), ('iso', iso), ('script', Path(__file__)),
        ('frame_index_code', Path('src/yt2slp/frame_index.py')))}
    if args.osd_calibration: identities['input_calibration'] = sha256(args.osd_calibration)
    wrapped = exe.parent/'AppRun.wrapped'
    if wrapped.is_file(): identities['wrapped_executable'] = sha256(wrapped.resolve())
    shutil.copy2(Path(__file__), out/'capture-used.py')
    shutil.copy2(Path('src/yt2slp/frame_index.py'), out/'frame-index-used.py')
    result = {'schema': 1, 'kind': 'official-stepped-frame-capture', 'capture_passed': False,
        'playback_version': '3.5.2', 'version_command_exit_code': version.returncode,
        'source_commit': 'bffe989d0bd3b83a4be3eaee708cf2755659e01e',
        'source_replay_sha256': sha256(replay), 'wanted_interval': [args.first, args.last],
        'ui_screenshot_region': 'full calibration screen' if args.collect_calibration else [0,0,182,35],
        'ui_screenshot_backend': 'Pillow XCB' if features.check_feature('xcb') else 'ImageMagick',
        'paused_log_association': 'per-step' if args.per_step_log_association else 'fixed',
        'png_completion_guard': 'IEND-before-hash-v1',
        'request_interval': [request_start, args.last+3], 'should_resync': False, 'command': command,
        'identities': identities,
        'image_post_phase_verified': False, 'positive_timer_crosscheck': None,
        'label_policy': 'paused single-VI advances; exact cyan OSD glyphs plus logged frame; clean PNG uses audited one-swap OGL PBO delay, requiring independent positive HUD crosscheck'}
    deadline = time.monotonic()+args.timeout
    with log_path.open('wb') as log:
        proc = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            while time.monotonic() < deadline:
                windows = subprocess.run(['xdotool', 'search', '--onlyvisible', '--pid', str(proc.pid)],
                    capture_output=True, text=True)
                if windows.returncode == 0:
                    subprocess.run(['xdotool', 'windowfocus', windows.stdout.splitlines()[-1]], check=True)
                frame = current_frame(log_path)
                if frame is not None and frame >= request_start+13:
                    press('F10'); break
                if proc.poll() is not None: raise RuntimeError(f'Playback exited during startup ({proc.returncode}); see stdout.log')
                time.sleep(.01)
            else:
                raise TimeoutError('startup exceeded capture budget')
            time.sleep(.15)
            before_log = current_frame(log_path)
            if before_log is None or before_log >= args.first-5:
                raise ValueError('startup pause left insufficient calibration/prefix frames')
            time.sleep(.08)
            if current_frame(log_path) != before_log: raise ValueError('Playback did not remain paused')
            previous_screen = screens/'000000.png'
            cells = screenshot(previous_screen, full=args.collect_calibration)
            if args.collect_calibration:
                # Console values are retained as separate metadata, never used
                # as literal UI labels. A visual annotation supplies those later.
                anchors = [{'image': str(previous_screen.relative_to(out)), 'console_frame': before_log,
                    'sha256': sha256(previous_screen)}]
                for i in range(12):
                    press('period'); time.sleep(.12)
                    screen = screens/f'{i+1:06d}.png'
                    screenshot(screen, full=True)
                    anchors.append({'image': str(screen.relative_to(out)), 'console_frame': current_frame(log_path),
                        'sha256': sha256(screen)})
                (out/'calibration-candidates.json').write_text(json.dumps({'schema': 1,
                    'frame_ids_verified': False, 'screens': anchors,
                    'policy': 'read literal cyan Frame text visually; console may be one frame ahead'}, indent=2)+'\n')
                result.update(kind='frame-index-calibration-capture', calibration_screens_collected=True)
                print(out/'calibration-candidates.json')
                return
            before = decode_index(cells, calibration)
            log_offset = before_log-before
            if log_offset not in (0, 1): raise ValueError('unsupported paused log/display clock association')
            result['startup_paused_log_minus_osd'] = log_offset
            selected_log_offset = None
            while before <= args.last:
                if time.monotonic() >= deadline: raise TimeoutError('signed capture exceeded budget')
                old = dump_files(dumps)
                press('period')
                wait_end = min(deadline, time.monotonic()+5)
                while time.monotonic() < wait_end:
                    after = current_frame(log_path); files = dump_files(dumps)
                    if after is not None and len(files) > len(old): break
                    if proc.poll() is not None: raise RuntimeError(f'Playback exited during frame step ({proc.returncode}); see stdout.log')
                    time.sleep(.01)
                time.sleep(.035)
                after = current_frame(log_path); files = dump_files(dumps)
                screen = screens/f'{len(steps)+1:06d}.png'
                cells = screenshot(screen)
                osd = decode_index(cells, calibration)
                log_offset = after-osd
                if log_offset not in (0, 1) or after-before_log not in (0, 1, 2):
                    raise ValueError('console counter incompatible with one displayed step')
                if current_frame(log_path) != after: raise ValueError('Playback advanced after released step key')
                old_names = {p.name for p in old}
                new = [p.name for p in files if p.name not in old_names]
                row = assess_step(before, osd, after, new, paused_log_minus_osd=log_offset)
                row.update(index_screen=str(previous_screen.relative_to(out)),
                    index_screen_sha256=sha256(previous_screen),
                    next_index_screen=str(screen.relative_to(out)), next_index_screen_sha256=sha256(screen),
                    capture_image_sha256=wait_png(dumps/row['capture_image'],min(deadline,time.monotonic()+5)), paused_log_minus_osd=log_offset)
                steps.append(row)
                if before >= args.first:
                    if selected_log_offset is None:
                        selected_log_offset = log_offset
                        result['paused_log_minus_osd'] = log_offset
                    if log_offset != selected_log_offset and not args.per_step_log_association:
                        raise ValueError('paused console/display association drifted inside wanted interval')
                    selected.append(row)
                    if len(selected) % 20 == 0: print(f'verified signed frame {before}', flush=True)
                before, before_log, previous_screen = osd, after, screen
            if [r['replay_frame'] for r in selected] != list(range(args.first, args.last+1)):
                raise ValueError('incomplete signed interval')
            paths = re.findall(r'^\[FILE_PATH\] (.+)$', log_path.read_text(errors='replace'), re.M)
            if not paths or any(path != str(replay) for path in paths): raise ValueError('Playback replay identity changed')
            result['capture_passed'] = True
            result['observed_paused_log_offsets'] = sorted({r['paused_log_minus_osd'] for r in selected})
        except Exception as error:
            result['error'] = str(error)
            raise
        finally:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGTERM)
                try: proc.wait(timeout=5)
                except subprocess.TimeoutExpired: os.killpg(proc.pid, signal.SIGKILL); proc.wait()
            result['regenerated_replays'] = [str(p.relative_to(out)) for p in sorted((out/'regenerated').glob('*.slp'))]
            result['process_exit_code'] = proc.returncode
            (out/'steps.json').write_text(json.dumps(steps, indent=2)+'\n')
            (out/'capture-index.json').write_text(json.dumps(selected, indent=2)+'\n')
            (out/'capture.json').write_text(json.dumps(result, indent=2)+'\n')
    print(out/'capture.json')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('dolphin', 'iso', 'replay', 'output'): parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--osd-calibration', type=Path)
    parser.add_argument('--collect-calibration', action='store_true', help='retain UI screenshots for literal visual annotation; does not label gameplay')
    parser.add_argument('--per-step-log-association', action='store_true',
        help='permit independently checked 0/1 console lead per step; exact UI+single-PNG progression remains required')
    parser.add_argument('--first', type=int, default=-60)
    parser.add_argument('--last', type=int, default=180)
    parser.add_argument('--timeout', type=float, default=300)
    args = parser.parse_args()
    if (args.osd_calibration is None) == (not args.collect_calibration):
        parser.error('choose an existing OSD calibration or --collect-calibration')
    try: capture_request_start(args.first, args.last)
    except ValueError as error: parser.error(str(error))
    if not 0 < args.timeout < 3600: parser.error('capture budget must be between 0 and 3600 seconds')
    for name in ('xdotool', 'import'):
        if not shutil.which(name): parser.error('missing host tool: '+name)
    capture(args)


if __name__ == '__main__': main()
