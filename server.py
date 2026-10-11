#!/usr/bin/env python3
"""Local attribute planner, bounded native image jobs, and indexed gallery API."""
from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import mimetypes
import os
import random
import re
import stat
import sys
import threading
import warnings
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from PIL import Image, UnidentifiedImageError

from gallery import Gallery, MAX_IMAGE_BYTES, MAX_IMAGE_PIXELS, QueueFull, SAFE_PROVIDER_ERROR, save_image

ROOT = Path(__file__).resolve().parent
GENERATED_DIR = ROOT / 'generated'
HERMES_SOURCE = Path(os.environ.get('HERMES_SOURCE', Path.home() / '.hermes' / 'hermes-agent'))
if str(HERMES_SOURCE) not in sys.path:
    sys.path.insert(0, str(HERMES_SOURCE))

XAI_ASPECT_RATIOS = {'1:1', '16:9', '9:16', '4:3', '3:4', '3:2', '2:3'}
BODY_LIMIT = 200_000
PROVIDER_SLOTS = threading.BoundedSemaphore(4)
EXACT_PRODUCT_LIMIT = 4_096
PLANNER_NODE_LIMIT = 20_000
PLANNER_RESULT_LIMIT = 256
PREVIEW_MANIFEST_LIMIT = 2 * 1024 * 1024
PREVIEW_ID = re.compile(r'[a-zA-Z0-9_-]+\Z')
PHOTO_ID = re.compile(r'[0-9a-f]{32}\Z')


def safe_svg(raw):
    """Allow bounded, inert steering shapes only; never active XML/CSS/URLs."""
    if not raw or len(raw) > 262_144:
        return False
    source = re.sub(br'^\s*<\?xml\s+[^?]*\?>', b'', raw, count=1, flags=re.I)
    if re.search(br'(?i)<!DOCTYPE|<!ENTITY|<\?', source):
        return False
    namespace = '{http://www.w3.org/2000/svg}'
    tags = {'svg', 'g', 'title', 'desc', 'rect', 'circle', 'ellipse', 'line', 'path', 'polygon', 'text'}
    try:
        root = ET.fromstring(raw)
        if root.tag != namespace + 'svg':
            return False
        for index, node in enumerate(root.iter()):
            if index > 10_000 or node.tag not in {namespace + tag for tag in tags}:
                return False
            for key, value in node.attrib.items():
                lower = key.lower()
                if lower.startswith('on') or 'href' in lower or lower == 'style' or '{' in key:
                    return False
                if re.search(r'(?i)(?:https?:|data:|javascript:|url\s*\()', value):
                    return False
        return True
    except (ET.ParseError, ValueError, RecursionError):
        return False


class Catalog:
    def __init__(self, library):
        self.library_hash = hashlib.sha256(json.dumps(library, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        self.library = json.loads(json.dumps(library))
        self.attributes = {}
        self.thumbnail_paths = set()
        for category in self.library['categories']:
            for attribute in category['attributes']:
                aid = attribute['id']
                if aid in self.attributes or attribute['type'] not in {'exclusive', 'boolean', 'multi'}:
                    raise ValueError('invalid library attribute')
                attribute.setdefault('description', '')
                attribute.setdefault('thumbnail_url', attribute.get('thumbnail', ''))
                values = attribute['values']
                if not values or len({value['id'] for value in values}) != len(values):
                    raise ValueError('invalid library values')
                for value in values:
                    value.setdefault('steers', '')
                    value.setdefault('description', value['steers'])
                    value.setdefault('thumbnail_url', value.get('thumbnail', ''))
                self.attributes[aid] = attribute
                for item in [attribute, *values]:
                    url = item['thumbnail_url']
                    if isinstance(url, str) and url.startswith('/thumbnails/'):
                        self.thumbnail_paths.add(url)
        self.exclusions = set()
        known = {(aid, value['id']) for aid, attr in self.attributes.items() for value in attr['values']}
        for aid, attr in self.attributes.items():
            for value in attr['values']:
                refs = value.get('excludes', [])
                if not isinstance(refs, list) or any(not isinstance(ref, str) for ref in refs):
                    raise ValueError('invalid library excludes')
                for ref in refs:
                    target = tuple(ref.split(':'))
                    if target not in known:
                        raise ValueError(f'unknown library excludes reference: {ref}')
                    self.exclusions.add(frozenset(((aid, value['id']), target)))
        # Narrow, explicit rules for the current library; no inferred prompt ontology.
        short = [('hair_length', vid) for vid in ('shaved', 'buzz_cut')]
        styled = [('hair_style', vid) for vid in ('braided_crown', 'low_bun', 'high_bun',
                  'low_ponytail', 'high_ponytail', 'twin_braids')]
        styled += [('hair_fringe', vid) for vid in ('blunt_bangs', 'curtain_bangs', 'side_swept_fringe',
                   'wispy_fringe', 'micro_bangs', 'curved_fringe', 'face_framing_strands')]
        for left in short:
            for right in styled:
                if left in known and right in known:
                    self.exclusions.add(frozenset((left, right)))
        self.ordered_exclusions = sorted(self.exclusions, key=lambda pair: sorted(pair))

    @classmethod
    def load(cls, path):
        raw = Path(path).read_bytes()
        catalog = cls(json.loads(raw))
        catalog.library_hash = hashlib.sha256(raw).hexdigest()
        return catalog

    def conflict(self, selections):
        selected = {(aid, vid) for aid, ids in selections.items() for vid in ids}
        for pair in self.ordered_exclusions:
            if pair <= selected:
                return 'conflicting selections: ' + ' + '.join(f'{aid}:{vid}' for aid, vid in sorted(pair))
        return None

    def snapshot(self, mapping):
        return {aid: {'name': self.attributes[aid]['name'], 'type': self.attributes[aid]['type'],
                     'values': [dict(id=v['id'], name=v['name'], steers=v['steers'])
                                for v in self.attributes[aid]['values'] if v['id'] in ids]}
                for aid, ids in mapping.items()}

    def validate_map(self, mapping, kind='selections'):
        if not isinstance(mapping, dict):
            raise ValueError(f'{kind} must be an object of attribute IDs to value ID arrays')
        normalized = {}
        for aid, ids in mapping.items():
            if aid not in self.attributes:
                raise ValueError(f'unknown attribute: {aid}')
            attribute = self.attributes[aid]
            if not isinstance(ids, list) or any(not isinstance(vid, str) for vid in ids):
                raise ValueError(f'{aid} must contain an array of value IDs')
            if len(ids) != len(set(ids)):
                raise ValueError(f'{aid} contains duplicate value IDs')
            known = {v['id'] for v in attribute['values']}
            if any(vid not in known for vid in ids):
                raise ValueError(f'{aid} contains an unknown value ID')
            if kind == 'whitelist' and not ids:
                raise ValueError(f'{aid} whitelist must contain at least one value ID')
            if kind == 'selections' and attribute['type'] in {'exclusive', 'boolean'} and len(ids) > 1:
                raise ValueError(f'{aid} permits at most one {attribute["type"]} value ID')
            if ids:
                normalized[aid] = [v['id'] for v in attribute['values'] if v['id'] in ids]
        return normalized

    def prompt(self, selections, extra_prompt):
        parts = [self.library.get('base_locks', '')]
        for aid, attribute in self.attributes.items():
            for value in attribute['values']:
                if value['id'] in selections.get(aid, []):
                    parts.append(value['steers'])
        parts.extend([self.library.get('always_on', ''), extra_prompt])
        return '. '.join(part.strip().rstrip('.') for part in parts if part.strip())

    def preview(self, payload):
        if not isinstance(payload, dict):
            raise ValueError('request body must be an object')
        if set(payload) - {'selections', 'whitelist', 'mode', 'n', 'aspect_ratio', 'extra_prompt', 'seed'}:
            raise ValueError('unknown request fields')
        selections = self.validate_map(payload.get('selections', {}))
        conflict = self.conflict(selections)
        if conflict:
            raise ValueError(conflict)
        whitelist = self.validate_map(payload.get('whitelist', {}), 'whitelist')
        if set(payload.get('selections', {})) & set(payload.get('whitelist', {})):
            raise ValueError('an attribute cannot appear in both selections and whitelist')
        mode, n = payload.get('mode', 'single'), payload.get('n', 1)
        if not isinstance(mode, str) or mode not in {'single', 'repeat', 'variations'}:
            raise ValueError('mode must be single, repeat, or variations')
        if isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= 24:
            raise ValueError('n must be an integer between 1 and 24')
        if mode == 'single' and n != 1:
            raise ValueError('single mode requires n=1; use repeat for repeated images')
        if mode != 'variations' and whitelist:
            raise ValueError('whitelist requires variations mode')
        aspect_ratio = payload.get('aspect_ratio', '9:16')
        if not isinstance(aspect_ratio, str) or aspect_ratio not in XAI_ASPECT_RATIOS:
            raise ValueError('unsupported aspect_ratio')
        extra = payload.get('extra_prompt', '')
        if not isinstance(extra, str) or len(extra) > 10000:
            raise ValueError('extra_prompt must be a string of at most 10000 characters')
        seed = payload.get('seed')
        if seed is not None and (isinstance(seed, bool) or not isinstance(seed, int) or not -(2**63) <= seed < 2**63):
            raise ValueError('seed must be a 64-bit integer')
        if seed is None:
            seed = random.SystemRandom().randrange(2**63)
        choices = []
        for aid in sorted(self.attributes):
            if aid not in whitelist:
                continue
            ids = sorted(whitelist[aid])
            options = [[vid] for vid in ids]
            # Small multi subsets give meaningful combinations without an exponential power set.
            if self.attributes[aid]['type'] == 'multi':
                options.extend([[ids[i], ids[j]] for i in range(len(ids)) for j in range(i + 1, len(ids))])
            choices.append((aid, options))
        count = 1
        for _, options in choices:
            count *= len(options)
        rng = random.Random(seed)
        raw_count = count
        exact = count <= EXACT_PRODUCT_LIMIT
        valid = []
        nodes = 0
        selected = {aid: list(ids) for aid, ids in selections.items()}

        if exact:
            def visit(depth):
                nonlocal nodes
                nodes += 1
                if depth == len(choices):
                    valid.append({aid: list(ids) for aid, ids in selected.items()})
                    return
                aid, options = choices[depth]
                for option in options:
                    selected[aid] = option
                    if not self.conflict(selected):
                        visit(depth + 1)
                selected.pop(aid, None)
            visit(0)
            count = len(valid)
        else:
            # Draw ALL whitelisted attributes independently. A truncated DFS
            # freezes early attributes and is not a valid variation sampler.
            potential = {(aid, vid) for aid, ids in selections.items() for vid in ids}
            potential.update((aid, vid) for aid, ids in whitelist.items() for vid in ids)
            constrained = any(pair <= potential for pair in self.ordered_exclusions)
            seen = set()
            step_cost = len(choices) + 1
            while nodes + step_cost <= PLANNER_NODE_LIMIT and len(valid) < PLANNER_RESULT_LIMIT:
                nodes += step_cost
                candidate = {aid: list(ids) for aid, ids in selections.items()}
                signature = []
                for aid, options in choices:
                    option = rng.choice(options)
                    candidate[aid] = list(option)
                    signature.append(tuple(option))
                key = tuple(signature)
                if key not in seen and not self.conflict(candidate):
                    seen.add(key)
                    valid.append(candidate)
            # The unrestricted product is exact only if no catalog exclusion
            # can apply. Otherwise disclose only the observed valid lower bound.
            exact = not constrained
            count = raw_count if exact else len(valid)

        if mode == 'variations':
            if n > len(valid):
                if exact and n > count:
                    raise ValueError(f'n exceeds {count} distinct compatible combinations; use repeat for identical plans')
                raise ValueError(f'bounded planner found only {len(valid)} compatible combinations; narrow the whitelist')
            resolved = rng.sample(valid, n)
        else:
            resolved = [selections] * n
        plans = []
        requested_snapshot = {'selections': self.snapshot(selections), 'whitelist': self.snapshot(whitelist)}
        for index, selected in enumerate(resolved):
            selected = {aid: selected[aid] for aid in self.attributes if aid in selected}
            plans.append({'selections': selected, 'prompt': self.prompt(selected, extra),
                          'plan_index': index, 'library_hash': self.library_hash,
                          'selection_sampling_seed': seed, 'requested_selection_snapshot': requested_snapshot,
                          'resolved_selection_snapshot': self.snapshot(selected)})
        return {'plans': plans, 'combination_count': count,
                'combination_count_exact': exact, 'combination_count_metadata': {
                    'method': 'exact' if exact else 'bounded_search_lower_bound',
                    'unrestricted_product_count': raw_count, 'visited_nodes': nodes,
                    'node_limit': PLANNER_NODE_LIMIT, 'result_limit': PLANNER_RESULT_LIMIT}}


def generate_native_image(prompt: str, aspect_ratio: str) -> tuple[str, str]:
    """Generate through Hermes' xAI OAuth credentials without exposing them to the browser."""
    import requests
    from hermes_cli.config import load_config
    from tools.xai_http import hermes_xai_user_agent, resolve_xai_http_credentials

    credentials = resolve_xai_http_credentials()
    bearer = str(credentials.get('api_key') or '').strip()
    if not bearer:
        raise RuntimeError('No Hermes xAI OAuth credentials are available')
    config = load_config().get('image_gen', {}).get('xai', {})
    model = str(config.get('model') or 'grok-imagine-image-quality')
    resolution = str(config.get('resolution') or '1k')
    response = requests.post(
        f"{str(credentials.get('base_url') or 'https://api.x.ai/v1').rstrip('/')}/images/generations",
        headers={
            'Authorization': f'Bearer {bearer}',
            'Content-Type': 'application/json',
            'User-Agent': hermes_xai_user_agent(),
        },
        json={'model': model, 'prompt': prompt, 'aspect_ratio': aspect_ratio, 'resolution': resolution},
        timeout=120,
    )
    response.raise_for_status()
    data = response.json().get('data') or []
    if not data:
        raise RuntimeError('xAI returned no image data')
    first = data[0]
    if first.get('b64_json'):
        return first['b64_json'], 'image/jpeg'
    if first.get('url'):
        image = requests.get(first['url'], timeout=60)
        image.raise_for_status()
        return base64.b64encode(image.content).decode('ascii'), image.headers.get('Content-Type', 'image/jpeg')
    raise RuntimeError('xAI returned neither image bytes nor a URL')



def invoke_provider(prompt, aspect_ratio, provider=None):
    with PROVIDER_SLOTS:
        return (provider or generate_native_image)(prompt, aspect_ratio)


def legacy_request(payload):
    if not isinstance(payload, dict):
        raise ValueError('request body must be an object')
    if set(payload) - {'prompt', 'n', 'aspect_ratio'}:
        raise ValueError('unknown request fields')
    prompt = payload.get('prompt', '')
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 20000:
        raise ValueError('prompt is required and must be at most 20000 characters')
    n = payload.get('n', 1)
    if isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= 4:
        raise ValueError('n must be an integer between 1 and 4')
    aspect = payload.get('aspect_ratio', '9:16')
    if not isinstance(aspect, str) or aspect not in XAI_ASPECT_RATIOS:
        raise ValueError('unsupported aspect_ratio')
    return prompt.strip(), n, aspect


def generate_batch(payload, output_dir, store=None, provider=None, catalog=None):
    prompt, n, aspect = legacy_request(payload)
    records, errors = [], []
    plans = [{'prompt': prompt, 'selections': {}, 'library_hash': catalog.library_hash if catalog else None,
              'requested_selection_snapshot': {'selections': {}, 'whitelist': {}},
              'resolved_selection_snapshot': {}} for _ in range(n)]
    job_id = store.create_job(plans, aspect) if store else None
    for index in range(n):
        record = None
        try:
            if store:
                store.claim(job_id, index)
            encoded, _ = invoke_provider(prompt, aspect, provider)
            record = save_image(encoded, output_dir, aspect)
            if store:
                public = store.complete_plan(job_id, index, record=record)
            else:
                public = {'url': '/generated/' + record['filename']}
            records.append(public)
        except Exception:
            if record:
                for name in ('filename', 'thumbnail'):
                    (Path(output_dir) / record[name]).unlink(missing_ok=True)
            if store:
                store.complete_plan(job_id, index, error=SAFE_PROVIDER_ERROR)
            errors.append({'index': index, 'error': SAFE_PROVIDER_ERROR})
    if not records:
        raise RuntimeError(SAFE_PROVIDER_ERROR)
    result = {'data': records}
    if errors:
        result['errors'] = errors
    return result


class JobManager:
    def __init__(self, store, provider=None, recover=True):
        self.store, self.provider = store, provider
        if recover:
            store.recover()
        self.executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix='image-job')
        self.lock = threading.Lock()
        self.closed = False

    def submit(self, plans, aspect):
        with self.lock:
            if self.closed:
                raise QueueFull('generation queue is closed')
            job_id = self.store.create_job(plans, aspect)
            for index, plan in enumerate(plans):
                self.executor.submit(self._run, job_id, index, plan, aspect)
        return job_id

    def _run(self, job_id, index, plan, aspect):
        record = None
        try:
            if not self.store.claim(job_id, index):
                return
            encoded, _ = invoke_provider(plan['prompt'], aspect, self.provider)
            record = save_image(encoded, self.store.output_dir, aspect)
            self.store.complete_plan(job_id, index, record=record)
        except Exception:
            if record:
                for name in ('filename', 'thumbnail'):
                    (self.store.output_dir / record[name]).unlink(missing_ok=True)
            self.store.complete_plan(job_id, index, error=SAFE_PROVIDER_ERROR)

    def close(self):
        with self.lock:
            self.closed = True
        self.executor.shutdown(wait=True)


class Application:
    def __init__(self, root=ROOT, db_path=None, output_dir=None, catalog=None, provider=None, import_legacy=False):
        self.root = Path(root)
        self.catalog = catalog or Catalog.load(self.root / 'library.json')
        self.store = Gallery(db_path or self.root / 'gallery.sqlite3', output_dir or self.root / 'generated')
        if import_legacy:
            self.store.import_legacy()
        self.jobs = JobManager(self.store, provider)
        self.provider = provider
        self._preview_jpeg_cache = {}
        self._preview_cache_lock = threading.Lock()

    def _preview_file(self, path, limit):
        """Open a regular file without following a symlink in either local component."""
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        finally:
            os.close(directory)
        handle = os.fdopen(descriptor, 'rb')
        metadata = os.fstat(handle.fileno())
        if not stat.S_ISREG(metadata.st_mode) or not 0 < metadata.st_size <= limit:
            handle.close()
            raise ValueError('invalid preview file')
        return handle, metadata

    def _preview_jpeg(self, path, max_side=None, raw=False):
        """Validate pixels once per file revision; never trust an extension or MIME claim."""
        limit = PREVIEW_MANIFEST_LIMIT if max_side else MAX_IMAGE_BYTES
        try:
            handle, metadata = self._preview_file(path, limit)
            with handle:
                key = (metadata.st_dev, metadata.st_ino, metadata.st_size,
                       metadata.st_mtime_ns, metadata.st_ctime_ns, max_side)
                with self._preview_cache_lock:
                    cached = self._preview_jpeg_cache.get(path)
                if cached is None or cached[0] != key:
                    valid = False
                    try:
                        with warnings.catch_warnings():
                            warnings.simplefilter('error', Image.DecompressionBombWarning)
                            with Image.open(handle) as image:
                                if (image.format != 'JPEG' or image.width * image.height > MAX_IMAGE_PIXELS
                                        or (max_side and max(image.size) > max_side)):
                                    raise ValueError('invalid preview image')
                                image.verify()
                            handle.seek(0)
                            with Image.open(handle) as image:
                                image.load()
                        valid = True
                    except (ValueError, OSError, SyntaxError, UnidentifiedImageError, Image.DecompressionBombError,
                            Image.DecompressionBombWarning):
                        pass
                    with self._preview_cache_lock:
                        if len(self._preview_jpeg_cache) >= 4096:
                            self._preview_jpeg_cache.clear()
                        self._preview_jpeg_cache[path] = (key, valid)
                else:
                    valid = cached[1]
                if not valid:
                    return None
                if raw:
                    handle.seek(0)
                    contents = handle.read(limit + 1)
                    return contents if len(contents) <= limit else None
                return path
        except (OSError, ValueError):
            return None

    def preview_atlas(self, aid, raw=False):
        if aid not in self.catalog.attributes or not PREVIEW_ID.fullmatch(aid):
            return None
        # The output root is also forbidden from being a symlink.
        if self.store.output_dir.is_symlink():
            return None
        return self._preview_jpeg(self.store.output_dir / 'preview-atlases' / (aid + '.jpg'), 400, raw)

    def _preview_manifest(self):
        path = self.store.output_dir / 'photographic-previews.json'
        if not os.path.lexists(path):
            return False, None
        try:
            handle, _ = self._preview_file(path, PREVIEW_MANIFEST_LIMIT)
            with handle:
                raw = handle.read(PREVIEW_MANIFEST_LIMIT + 1)
            if len(raw) > PREVIEW_MANIFEST_LIMIT:
                raise ValueError('oversized preview manifest')
            def unique_object(pairs):
                result = {}
                for key, value in pairs:
                    if key in result:
                        raise ValueError('duplicate preview key')
                    result[key] = value
                return result
            manifest = json.loads(raw, object_pairs_hook=unique_object,
                                  parse_constant=lambda value: (_ for _ in ()).throw(ValueError('invalid constant')))
            if not isinstance(manifest, dict) or not isinstance(manifest.get('attributes'), dict):
                raise ValueError('invalid preview manifest')
            return True, manifest
        except (OSError, ValueError, UnicodeError, RecursionError):
            return True, None

    def thumbnail_library(self):
        """Merge on a copy so atomic worker updates need no catalog reload/restart."""
        active, manifest = self._preview_manifest()
        library = json.loads(json.dumps(self.catalog.library))
        total = sum(len(attribute['values']) for attribute in self.catalog.attributes.values())
        progress = dict(total=total, value_completed=0, attribute_completed=0, failed=0,
                        status='completed', version=0)
        if not active:
            progress['value_completed'] = sum(bool(value.get('thumbnail_url'))
                for attribute in self.catalog.attributes.values() for value in attribute['values'])
            progress['attribute_completed'] = sum(bool(attribute.get('thumbnail_url'))
                for attribute in self.catalog.attributes.values())
            return library, 'illustrative', progress
        manifest = manifest or {}
        attributes = manifest.get('attributes', {})
        version = manifest.get('version')
        if type(version) is int and 0 <= version <= 2**31 - 1:
            progress['version'] = version
        status = manifest.get('status')
        progress['status'] = status if isinstance(status, str) and status in {'running', 'completed', 'paused', 'failed'} else 'failed'
        # Fetch only the gallery fields needed for validation, in one read snapshot.
        wanted = {item.get('image_id') for aid, attr in attributes.items()
                  if aid in self.catalog.attributes and isinstance(attr, dict)
                  and isinstance(attr.get('values'), dict)
                  for vid, item in attr['values'].items()
                  if vid in {v['id'] for v in self.catalog.attributes[aid]['values']}
                  and isinstance(item, dict) and isinstance(item.get('image_id'), str)
                  and PHOTO_ID.fullmatch(item['image_id'])}
        records, tags = {}, set()
        if wanted:
            with self.store.connect() as db:
                db.execute('BEGIN')
                ids = sorted(wanted)
                for start in range(0, len(ids), 400):
                    chunk = ids[start:start + 400]
                    placeholders = ','.join('?' for _ in chunk)
                    for row in db.execute('SELECT id,filename,thumbnail,selections,width,height FROM images '
                                          f'WHERE id IN ({placeholders})', chunk):
                        records[row['id']] = dict(row)
                    for row in db.execute('SELECT image_id,attribute,value FROM image_tags '
                                          f'WHERE image_id IN ({placeholders})', chunk):
                        tags.add(tuple(row))
        for category in library['categories']:
            for attribute in category['attributes']:
                aid = attribute['id']
                entry = attributes.get(aid)
                entry = entry if isinstance(entry, dict) and PREVIEW_ID.fullmatch(aid) else {}
                values = entry.get('values', {})
                values = values if isinstance(values, dict) else {}
                for item in [attribute, *attribute['values']]:
                    illustration = item.get('thumbnail_url', '')
                    if isinstance(illustration, str) and illustration in self.catalog.thumbnail_paths:
                        item['illustration_url'] = illustration
                    item.update(thumbnail_url='', thumbnail_kind='pending', thumbnail_status='pending')
                    item.pop('example_url', None)
                    item.pop('thumbnail', None)
                for value in attribute['values']:
                    vid = value['id']
                    photo = values.get(vid)
                    if not isinstance(photo, dict) or photo.get('status') != 'ready' or not PREVIEW_ID.fullmatch(vid):
                        continue
                    image_id = photo.get('image_id')
                    record = records.get(image_id) if isinstance(image_id, str) else None
                    if not record or (image_id, aid, vid) not in tags:
                        continue
                    original, thumb = image_id + '.jpg', image_id + '-thumb.jpg'
                    if (photo.get('example_url') != '/generated/' + original
                            or photo.get('thumbnail_url') != '/generated/' + thumb
                            or record['filename'] != original or record['thumbnail'] != thumb
                            or type(record['width']) is not int or type(record['height']) is not int
                            or record['width'] <= 0 or record['height'] <= 0
                            or not 0 < record['width'] * record['height'] <= MAX_IMAGE_PIXELS):
                        continue
                    try:
                        selections = json.loads(record['selections'])
                        if not isinstance(selections, dict) or not isinstance(selections.get(aid), list) or vid not in selections[aid]:
                            continue
                    except (ValueError, TypeError, RecursionError):
                        continue
                    if (not self._preview_jpeg(self.store.output_dir / original)
                            or not self._preview_jpeg(self.store.output_dir / thumb, 400)):
                        continue
                    value.update(thumbnail_url='/generated/' + thumb, thumbnail_kind='photographic',
                                 thumbnail_status='ready', example_url='/generated/' + original)
                    progress['value_completed'] += 1
                atlas = '/preview-atlases/' + aid + '.jpg'
                if entry.get('thumbnail_url') == atlas and self.preview_atlas(aid):
                    attribute.update(thumbnail_url=atlas + '?v=' + str(progress['version']), thumbnail_kind='contact_sheet', thumbnail_status='ready')
                    progress['attribute_completed'] += 1
        # Failures are worker-reported; successes and totals always come from verified local data.
        failed = manifest.get('failed')
        if type(failed) is int and failed >= 0:
            progress['failed'] = min(failed, total - progress['value_completed'])
        if progress['status'] == 'completed' and (progress['value_completed'] != total
                or progress['attribute_completed'] != len(self.catalog.attributes)):
            progress['status'] = 'running'
        library.update(thumbnail_mode='photographic', thumbnail_progress=progress)
        return library, 'photographic', progress

    def close(self):
        self.jobs.close()


class APIError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


class AppHandler(BaseHTTPRequestHandler):
    # No inherited filesystem serving, HEAD, or directory listing behavior.
    @property
    def app(self):
        return self.server.app

    def log_message(self, format, *args):
        # Avoid logging user prompts/query strings or provider exception details.
        pass

    def _send(self, status, raw, content_type):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        if content_type == 'image/svg+xml':
            self.send_header('Content-Security-Policy', "default-src 'none'; style-src 'none'; sandbox")
        self.send_header('Cache-Control', 'no-store' if content_type.startswith('application/json') else 'no-cache')
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(raw)

    def _json(self, status, body):
        self._send(status, json.dumps(body).encode('utf-8'), 'application/json; charset=utf-8')

    @staticmethod
    def _loopback(host):
        if host == 'localhost':
            return True
        try:
            return ipaddress.ip_address(host).is_loopback
        except ValueError:
            return False

    def _guard(self, paid=False):
        hosts = self.headers.get_all('Host') or []
        if len(hosts) != 1:
            raise APIError(403, 'a loopback Host header is required')
        host = hosts[0]
        parsed = urlparse('http://' + host)
        try:
            port = parsed.port or 80
        except ValueError:
            raise APIError(403, 'invalid Host header')
        if (not self._loopback(parsed.hostname or '') or parsed.username or parsed.password or
                parsed.path or parsed.query or parsed.fragment or port != self.server.server_port):
            raise APIError(403, 'Host must match this loopback server')
        if not self._loopback(self.client_address[0]):
            raise APIError(403, 'loopback clients only')
        if paid:
            origins = self.headers.get_all('Origin') or []
            if len(origins) > 1 or (origins and origins[0] != 'http://' + host):
                raise APIError(403, 'Origin must match this server')
            if self.headers.get('Sec-Fetch-Site', '').lower() == 'cross-site':
                raise APIError(403, 'cross-site generation is forbidden')

    def _body(self):
        if self.headers.get_all('Transfer-Encoding') is not None:
            raise APIError(400, 'transfer encoding is not supported')
        lengths = self.headers.get_all('Content-Length') or []
        if not lengths:
            raise APIError(411, 'Content-Length is required')
        if len(lengths) != 1 or not lengths[0].isdigit():
            raise APIError(400, 'invalid Content-Length')
        length = int(lengths[0])
        if length > BODY_LIMIT:
            raise APIError(413, 'request body is too large')
        if self.headers.get_content_type() != 'application/json':
            raise APIError(415, 'Content-Type must be application/json')
        self.connection.settimeout(10)
        try:
            raw = self.rfile.read(length)
        except TimeoutError:
            raise APIError(408, 'request body timed out')
        if len(raw) != length:
            raise APIError(400, 'incomplete request body')
        try:
            def unique_object(pairs):
                result = {}
                for key, value in pairs:
                    if key in result:
                        raise ValueError('duplicate JSON key')
                    result[key] = value
                return result
            payload = json.loads(raw, object_pairs_hook=unique_object,
                                 parse_constant=lambda value: (_ for _ in ()).throw(ValueError('invalid JSON constant')))
        except (ValueError, UnicodeDecodeError, RecursionError):
            raise APIError(400, 'malformed JSON')
        if not isinstance(payload, dict):
            raise APIError(400, 'request body must be an object')
        return payload

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            self._guard(paid=path in {'/api/jobs', '/api/generate'})
            if path not in {'/api/preview', '/api/jobs', '/api/generate'}:
                raise APIError(404, 'not found')
            payload = self._body()
            if path == '/api/generate':
                result = generate_batch(payload, self.app.store.output_dir, self.app.store, self.app.provider, self.app.catalog)
                self._json(200, result)
                return
            preview = self.app.catalog.preview(payload)
            if path == '/api/preview':
                self._json(200, preview)
            else:
                job_id = self.app.jobs.submit(preview['plans'], payload.get('aspect_ratio', '9:16'))
                self._json(202, {'id': job_id})
        except APIError as exc:
            self._json(exc.status, {'error': exc.message})
        except ValueError as exc:
            self._json(400, {'error': str(exc)})
        except QueueFull as exc:
            self._json(429, {'error': str(exc)})
        except Exception:
            self._json(502, {'error': SAFE_PROVIDER_ERROR})
        self.close_connection = True

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        try:
            self._guard()
            parsed = urlparse(self.path)
            path = unquote(parsed.path)
            if path == '/api/health':
                self._json(200, self.app.store.health())
                return
            if path == '/api/library':
                self._json(200, self.app.thumbnail_library()[0])
                return
            if path == '/api/thumbnail-status':
                _, mode, progress = self.app.thumbnail_library()
                self._json(200, dict(mode=mode, **progress))
                return
            if path.startswith('/preview-atlases/'):
                basename = path[len('/preview-atlases/'):]
                aid = basename[:-4] if basename.endswith('.jpg') else ''
                raw = self.app.preview_atlas(aid, raw=True)
                if raw is None:
                    raise APIError(404, 'not found')
                self._send(200, raw, 'image/jpeg')
                return
            if path == '/api/gallery':
                params = parse_qs(parsed.query, keep_blank_values=True, max_num_fields=12)
                if set(params) - {'q', 'page', 'page_size', 'filters', 'aspect_ratio'} or any(len(v) != 1 for v in params.values()):
                    raise ValueError('invalid gallery query parameters')
                get = lambda key, default: params.get(key, [default])[0]
                try:
                    filters = json.loads(get('filters', '{}'))
                except (ValueError, RecursionError):
                    raise ValueError('filters must be a JSON object')
                filters = self.app.catalog.validate_map(filters, 'filters')
                aspect = get('aspect_ratio', '')
                if aspect and aspect not in XAI_ASPECT_RATIOS:
                    raise ValueError('unsupported aspect_ratio')
                try:
                    page, size = int(get('page', '1')), int(get('page_size', '24'))
                except ValueError:
                    raise ValueError('page and page_size must be integers')
                self._json(200, self.app.store.query(get('q', ''), page, size, filters, aspect))
                return
            for prefix, lookup in (('/api/jobs/', self.app.store.job), ('/api/images/', self.app.store.image)):
                if path.startswith(prefix):
                    image_id = path[len(prefix):]
                    if len(image_id) != 32 or any(ch not in '0123456789abcdef' for ch in image_id):
                        raise APIError(404, 'not found')
                    result = lookup(image_id)
                    if not result:
                        raise APIError(404, 'not found')
                    self._json(200, result)
                    return
            target = None
            if path in {'/', '/index.html'}:
                target = self.app.root / 'dist' / 'index.html'
                if not target.resolve().is_relative_to(self.app.root.resolve() / 'dist'):
                    target = None
            elif path.startswith('/assets/'):
                relative = path[len('/assets/'):]
                pieces = relative.split('/')
                allowed = {'.js', '.css', '.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg', '.ico', '.woff', '.woff2', '.ttf', '.avif'}
                base = self.app.root.resolve() / 'dist' / 'assets'
                candidate = base.joinpath(*pieces)
                if (relative and all(piece and not piece.startswith('.') and piece not in {'..', '.'} for piece in pieces)
                        and candidate.suffix.lower() in allowed and candidate.resolve().is_relative_to(base)):
                    target = candidate
            elif path.startswith('/thumbnails/') and path in self.app.catalog.thumbnail_paths:
                relative = path[len('/thumbnails/'):]
                base = self.app.root.resolve() / 'thumbnails'
                candidate = base / relative
                if (all(piece and not piece.startswith('.') for piece in relative.split('/'))
                        and candidate.suffix.lower() in {'.svg', '.png', '.jpg', '.jpeg', '.webp', '.avif'}
                        and candidate.resolve().is_relative_to(base)):
                    target = candidate
            elif path.startswith('/generated/'):
                filename = path[len('/generated/'):]
                if re.fullmatch(r'[0-9a-f]{32}(?:-thumb)?\.jpg', filename):
                    target = self.app.store.asset(filename)
                    if target and not target.resolve().is_relative_to(self.app.store.output_dir.resolve()):
                        target = None
            if target is None or not target.is_file() or target.is_symlink():
                raise APIError(404, 'not found')
            if target.suffix.lower() == '.svg' and target.stat().st_size > 262_144:
                raise APIError(404, 'illustration unavailable')
            raw = target.read_bytes()
            if target.suffix.lower() == '.svg' and not safe_svg(raw):
                raise APIError(404, 'illustration unavailable')
            self._send(200, raw, mimetypes.guess_type(target.name)[0] or 'application/octet-stream')
        except APIError as exc:
            self._json(exc.status, {'error': exc.message})
        except (ValueError, RecursionError) as exc:
            self._json(400, {'error': str(exc)})
        except Exception:
            self._json(500, {'error': 'Unable to read local data.'})


def create_server(app, host='127.0.0.1', port=8123):
    if not AppHandler._loopback(host):
        raise ValueError('server must bind to a loopback address')
    httpd = ThreadingHTTPServer((host, port), AppHandler)
    httpd.daemon_threads = True
    httpd.app = app
    return httpd


def main():
    host, port = os.environ.get('HOST', '127.0.0.1'), int(os.environ.get('PORT', '8123'))
    if not AppHandler._loopback(host):
        raise ValueError('server must bind to a loopback address')
    app = Application(import_legacy=os.environ.get('IMPORT_LEGACY_IMAGES') == '1')
    httpd = create_server(app, host, port)
    print(f'Open http://{host}:{port}. Native Hermes xAI OAuth stays on the server.')
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
        app.close()


if __name__ == '__main__':
    main()
