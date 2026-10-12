#!/usr/bin/env python3
"""Local attribute planner, bounded native image jobs, and indexed gallery API."""
from __future__ import annotations

import base64
import hashlib
import io
import ipaddress
import json
import mimetypes
import os
import random
import re
import stat
import sys
import tempfile
import threading
import warnings
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from PIL import Image, UnidentifiedImageError

from gallery import Gallery, MAX_IMAGE_BYTES, MAX_IMAGE_PIXELS, QueueFull, SAFE_PROVIDER_ERROR, save_image
from presets import Presets, PresetError

try:
    import catalog_v2
except ModuleNotFoundError as exc:
    if exc.name != 'catalog_v2':
        raise
    catalog_v2 = None

try:
    from comparisons import ComparisonStore
except ModuleNotFoundError as exc:
    if exc.name != 'comparisons':
        raise
    ComparisonStore = None

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
    def __init__(self, library, bundle=None):
        self.library_hash = hashlib.sha256(json.dumps(library, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        self.library = json.loads(json.dumps(library))
        self.bundle = bundle
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
        # Required controls may occur later in the planner's search order.
        self.partial_library = dict(self.library, compatibility_rules=[
            {key: value for key, value in rule.items() if key != 'requires'}
            for rule in self.library.get('compatibility_rules', [])])

    @classmethod
    def load(cls, path):
        raw = Path(path).read_bytes()
        catalog = cls(json.loads(raw))
        catalog.library_hash = hashlib.sha256(raw).hexdigest()
        return catalog

    def conflict(self, selections, partial=False):
        selected = {(aid, vid) for aid, ids in selections.items() for vid in ids}
        for pair in self.ordered_exclusions:
            if pair <= selected:
                return 'conflicting selections: ' + ' + '.join(f'{aid}:{vid}' for aid, vid in sorted(pair))
        if catalog_v2 is not None and (self.bundle is not None or self.library.get('catalog_version') == 2 or self.library.get('compatibility_rules')):
            return catalog_v2.validate_compatibility(selections, self.partial_library if partial else self.library)
        return None

    def expand_recipes(self, selections):
        expanded = {aid: list(ids) for aid, ids in selections.items()}
        queue = [(aid, vid) for aid, ids in expanded.items() for vid in ids]
        visited = set()
        while queue:
            aid, vid = queue.pop(0)
            if (aid, vid) in visited:
                continue
            visited.add((aid, vid))
            value = next(v for v in self.attributes[aid]['values'] if v['id'] == vid)
            for component, wanted in value.get('recipe', {}).get('selections', {}).items():
                current = expanded.setdefault(component, [])
                for component_id in wanted:
                    if component_id not in current:
                        current.append(component_id)
                        queue.append((component, component_id))
        return expanded

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
                if self.bundle is not None:
                    raise ValueError(f'retired or unsupported attribute: {aid}; use /api/catalog/resolve to review migration')
                raise ValueError(f'unknown attribute: {aid}')
            attribute = self.attributes[aid]
            if not isinstance(ids, list) or any(not isinstance(vid, str) for vid in ids):
                raise ValueError(f'{aid} must contain an array of value IDs')
            if len(ids) != len(set(ids)):
                raise ValueError(f'{aid} contains duplicate value IDs')
            known = {v['id'] for v in attribute['values']}
            if any(vid not in known for vid in ids):
                if self.bundle is not None:
                    raise ValueError(f'{aid} contains a retired or unsupported value ID; use /api/catalog/resolve to review migration')
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
        requested_selections = {aid: list(ids) for aid, ids in selections.items()}
        defaulted = []
        # Defaults are authoritative catalog values, never prompt text from a client.
        for aid, attr in self.attributes.items():
            default = attr.get('default', attr.get('default_value'))
            raw_whitelist = payload.get('whitelist', {})
            if default and aid not in selections and (not isinstance(raw_whitelist, dict) or aid not in raw_whitelist):
                selections[aid] = self.validate_map({aid: [default]})[aid]
                defaulted.append(aid)
        conflict = self.conflict(selections, partial=bool(payload.get('whitelist')))
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
                    if not self.conflict(selected):
                        valid.append({aid: list(ids) for aid, ids in selected.items()})
                    return
                aid, options = choices[depth]
                for option in options:
                    selected[aid] = option
                    if not self.conflict(selected, partial=True):
                        visit(depth + 1)
                selected.pop(aid, None)
            visit(0)
            count = len(valid)
        else:
            # Draw ALL whitelisted attributes independently. A truncated DFS
            # freezes early attributes and is not a valid variation sampler.
            potential = {(aid, vid) for aid, ids in selections.items() for vid in ids}
            potential.update((aid, vid) for aid, ids in whitelist.items() for vid in ids)
            constrained = any(pair <= potential for pair in self.ordered_exclusions) or bool(self.library.get('compatibility_rules')) or any(
                v.get('recipe') for a in self.attributes.values() for v in a['values'])
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
        requested_snapshot = {'selections': self.snapshot(requested_selections), 'whitelist': self.snapshot(whitelist),
                              'requested_maps': json.loads(json.dumps({'selections': payload.get('selections', {}), 'whitelist': payload.get('whitelist', {})})),
                              'defaulted': defaulted}
        for index, selected in enumerate(resolved):
            selected = self.expand_recipes(selected)
            conflict = self.conflict(selected)
            if conflict:
                raise ValueError(conflict)
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


def _validated_image_bytes(raw, aspect_ratio=None, mime=None):
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_IMAGE_BYTES:
        raise ValueError('invalid image bytes')
    with warnings.catch_warnings():
        warnings.simplefilter('error', Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(raw)) as image:
            if not 0 < image.width * image.height <= MAX_IMAGE_PIXELS:
                raise ValueError('invalid image dimensions')
            actual_mime = Image.MIME.get(image.format)
            if actual_mime not in {'image/jpeg', 'image/png', 'image/webp'} or (mime and mime != actual_mime):
                raise ValueError('invalid image format')
            width, height = image.size
            image.verify()
        with Image.open(io.BytesIO(raw)) as image:
            image.load()
    if aspect_ratio:
        left, right = map(int, aspect_ratio.split(':'))
        if abs(width / height - left / right) > max(left / right * .02, 1 / height):
            raise ValueError('provider image has the wrong aspect ratio')
    return actual_mime


def edit_native_image(prompt: str, image_bytes: bytes, mime: str, aspect_ratio: str) -> tuple[str, str]:
    """Native JSON reference edit. No URL downloads or text-generation fallback."""
    try:
        if (not isinstance(prompt, str) or not 0 < len(prompt) <= 20000 or not isinstance(aspect_ratio, str)
                or not re.fullmatch(r'[1-9][0-9]{0,4}:[1-9][0-9]{0,4}', aspect_ratio)):
            raise ValueError('invalid edit request')
        actual_mime = _validated_image_bytes(image_bytes, aspect_ratio, mime=mime)
        import requests
        from hermes_cli.config import load_config
        from tools.xai_http import hermes_xai_user_agent, resolve_xai_http_credentials
        credentials = resolve_xai_http_credentials()
        bearer = str(credentials.get('api_key') or '').strip()
        if not bearer:
            raise ValueError('credentials unavailable')
        model = str(load_config().get('image_gen', {}).get('xai', {}).get('edit_model') or 'grok-imagine-image-2.0')
        body = {'model': model, 'prompt': prompt, 'response_format': 'b64_json',
                'image': {'url': 'data:' + actual_mime + ';base64,' + base64.b64encode(image_bytes).decode('ascii'),
                          'type': 'image_url'}}
        # For a reviewed crop outside supported generation ratios, retain the reference
        # dimensions rather than instructing the provider to stretch or resize it.
        if aspect_ratio in XAI_ASPECT_RATIOS:
            body['aspect_ratio'] = aspect_ratio
        response = requests.post(
            str(credentials.get('base_url') or 'https://api.x.ai/v1').rstrip('/') + '/images/edits',
            headers={'Authorization': 'Bearer ' + bearer, 'Content-Type': 'application/json',
                     'User-Agent': hermes_xai_user_agent()},
            json=body, timeout=120, stream=True)
        try:
            response.raise_for_status()
            limit = MAX_IMAGE_BYTES * 4 // 3 + 65536
            chunks, size = [], 0
            for chunk in response.iter_content(chunk_size=65536):
                size += len(chunk)
                if size > limit:
                    raise ValueError('oversized image response')
                chunks.append(chunk)
            data = json.loads(b''.join(chunks)).get('data')
        finally:
            response.close()
        if not isinstance(data, list) or not data or not isinstance(data[0], dict):
            raise ValueError('no image data')
        encoded = data[0].get('b64_json')
        if not isinstance(encoded, str) or len(encoded) > MAX_IMAGE_BYTES * 4 // 3 + 4:
            raise ValueError('no bounded image bytes')
        raw = base64.b64decode(encoded, validate=True)
        actual_mime = _validated_image_bytes(raw, aspect_ratio)
        return encoded, actual_mime
    except Exception:
        raise RuntimeError(SAFE_PROVIDER_ERROR) from None


def invoke_edit_provider(prompt, image_bytes, mime, aspect_ratio, provider=None):
    with PROVIDER_SLOTS:
        try:
            return (provider or edit_native_image)(prompt, image_bytes, mime, aspect_ratio)
        except Exception:
            raise RuntimeError(SAFE_PROVIDER_ERROR) from None


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
    def __init__(self, root=ROOT, db_path=None, output_dir=None, catalog=None, provider=None, import_legacy=False, edit_provider=None):
        self.root = Path(root)
        self.bundle = (getattr(catalog, 'bundle', None) if catalog is not None else
                       catalog_v2.load_bundle(self.root) if catalog_v2 is not None else None)
        self.catalog = catalog or (Catalog(self.bundle['library'], self.bundle) if self.bundle else Catalog.load(self.root / 'library.json'))
        self.historical_catalog = Catalog(catalog_v2.historical_library(self.bundle)) if self.bundle else self.catalog
        self.legacy_catalog = Catalog(self.bundle['legacy_library']) if self.bundle else self.catalog
        if self.bundle:
            active_categories = {c['id'] for c in self.catalog.library['categories']}
            for category in self.historical_catalog.library['categories']:
                category['historical_only'] = category['id'] not in active_categories
                for attribute in category['attributes']:
                    active = self.catalog.attributes.get(attribute['id'])
                    attribute['historical_only'] = active is None
                    current_ids = {v['id'] for v in active['values']} if active else set()
                    for value in attribute['values']:
                        value['historical_only'] = value['id'] not in current_ids
        self.store = Gallery(db_path or self.root / 'gallery.sqlite3', output_dir or self.root / 'generated')
        if self.bundle:
            self.store.set_filter_aliases(self.bundle['aliases'])
        self.presets = Presets(self.root / 'presets.sqlite3', self.catalog.library_hash)
        if import_legacy:
            self.store.import_legacy()
        self.jobs = JobManager(self.store, provider)
        self.provider = provider
        self.edit_provider = edit_provider
        self.comparisons = ComparisonStore(self.root) if ComparisonStore is not None and self.bundle else None
        if self.comparisons is not None:
            assert self.bundle is not None
            self.comparisons.list_categories(self.bundle['library'])
        self._preview_jpeg_cache = {}
        self._preview_cache_lock = threading.Lock()

    def catalog_versions(self):
        categories = []
        for cat in self.catalog.library['categories']:
            attrs = cat['attributes']
            categories.append({'id': cat['id'], 'name': cat['name'],
                               'attributes': len(attrs), 'values': sum(len(a['values']) for a in attrs),
                               'source_control_mode': cat.get('preview_status', 'legacy_independent' if not self.bundle else 'draft')})
        return {'active_version': 2 if self.bundle else 1, 'legacy_version': 1,
                'library_hash': self.catalog.library_hash,
                'source_control_mode': 'category_review' if self.bundle else 'legacy',
                'effective_counts': {'categories': len(categories), 'attributes': len(self.catalog.attributes),
                                     'values': sum(len(a['values']) for a in self.catalog.attributes.values())},
                'categories': categories}

    def gallery_labels(self, image):
        if not self.bundle or not image or image.get('resolved_selection_snapshot'):
            return image
        selections = image.get('selections', {})
        snapshot = {}
        for aid, ids in selections.items():
            source = self.legacy_catalog if aid in self.legacy_catalog.attributes else self.historical_catalog
            if aid in source.attributes and isinstance(ids, list):
                snapshot.update(source.snapshot({aid: ids}))
        if snapshot:
            image = dict(image, resolved_selection_snapshot=snapshot, label_snapshot_source='archived_catalog')
        return image

    def resolve_draft(self, raw):
        if not isinstance(raw, dict):
            raise ValueError('draft must be an object')
        if self.bundle:
            result = catalog_v2.resolve_draft(raw, self.bundle)
        else:
            unresolved = []
            for field in ('selections', 'whitelist'):
                mapping = raw.get(field, {})
                if not isinstance(mapping, dict):
                    unresolved.append({'field': field, 'reason': 'unsupported control structure'})
                    continue
                for aid, ids in mapping.items():
                    try:
                        self.catalog.validate_map({aid: ids}, 'filters')
                    except ValueError as exc:
                        unresolved.append({'field': field, 'attribute_id': aid, 'reason': str(exc)})
            result = {'draft': json.loads(json.dumps(raw)), 'changes': [], 'unresolved': unresolved}
        return dict(result, raw_draft=json.loads(json.dumps(raw)))

    def comparison_post(self, category_id, action, payload):
        if self.comparisons is None or category_id not in {cat['id'] for cat in self.catalog.library['categories']}:
            raise APIError(404, 'comparison category not found')
        fields = {
            'base': ({'image_id'}, {'image_id', 'subject_id', 'crop', 'attribute_id', 'group', 'baseline_confirmations'}),
            'mask': ({'attribute_id', 'polygon'}, {'attribute_id', 'polygon', 'group'}),
            'approve': ({'stage', 'expected_contract_hash'}, {'stage', 'expected_contract_hash', 'artifact_ids', 'provider_attempt_cap', 'approval_note', 'attribute_id', 'group'}),
            'preview': ({'attribute_id', 'value_id', 'method', 'request_key'}, {'attribute_id', 'value_id', 'method', 'params', 'request_key', 'group'}),
        }
        fields['reopen'] = ({'expected_contract_hash', 'approval_note'}, {'expected_contract_hash', 'approval_note', 'attribute_id', 'group'})
        required, allowed = fields[action]
        if not required <= set(payload) or set(payload) - allowed:
            raise ValueError('invalid comparison request fields')
        targeting = {k: payload[k] for k in ('attribute_id', 'group') if k in payload}
        for field, value in targeting.items():
            if not isinstance(value, str) or not value or len(value) > 200:
                raise ValueError('invalid comparison ' + field)
        if action == 'reopen':
            return self.comparisons.reopen(category_id, payload['expected_contract_hash'], payload['approval_note'], **targeting)
        if action == 'base':
            confirmations = payload.get('baseline_confirmations')
            if 'baseline_confirmations' in payload and (not isinstance(confirmations, list) or len(confirmations) > 100 or
                    any(not isinstance(v, str) or not v.strip() or len(v) > 1000 for v in confirmations) or
                    len(set(confirmations)) != len(confirmations)):
                raise ValueError('invalid operator baseline_confirmations')
            targeting['baseline_confirmations'] = confirmations
            path = self.store.owned_image(payload['image_id'])
            if path is None or self._preview_jpeg(path) is None:
                raise ValueError('image_id must identify an owned gallery photograph')
            subject = payload.get('subject_id', 'woman-1')
            if not isinstance(subject, str) or not PREVIEW_ID.fullmatch(subject) or len(subject) > 100:
                raise ValueError('invalid subject_id')
            if path.resolve().is_relative_to(self.root.resolve()):
                return self.comparisons.set_base(category_id, path, payload['image_id'], subject, payload.get('crop'), **targeting)
            # The catalog checkout may use an existing installation's private
            # gallery path. Copy owned bytes transiently across the engine's root
            # boundary; never move, rename or rewrite the source photograph.
            handle, _ = self._preview_file(path, MAX_IMAGE_BYTES)
            with handle:
                original = handle.read(MAX_IMAGE_BYTES + 1)
            _validated_image_bytes(original, mime='image/jpeg')
            with tempfile.NamedTemporaryFile(dir=self.root / 'generated', prefix='.owned-reference-', suffix='.jpg') as reference:
                reference.write(original)
                reference.flush()
                return self.comparisons.set_base(category_id, Path(reference.name), payload['image_id'], subject, payload.get('crop'), **targeting)
        if action == 'approve':
            if payload['stage'] not in ('contract', 'pilot', 'publish', 'expansion'):
                raise ValueError('stage must be contract, pilot, publish, or expansion')
            digest = payload['expected_contract_hash']
            if not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest):
                raise ValueError('expected_contract_hash must be a SHA256 digest')
            artifacts = payload.get('artifact_ids', [])
            if not isinstance(artifacts, list) or len(artifacts) > 2000 or any(not isinstance(a, str) or not PHOTO_ID.fullmatch(a) for a in artifacts) or len(set(artifacts)) != len(artifacts):
                raise ValueError('artifact_ids must be distinct registered IDs')
            cap = payload.get('provider_attempt_cap', 0)
            if type(cap) is not int or not 0 <= cap <= 3:
                raise ValueError('provider_attempt_cap must be an integer between 0 and 3')
            note = payload.get('approval_note', '')
            if not isinstance(note, str) or len(note) > 2000:
                raise ValueError('approval_note must be at most 2000 characters')
            return self.comparisons.approve(category_id, payload['stage'], digest, artifacts, cap, note, **targeting)
        aid = payload['attribute_id']
        category = next(c for c in self.catalog.library['categories'] if c['id'] == category_id)
        if not isinstance(aid, str) or aid not in {a['id'] for a in category['attributes']}:
            raise ValueError('attribute_id must belong to this comparison category')
        if action == 'mask':
            return self.comparisons.set_mask(category_id, aid, payload['polygon'], group=payload.get('group'))
        vid = payload['value_id']
        if not isinstance(vid, str) or vid not in {v['id'] for v in self.catalog.attributes[aid]['values']}:
            raise ValueError('value_id must belong to attribute_id')
        method, params, key = payload['method'], payload.get('params', {}), payload['request_key']
        if not isinstance(method, str) or not PREVIEW_ID.fullmatch(method) or len(method) > 100:
            raise ValueError('invalid preview method')
        if not isinstance(params, dict):
            raise ValueError('params must be an object')
        forbidden_sources = {'url', 'path', 'filename', 'source', 'source_url', 'source_path', 'image_url',
                             'image_path', 'image_bytes', 'image_id', 'base_url', 'base_path', 'base_asset_id',
                             'mask', 'mask_url', 'mask_path', 'mask_asset_id', 'polygon', 'output_size', 'resize', 'prompt'}
        def owned_params(value, depth=0):
            if depth > 12:
                raise ValueError('comparison parameters are too deeply nested')
            if isinstance(value, dict):
                if any(key.lower() in forbidden_sources for key in value):
                    raise ValueError('comparison sources, masks and prompts are server-owned')
                for item in value.values():
                    owned_params(item, depth + 1)
            elif isinstance(value, list):
                for item in value:
                    owned_params(item, depth + 1)
        owned_params(params)
        if not isinstance(key, str) or not 1 <= len(key) <= 128 or not PREVIEW_ID.fullmatch(key):
            raise ValueError('invalid request_key')
        def provider(prompt, raw, mime, aspect):
            return invoke_edit_provider(prompt, raw, mime, aspect, self.edit_provider)
        assert self.bundle is not None
        return self.comparisons.render(category_id, aid, vid, method, params, key, self.bundle['library'], provider=provider, group=payload.get('group'))

    def _v2_thumbnail_sources(self, library, progress):
        """Pending is empty; old photographs are labeled independent; publication is explicit."""
        if not self.bundle:
            return library
        reviews = {}
        if self.comparisons:
            for cat in library['categories']:
                reviews[cat['id']] = self.comparisons.review(cat['id'])
        for cat in library['categories']:
            review = reviews.get(cat['id'], {})
            group_views = [view for view in review.get('groups', {}).values() if view.get('baseline')]
            views = ([review] if review.get('compatibility_view') else []) + group_views or [review]
            targeted_attributes = {attr['id'] for view in group_views for attr in view.get('attributes', [])}
            accepted, withheld = {}, set()
            for view in views:
                for artifact in view.get('artifacts', []):
                    if view.get('state') != 'published' or artifact['id'] not in view.get('published_artifact_ids', []):
                        continue
                    if view is review and artifact['attribute_id'] in targeted_attributes:
                        continue
                    target = (artifact['attribute_id'], artifact['value_id'])
                    if self.comparisons.publication_valid(cat['id'], artifact['id'], group=view.get('group')):
                        accepted[target] = artifact
                    else:
                        withheld.add(target)
            for attr in cat['attributes']:
                aid = attr['id']
                legacy = self.legacy_catalog.attributes.get(aid, {})
                old_values = {v['id']: v for v in legacy.get('values', [])}
                unchanged = len(old_values) == len(attr['values'])
                for value in attr['values']:
                    old = old_values.get(value['id'])
                    same = bool(old and old.get('steers') == value.get('steers') and value.get('legacy_semantic_match', True))
                    unchanged = unchanged and same
                    controlled = accepted.get((aid, value['id']))
                    control_only = attr.get('control') == 'range' or aid in {'age', 'gender'} or attr.get('preview_method') == 'control_only'
                    swatch = attr.get('control') == 'swatch' or attr.get('preview_method') == 'fabric_swatch'
                    if controlled and not control_only:
                        value.update(thumbnail_url=controlled['url'], example_url=controlled['url'],
                                     thumbnail_kind='comparison', thumbnail_status='ready', thumbnail_source='approved_comparison')
                    elif (aid, value['id']) in withheld:
                        value.update(thumbnail_url='', thumbnail_kind='pending', thumbnail_status='review_required',
                                     thumbnail_source='withheld_provenance')
                        for pointer in ('example_url', 'thumbnail'):
                            value.pop(pointer, None)
                    elif same and value.get('thumbnail_kind') == 'photographic' and not control_only and not swatch:
                        value['thumbnail_source'] = 'legacy_independent'
                    else:
                        illustration = value.get('illustration_url') or value.get('thumbnail_url')
                        if illustration and illustration in self.catalog.thumbnail_paths:
                            value['illustration_url'] = illustration
                        value.update(thumbnail_url='', thumbnail_kind='control_only' if control_only else 'swatch' if swatch else 'pending',
                                     thumbnail_status='control_only' if control_only else 'swatch' if swatch else 'pending',
                                     thumbnail_source='control_only' if control_only else 'palette' if swatch else 'pending')
                        value.pop('example_url', None)
                        value.pop('thumbnail', None)
                if not unchanged or attr.get('control') in {'range', 'swatch'} or aid == 'gender' or attr.get('thumbnail_kind') != 'contact_sheet':
                    attr.update(thumbnail_url='', thumbnail_kind='pending', thumbnail_status='pending')
                    attr.pop('thumbnail', None)
                else:
                    attr['thumbnail_source'] = 'legacy_independent'
                attr['comparison_state'] = review.get('groups', {}).get(attr.get('comparison_group'), review).get('state', 'draft')
        progress['value_completed'] = sum(v.get('thumbnail_status') == 'ready' for c in library['categories'] for a in c['attributes'] for v in a['values'])
        progress['attribute_completed'] = sum(bool(a.get('thumbnail_url')) for c in library['categories'] for a in c['attributes'])
        progress['control_only'] = sum(v.get('thumbnail_status') == 'control_only' for c in library['categories'] for a in c['attributes'] for v in a['values'])
        progress['swatches'] = sum(v.get('thumbnail_status') == 'swatch' for c in library['categories'] for a in c['attributes'] for v in a['values'])
        progress['review_required'] = any(v.get('thumbnail_status') in ('pending', 'review_required') for c in library['categories'] for a in c['attributes'] for v in a['values'])
        if progress['review_required']:
            progress['status'] = 'paused'
        library.update(catalog_version=2, thumbnail_mode='mixed', historical_library=self.historical_catalog.library,
                       historical_categories=self.historical_catalog.library['categories'],
                       retired=self.bundle.get('retired', {}), thumbnail_progress=progress)
        return library

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

    @staticmethod
    def _validated_comparison_png(raw):
        try:
            if not raw.startswith(b'\x89PNG\r\n\x1a\n'):
                return False
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(raw)) as image:
                    if image.format != 'PNG' or not 0 < image.width * image.height <= MAX_IMAGE_PIXELS:
                        return False
                    image.verify()
                with Image.open(io.BytesIO(raw)) as image:
                    image.load()
            return True
        except (ValueError, OSError, UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning):
            return False

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
            library = self._v2_thumbnail_sources(library, progress)
            return library, 'mixed' if self.bundle else 'illustrative', progress
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
        library = self._v2_thumbnail_sources(library, progress)
        return library, 'mixed' if self.bundle else 'photographic', progress

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

    def _guard(self, paid=False, mutation=False):
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
        if paid or mutation:
            origins = self.headers.get_all('Origin') or []
            if (mutation and len(origins) != 1) or len(origins) > 1 or (origins and origins[0] != 'http://' + host):
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
        if len(self.headers.get_all('Content-Type') or []) != 1:
            raise APIError(400, 'one Content-Type header is required')
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
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            comparison = re.fullmatch(r'/api/comparisons/([a-zA-Z0-9_-]+)/(base|mask|approve|preview|reopen)', path)
            self._guard(paid=path in {'/api/jobs', '/api/generate'},
                        mutation=path in {'/api/presets', '/api/presets/import', '/api/catalog/resolve'}
                        or path.startswith('/api/comparisons/')
                        or bool(self.app.bundle) and path in {'/api/jobs', '/api/generate'})
            if parsed.query and (comparison or path == '/api/catalog/resolve'):
                raise ValueError('query parameters are not supported for catalog/comparison mutations')
            if path not in {'/api/preview', '/api/jobs', '/api/generate', '/api/presets', '/api/presets/import', '/api/catalog/resolve'} and not comparison:
                raise APIError(404, 'not found')
            payload = self._body()
            if path == '/api/catalog/resolve':
                if set(payload) != {'draft'}:
                    raise ValueError('request must contain only draft')
                self._json(200, self.app.resolve_draft(payload['draft']))
                return
            if comparison:
                self._json(200, self.app.comparison_post(comparison[1], comparison[2], payload))
                return
            if path == '/api/presets':
                preset, created = self.app.presets.create(payload)
                self._json(201 if created else 200, preset)
                return
            if path == '/api/presets/import':
                self._json(200, self.app.presets.import_legacy(payload))
                return
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
        except PresetError as exc:
            self._json(exc.status, {'error': str(exc)})
        except ValueError as exc:
            # Engine uses ValueError for contract/budget guards; never leak provider exceptions.
            self._json(409 if type(exc).__name__ == 'ComparisonConflict' else 400, {'error': str(exc)})
        except QueueFull as exc:
            self._json(429, {'error': str(exc)})
        except Exception:
            self._json(502, {'error': SAFE_PROVIDER_ERROR})
        self.close_connection = True

    def do_DELETE(self):
        try:
            self._guard(mutation=True)
            path = urlparse(self.path).path
            if not path.startswith('/api/presets/'):
                raise APIError(404, 'not found')
            self._body()
            self.app.presets.delete(path[len('/api/presets/'):])
            self._json(200, {'presets': self.app.presets.list()})
        except APIError as exc:
            self._json(exc.status, {'error': exc.message})
        except PresetError as exc:
            self._json(exc.status, {'error': str(exc)})
        except ValueError as exc:
            self._json(400, {'error': str(exc)})
        except Exception:
            self._json(500, {'error': 'Unable to delete preset. Please retry.'})
        self.close_connection = True

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        try:
            self._guard()
            parsed = urlparse(self.path)
            path = unquote(parsed.path)
            if path == '/api/presets':
                self._json(200, {'presets': self.app.presets.list()})
                return
            if path == '/api/health':
                self._json(200, self.app.store.health())
                return
            if path == '/api/library':
                self._json(200, self.app.thumbnail_library()[0])
                return
            if path == '/api/catalog/versions':
                self._json(200, self.app.catalog_versions())
                return
            if path == '/api/comparisons/categories':
                categories = self.app.comparisons.list_categories(self.app.bundle['library']) if self.app.comparisons else []
                self._json(200, {'categories': categories})
                return
            asset_match = re.fullmatch(r'/api/comparisons/assets/([0-9a-f]{32})\.png', path)
            if asset_match:
                try:
                    def bounded_read(target):
                        handle, _ = self.app._preview_file(target, MAX_IMAGE_BYTES)
                        with handle:
                            return handle.read(MAX_IMAGE_BYTES + 1)
                    raw = self.app.comparisons.read_bytes(asset_match[1], reader=bounded_read) if self.app.comparisons else None
                    if raw is None or len(raw) > MAX_IMAGE_BYTES or self.app._validated_comparison_png(raw) is False:
                        raise ValueError('invalid comparison image')
                except (ValueError, OSError):
                    raise APIError(404, 'comparison asset unavailable')
                self._send(200, raw, 'image/png')
                return
            review_match = re.fullmatch(r'/api/comparisons/([a-zA-Z0-9_-]+)', path)
            if review_match:
                if self.app.comparisons is None or review_match[1] not in {c['id'] for c in self.app.catalog.library['categories']}:
                    raise APIError(404, 'comparison category not found')
                params = parse_qs(parsed.query, keep_blank_values=True, max_num_fields=2)
                if set(params) - {'attribute_id', 'group'} or any(len(v) != 1 or not v[0] or len(v[0]) > 200 for v in params.values()):
                    raise ValueError('invalid comparison review query')
                self._json(200, self.app.comparisons.review(review_match[1], **{k: v[0] for k, v in params.items()}))
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
                filters = self.app.historical_catalog.validate_map(filters, 'filters')
                aspect = get('aspect_ratio', '')
                if aspect and aspect not in XAI_ASPECT_RATIOS:
                    raise ValueError('unsupported aspect_ratio')
                try:
                    page, size = int(get('page', '1')), int(get('page_size', '24'))
                except ValueError:
                    raise ValueError('page and page_size must be integers')
                result = self.app.store.query(get('q', ''), page, size, filters, aspect)
                result['items'] = [self.app.gallery_labels(item) for item in result['items']]
                self._json(200, result)
                return
            for prefix, lookup in (('/api/jobs/', self.app.store.job), ('/api/images/', self.app.store.image)):
                if path.startswith(prefix):
                    image_id = path[len(prefix):]
                    if len(image_id) != 32 or any(ch not in '0123456789abcdef' for ch in image_id):
                        raise APIError(404, 'not found')
                    result = lookup(image_id)
                    if not result:
                        raise APIError(404, 'not found')
                    if prefix == '/api/images/':
                        result = self.app.gallery_labels(result)
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
