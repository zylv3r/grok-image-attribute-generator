#!/usr/bin/env python3
"""Generate approved real-photo catalog previews via the existing bounded app API.

Resumes verified successes and known job IDs, never blindly retries ambiguous
paid submissions. Images remain normal tagged gallery records. Contact sheets
are derived locally and cost no extra image-provider requests.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'generated'
MANIFEST = OUT / 'photographic-previews.json'
ATLAS = OUT / 'preview-atlases'
LOCK = threading.RLock()


def now():
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path, data):
    temp = path.with_name(path.name + '.new')
    with temp.open('w', encoding='utf-8') as stream:
        json.dump(data, stream, indent=2, ensure_ascii=False)
        stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
    os.replace(temp, path)


def framing(aid, category):
    subject = 'An adult woman in tasteful fully opaque editorial clothing. Believable human anatomy and realistic photographic texture.'
    if aid != 'age':
        subject += ' The subject is approximately 28 years old.'
    if category == 'hair':
        view = 'Square head-and-shoulders hair beauty photograph; clearly visible hair, natural skin, simple ivory top, plain pale gray studio background.'
    elif category in {'skin', 'phenotype', 'face', 'makeup'}:
        view = 'Square close-up beauty photograph with the face occupying most of the frame, minimal distractions, simple ivory clothing and pale gray background.'
        if aid == 'micro_texture': view = 'Square macro beauty photograph of adult cheek, nose and eye area, readable real skin detail, no retouching artifacts.'
        if aid == 'eyelashes' or aid == 'eye_makeup': view = 'Square photographic close-up of adult eyes and eyebrows, sharply visible eyelashes and eyelid makeup, credible skin texture.'
        if aid == 'lip_color' or aid == 'lip_shape': view = 'Square photographic beauty close-up clearly displaying adult lips, chin and lower nose; credible skin, opaque modest clothing outside the crop.'
    elif aid == 'scenery' or category in {'location', 'weather'}:
        view = 'Square environmental fashion photograph: the requested setting occupies most of the frame, with one adult in simple opaque ivory clothing at a natural readable scale. Show the distinguishing location/weather elements.'
    elif category == 'pose':
        view = 'Square full-body editorial photograph, head through toes fully inside the frame with breathing room. The specified pose is the dominant visual cue; simple ivory outfit, uncluttered setting.'
    elif category in {'outfit', 'tops', 'bottoms', 'outerwear'}:
        view = 'Square fashion photograph clearly showing the targeted garment construction and fabric; opaque clothing with secure coverage, natural cloth behavior, an uncluttered pale gray setting.'
        if aid in {'fabric_material', 'garment_pattern', 'seam_detail', 'drape_effect'}:
            view = 'Square photographic fashion detail crop of a securely covered torso and skirt fabric; textile surface, seams, folds and highlights occupy most of the picture. Use neutral ivory fabric unless the selected value determines color.'
        elif aid == 'high_slit':
            view = 'Square full-body editorial photograph showing a fully opaque securely covered dress and the selected slit treatment, never underwear or explicit nudity.'
    elif category == 'footwear':
        view = 'Square photographic fashion close-up of shoes worn on adult feet, lower trouser hems visible, realistic leather/textile/sole details, plain unobtrusive floor.'
    elif category == 'accessories':
        view = 'Square photographic fashion detail showing the requested accessory worn or held naturally by an adult, close enough to read its shape and materials, restrained ivory clothing.'
    elif category == 'lighting':
        view = 'Square mid-shot photographic portrait showing the requested light treatment clearly on face, clothing and background. Do not impose another lighting setup; simple neutral ivory outfit and neutral setting.'
    elif category == 'composition' or aid in {'focal_length', 'aperture', 'focus_target', 'shutter_motion'}:
        view = 'Square actual photograph demonstrating the selected framing, lens, focus or motion treatment. Include an adult in an opaque neutral outfit and enough foreground/background to reveal the photographic effect.'
    elif category == 'props':
        view = 'Square actual editorial photograph clearly showing the selected prop in natural use by an adult wearing opaque neutral clothing, with restrained surroundings.'
    else:
        view = 'Square actual photographic adult fashion editorial example. Make the requested aesthetic treatment visually obvious while keeping simple opaque ivory clothing and a coherent uncluttered frame.'
    # The exact target steer is appended by the normal server-side catalog planner.
    return f'{subject} {view} The selected library attribute is the key visual difference. No illustration, no diagram, no color swatch, no collage, no watermark, no labels, no lettering or UI screenshot. This must look like a real photographic example, not an explanation graphic.'


def api(base, path, payload=None):
    body = json.dumps(payload).encode() if payload is not None else None
    request = Request(base + path, data=body,
                      headers={'Content-Type': 'application/json', 'Origin': base},
                      method='POST' if payload is not None else 'GET')
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def verified_record(record, aid, vid):
    image_id = record.get('id', '')
    if not re.fullmatch('[0-9a-f]{32}', image_id): return False
    if record.get('selections') != {aid: [vid]}: return False
    if record.get('url') != f'/generated/{image_id}.jpg' or record.get('thumbnail_url') != f'/generated/{image_id}-thumb.jpg': return False
    try:
        for suffix in ('.jpg', '-thumb.jpg'):
            target = OUT / (image_id + suffix)
            if target.is_symlink(): return False
            with Image.open(target) as image:
                image.verify()
        with Image.open(OUT / (image_id + '.jpg')) as image:
            return image.size == (record['width'], record['height']) and abs(image.width / image.height - 1) <= .02
    except (OSError, ValueError, KeyError):
        return False


def contact_sheet(aid, attribute, ready):
    if not ready: return None
    ordered = [ready[v['id']] for v in attribute['values'] if v['id'] in ready]
    indices = sorted(set(round(i * (len(ordered) - 1) / max(1, min(4, len(ordered)) - 1)) for i in range(min(4, len(ordered)))))
    sheet = Image.new('RGB', (320, 240), '#f6f4ee'); draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=10)
    columns = 1 if len(indices) == 1 else 2
    rows = 1 if len(indices) <= 2 else 2
    cell_width, cell_height = 320 // columns, 240 // rows
    for slot, index in enumerate(indices):
        item = ordered[index]; x, y = (slot % columns) * cell_width, (slot // columns) * cell_height
        with Image.open(OUT / (item['image_id'] + '-thumb.jpg')) as source:
            photo = ImageOps.contain(source.convert('RGB'), (cell_width - 8, cell_height - 21), Image.Resampling.LANCZOS)
            sheet.paste(photo, (x + (cell_width - photo.width)//2, y + 3))
        name = next(v['name'] for v in attribute['values'] if v['id'] == item['value'])
        draw.text((x + 5, y + cell_height - 14), name[:23], fill='#26344a', font=font)
    ATLAS.mkdir(parents=True, exist_ok=True)
    target = ATLAS / (aid + '.jpg'); temp = target.with_suffix('.new')
    with temp.open('wb') as stream:
        sheet.save(stream, 'JPEG', quality=90); stream.flush(); os.fsync(stream.fileno())
    os.replace(temp, target)
    return '/preview-atlases/' + aid + '.jpg'


def publish(state, attrs, status=None):
    if status is not None: state['status'] = status
    groups = {}
    for task in state['tasks'].values():
        if task['status'] != 'completed': continue
        aid, vid = task['attribute'], task['value']
        group = groups.setdefault(aid, {'values': {}})
        group['values'][vid] = {'status': 'ready', 'image_id': task['image_id'],
                                'thumbnail_url': task['thumbnail_url'], 'example_url': task['example_url']}
    for aid, group in groups.items():
        ready = {v: dict(info, value=v) for v, info in group['values'].items()}
        group['thumbnail_url'] = contact_sheet(aid, attrs[aid], ready)
    state['attributes'] = groups
    state['completed'] = sum(t['status'] == 'completed' for t in state['tasks'].values())
    state['failed'] = sum(t['status'] in {'failed', 'ambiguous'} for t in state['tasks'].values())
    state['version'] = state.get('version', 0) + 1
    state['updated_at'] = now()
    atomic_json(MANIFEST, state)


def generate_one(base, state, attrs, categories, key):
    task = state['tasks'][key]; aid, vid = task['attribute'], task['value']
    with LOCK:
        job_id = task.get('job_id')
        task['status'] = 'running'; task['started_at'] = now()
        atomic_json(MANIFEST, state)
    if not job_id:
        extra = framing(aid, categories[aid])
        seed = int(hashlib.sha256(key.encode()).hexdigest()[:15], 16)
        payload = {'selections': {aid: [vid]}, 'mode': 'single', 'n': 1,
                   'aspect_ratio': '1:1', 'extra_prompt': extra, 'seed': seed}
        for attempt in range(60):
            try:
                submitted = api(base, '/api/jobs', payload)
                job_id = submitted['id']
                with LOCK:
                    task['job_id'] = job_id; atomic_json(MANIFEST, state)
                break
            except HTTPError as exc:
                if exc.code != 429: raise
                time.sleep(min(30, 2 + attempt))  # Rejected queue submissions are not paid retries.
        if not job_id: raise RuntimeError('queue admission remained unavailable')
    deadline = time.monotonic() + 1200
    while time.monotonic() < deadline:
        job = api(base, '/api/jobs/' + job_id)
        if job['status'] in {'completed', 'partial', 'failed'}:
            if job['completed'] != 1 or job['failed'] != 0 or len(job['results']) != 1:
                raise RuntimeError('provider job failed; preserved for deliberate retry, not auto-resubmitted')
            record = job['results'][0]
            if not verified_record(record, aid, vid): raise RuntimeError('actual photograph verification failed')
            with LOCK:
                task.update(status='completed', image_id=record['id'], thumbnail_url=record['thumbnail_url'],
                            example_url=record['url'], width=record['width'], height=record['height'], completed_at=now())
                task.pop('error', None); publish(state, attrs)
                print(json.dumps({'completed':state['completed'], 'total':state['total'], 'key':key, 'image_id':record['id']}), flush=True)
            return True
        time.sleep(1)
    raise RuntimeError('known job still unfinished after wait; resume its ID without resubmitting')


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--base', default='http://127.0.0.1:8123')
    parser.add_argument('--workers', type=int, default=3); parser.add_argument('--limit', type=int)
    args = parser.parse_args(); assert 1 <= args.workers <= 4
    if args.limit is not None and args.limit < 0:
        parser.error('--limit must be nonnegative')
    OUT.mkdir(exist_ok=True)
    with (OUT / '.photographic-preview.lock').open('a') as process_lock:
        fcntl.flock(process_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        raw = (ROOT / 'library.json').read_bytes(); library = json.loads(raw)
        attrs = {a['id']: a for c in library['categories'] for a in c['attributes']}
        categories = {a['id']: c['id'] for c in library['categories'] for a in c['attributes']}
        tasks = {a['id']+':'+v['id']: {'attribute':a['id'], 'value':v['id'], 'status':'pending'} for a in attrs.values() for v in a['values']}
        digest = hashlib.sha256(raw).hexdigest()
        if MANIFEST.exists():
            state = json.loads(MANIFEST.read_text()); assert state['library_hash'] == digest, 'Catalog changed; explicit reconciliation required'
            assert set(state['tasks']) == set(tasks), 'Task inventory mismatch'
            for key, task in state['tasks'].items():
                if task['status'] == 'completed':
                    record = api(args.base, '/api/images/' + task['image_id'])
                    assert verified_record(record, task['attribute'], task['value']), key
                elif task.get('job_id'):
                    # Reconcile a known submission even if an earlier polling
                    # connection failed; never submit its paid request again.
                    existing = api(args.base, '/api/jobs/' + task['job_id'])
                    if existing['status'] == 'completed' and len(existing['results']) == 1:
                        record = existing['results'][0]
                        assert verified_record(record, task['attribute'], task['value']), key
                        task.update(status='completed', image_id=record['id'], thumbnail_url=record['thumbnail_url'],
                                    example_url=record['url'], width=record['width'], height=record['height'], completed_at=now())
                        task.pop('error', None)
                    elif existing['status'] in {'queued', 'running'}:
                        task['status'] = 'pending'
                    else:
                        task['status'] = 'failed'
                elif task['status'] == 'running':
                    task['status'] = 'ambiguous'
        else:
            state = {'schema':1, 'library_hash':digest, 'total':len(tasks), 'status':'running', 'tasks':tasks, 'version':0, 'created_at':now()}
        assert state['total'] == 893, state['total']
        publish(state, attrs, 'running')
        priority = ['hair_color:golden_blonde','hair_color:platinum','fabric_material:satin','fabric_material:cotton_poplin','light_quality:hard','light_quality:soft']
        order = list(priority)
        for index in range(max(len(a['values']) for a in attrs.values())):
            for aid, attribute in attrs.items():
                if index < len(attribute['values']):
                    key = aid+':'+attribute['values'][index]['id']
                    if key not in order: order.append(key)
        pending = [key for key in order if state['tasks'][key]['status'] == 'pending']
        if args.limit is not None: pending = pending[:args.limit]
        failures = 0
        # Submit in small windows so persistent provider faults do not bill/hammer the remaining catalog.
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            for start in range(0, len(pending), args.workers):
                batch = {pool.submit(generate_one, args.base, state, attrs, categories, key):key for key in pending[start:start+args.workers]}
                for future in as_completed(batch):
                    key = batch[future]
                    try:
                        future.result(); failures = 0
                    except Exception as exc:
                        with LOCK:
                            task = state['tasks'][key]
                            task['status'] = 'failed' if task.get('job_id') else 'ambiguous'
                            task['error'] = str(exc)[:300]; publish(state, attrs)
                            print(json.dumps({'failed_key':key,'error':task['error']}), flush=True)
                        failures += 1
                if failures >= 3:
                    publish(state, attrs, 'paused')
                    raise RuntimeError('batch paused after persistent failures; no blind paid retries')
        publish(state, attrs, 'completed' if state['completed'] == state['total'] else 'paused')
        print(json.dumps({'status':state['status'],'completed':state['completed'],'total':state['total'],'failed':state['failed'],'manifest':str(MANIFEST)}), flush=True)
        if args.limit is None and state['completed'] != state['total']: raise SystemExit(1)

if __name__ == '__main__': main()
