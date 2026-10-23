"""Local HUD glyph calibration for one fixed, unpaused reference-capture case.

Calibration is manually annotated from retained images. It is not a shipped game
font/model or a general OCR pipeline. Missing/ambiguous labels stay unknown.
"""
import hashlib
import math
import re
import struct
import subprocess
from pathlib import Path
import tempfile

WIDTH, HEIGHT = 24, 36
BOXES = {'main': (237,52,134,36), 'fraction': (372,60,51,29)}


def png_size(path):
    data=path.read_bytes()[:24]
    if data[:8] != b'\x89PNG\r\n\x1a\n' or data[12:16] != b'IHDR':
        raise ValueError('expected PNG image')
    return list(struct.unpack('!II',data[16:24]))


def decode_region(input_path, box, sequence=False):
    x,y,w,h=box
    command=['ffmpeg','-v','error','-i',str(input_path)]
    if not sequence: command += ['-frames:v','1']
    command += ['-vf',f'crop={w}:{h}:{x}:{y},format=gray','-fps_mode','passthrough','-f','rawvideo','pipe:1']
    return subprocess.run(command,capture_output=True,check=True).stdout


def glyphs(pixels, width, height, count):
    if len(pixels)!=width*height:
        raise ValueError('invalid grayscale region size')
    mask={i for i,b in enumerate(pixels) if b>=190}
    components=[]
    while mask:
        start=mask.pop();queue=[start]
        for point in queue:
            x,y=point%width,point//width
            for xx,yy in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
                n=yy*width+xx
                if 0<=xx<width and 0<=yy<height and n in mask:
                    mask.remove(n);queue.append(n)
        if len(queue)>5:components.append(queue)
    if len(components)<count:return None
    components=sorted(sorted(components,key=len,reverse=True)[:count],key=lambda c:min(i%width for i in c))
    result=[]
    for component in components:
        points=set(component)
        left,right=min(i%width for i in points),max(i%width for i in points)
        top,bottom=min(i//width for i in points),max(i//width for i in points)
        bits=tuple(((top+min(bottom-top,int((y+.5)*(bottom-top+1)/HEIGHT)))*width+
                    left+min(right-left,int((x+.5)*(right-left+1)/WIDTH))) in points
                   for y in range(HEIGHT) for x in range(WIDTH))
        result.append(bits)
    return result


def encode(bits):
    return format(int(''.join('1' if v else '0' for v in bits),2),f'0{WIDTH*HEIGHT//4}x')


def decode(text):
    if not isinstance(text,str) or len(text)!=WIDTH*HEIGHT//4 or not re.fullmatch('[0-9a-f]+',text):
        raise ValueError('invalid calibrated glyph')
    return tuple(c=='1' for c in format(int(text,16),f'0{WIDTH*HEIGHT}b'))


def calibrate(annotations, base):
    templates={name:{} for name in BOXES};sources=[]
    for anchor in annotations['anchors']:
        image=(base/anchor['image']).resolve()
        if png_size(image)!=[642,528]:raise ValueError('only the calibrated 642x528 capture geometry is supported')
        if not re.fullmatch(r'\d{2}:\d{2}\.\d{2}',anchor['timer']):raise ValueError('invalid annotated timer')
        digits=re.sub(r'\D','',anchor['timer'])
        for name,part,count in (('main',digits[:4],4),('fraction',digits[4:],2)):
            box=BOXES[name];found=glyphs(decode_region(image,box),box[2],box[3],count)
            if found is None:raise ValueError('annotated image has no complete timer glyphs')
            for digit,bits in zip(part,found):
                templates[name].setdefault(digit,[])
                word=encode(bits)
                if word not in templates[name][digit]:templates[name][digit].append(word)
        sources.append({'image':str(image),'timer':anchor['timer'],'sha256':hashlib.sha256(image.read_bytes()).hexdigest()})
    if set(templates['fraction'])!=set('0123456789'):raise ValueError('fraction calibration must cover all ten digits')
    return {'schema':1,'geometry':[642,528],'boxes':BOXES,'templates':templates,'sources':sources,
            'provenance':'manually verified timer annotations on retained images',
            'threshold':190,'max_hamming_error':0.12,'minimum_margin':0.015}


def recognize(found, templates, max_error, min_margin):
    if found is None:return None
    output='';worst=0.0;smallest=1.0
    for bits in found:
        scores=sorted((min(sum(a!=b for a,b in zip(bits,decode(word)))/len(bits) for word in words),digit)
                      for digit,words in templates.items())
        if len(scores)<2 or not all(math.isfinite(s[0]) for s in scores):raise ValueError('invalid glyph templates')
        error,digit=scores[0];margin=scores[1][0]-error
        if error>max_error or margin<min_margin:return None
        output+=digit;worst=max(worst,error);smallest=min(smallest,margin)
    return {'digits':output,'max_error':worst,'minimum_margin':smallest}


def label_images(folder, calibration, timers, first, last):
    if (calibration.get('schema')!=1 or calibration['geometry']!=[642,528]
            or calibration['boxes']!={k:list(v) for k,v in BOXES.items()}
            or calibration.get('threshold')!=190 or calibration.get('max_hamming_error')!=0.12
            or calibration.get('minimum_margin')!=0.015):
        raise ValueError('unsupported calibration geometry/schema')
    files=sorted(folder.glob('framedump_*.png'),key=lambda p:int(p.stem.split('_')[-1]))
    if not files or [int(p.stem.split('_')[-1]) for p in files]!=list(range(1,len(files)+1)):
        raise ValueError('missing/noncontiguous PNG sequence')
    eligible=[i for i,p in enumerate(files) if png_size(p)==[642,528]]
    if not eligible:raise ValueError('no images match calibrated capture geometry')
    mapping={}
    for frame,timer in timers.items():
        digits=re.sub(r'\D','',timer)
        if digits in mapping:raise ValueError('ambiguous timer-to-frame mapping')
        mapping[digits]=int(frame)
    recognized={};records=[]
    # Menus can use 640x528 while gameplay uses 642x528. Keep them unknown;
    # decode only exact-geometry images without resizing or assuming a frame ID.
    with tempfile.TemporaryDirectory() as temporary:
        inputs=Path(temporary)
        for index,source_index in enumerate(eligible,1):
            (inputs/f'{index}.png').symlink_to(files[source_index].resolve())
        for name,count in (('main',4),('fraction',2)):
            box=BOXES[name];size=box[2]*box[3]
            raw=decode_region(inputs/'%d.png',box,sequence=True)
            if len(raw)!=size*len(eligible):raise ValueError('decoded PNG count/geometry mismatch')
            recognized[name]=[None]*len(files)
            for i,source_index in enumerate(eligible):
                recognized[name][source_index]=recognize(glyphs(raw[i*size:(i+1)*size],box[2],box[3],count),
                    calibration['templates'][name],calibration['max_hamming_error'],calibration['minimum_margin'])
    for path,a,b in zip(files,recognized['main'],recognized['fraction']):
        digits=a['digits']+b['digits'] if a and b else None
        records.append({'image':path.name,'timer_digits':digits,'frame':mapping.get(digits),
                        'max_hamming_error':max(a['max_error'],b['max_error']) if a and b else None,
                        'minimum_digit_margin':min(a['minimum_margin'],b['minimum_margin']) if a and b else None})
    summary=summarize_labels(records,first,last)
    return {'schema':1,'method':'manually calibrated rendered HUD timer; no interpolation or numbering-based labels',
            'frame_label_provenance':'inferred from captured timer using local verified calibration',
            'recognition_policy':{k:calibration[k] for k in ('threshold','max_hamming_error','minimum_margin')},
            'uncalibrated_geometry_images':len(files)-len(eligible),
            'interval':[first,last],'records':records,**summary,
            'native_to_render_post_phase_equality_established':False}


def summarize_labels(records, first, last):
    selected={};last_seen=None;order_ok=True;duplicates=[]
    for record in records:
        frame=record['frame']
        if frame is None or not first<=frame<=last:continue
        if last_seen is not None and frame<last_seen:order_ok=False
        last_seen=frame
        if frame in selected:duplicates.append(frame)
        else:selected[frame]=record['image']
    missing=sorted(set(range(first,last+1))-selected.keys())
    return {'selected':selected,'missing_frames':missing,'duplicate_frames':duplicates,
            'chronological':order_ok,'passed':not missing and not duplicates and order_ok}
