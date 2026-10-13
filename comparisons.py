"""Immutable comparison PNGs, local simulations, and bounded reference-edit pilots.

This module has no network adapter and never changes catalog publication pointers.
The server must resolve owned gallery IDs and enforce its Origin/authentication guards.
Approval calls represent explicit operator actions, including visual mask/artifact review.

Integration contract:
* ComparisonStore(root).list_categories(library) registers categories and their declared
  comparison_group records. review/set_base/approve/reopen accept optional attribute_id
  and group (both must agree); masks and renders resolve the selected attribute's group.
  A base with no selector establishes the older single-category compatibility view.
  Unscoped review returns groups and category summaries; targeted review returns one
  contract. Published group artifacts project only their own attribute/value targets.
* reopen requires expected_contract_hash and a nonempty approval_note, archives the
  previous review, advances its contract revision and enables draft base/mask edits.
  Raw replacements of approved reviews reject. Assets and request tombstones survive.
* approve stages are contract/pilot/publish/expansion. Contract approval starts a
  bounded cycle in draft; expansion starts another only after accepted pilot or
  publication, with a nonempty note and cap 0..3. Public cycle={id,cap,used} records
  current usage; budget.used remains total consumed attempts, including failures.
  Request keys stay unique per category across groups, cycles and revisions.
* set_base receives a server-resolved owned path, never a browser-supplied filename. Crop
  is normalized [left, top, right, bottom]. Subject woman/adult metadata is declared,
  never inferred from pixels. Comparison outputs cannot be substituted as new references.
* set_mask takes normalized polygon points. Its registered overlay MUST be shown to the
  operator; approve('contract') affirms the baseline and masks. Local candidates may
  render in draft; pilot approval accepts individual artifacts, and publish accepts only
  those same accepted artifacts. No catalog source pointer is changed by this module.
* render uses each attribute's preview_method and value's colour.hex/preview_params.
  simulated_optics dispatches params.effect to a specifically labeled supported method.
  METHOD_ALIASES bridges the catalog's simulated_* names without changing the declared
  API method. local_parameter_schema is embedded in generated catalog attributes.
  Catalog-declared neutral preview_baseline values return status/effect_role='baseline',
  exact original pixels and a baseline label; they cannot pass effect-publication gates.
  Explicit global scopes alone permit wholeframe optical masks; swatch scope alone
  permits a synthetic no-person fabric reference. Other methods require drawn masks.
* Preflight errors raise ValueError. An attempted provider failure returns a receipt
  object with id/url None and status='failed'; retries return that same receipt and never
  invoke the provider again. In-flight reservations also fail closed after a crash.
* assets are addressed by registered 32hex IDs, optionally suffixed .png. The server's
  exact GET/HEAD /api/comparisons/assets/<32hex>.png route must preserve private guards.
  Pixel equality is a compositing check; identity, anatomy and mask correctness still
  require explicit operator review of the original, overlay and candidate at 1x/2x.
"""
import base64
import colorsys
import hashlib
import io
import json
import math
import os
import random
import re
import sqlite3
import stat
import time
import uuid
import warnings
from contextlib import contextmanager
from pathlib import Path

from PIL import Image, ImageCms, ImageDraw, ImageFilter, ImageOps
from prompt_policy import REFERENCE_AESTHETIC_LOCK


MAX_BYTES = 32 * 1024 * 1024
MAX_PIXELS = 16_000_000
MAX_SIDE = 8192
METHOD_VERSION = 'anchored-png-2'
METHOD_ALIASES = {
    'simulated_fov_crop': 'focal_fov', 'simulated_depth_blur': 'aperture_blur',
    'simulated_motion_blur': 'motion_blur', 'simulated_grain': 'grain',
    'simulated_focus': 'focus_depth_blur', 'simulated_white_balance': 'white_balance',
    'simulated_tone_curve': 'gentlehighlight_rolloff', 'simulated_color_grade': 'color_grade',
    'simulated_contrast': 'contrast', 'simulated_palette': 'palette',
    'simulated_editorial_grade': 'editorial_grade',
}
LOCAL_METHODS = {
    'masked_recolor': ('Masked pigment recolor preserving luminance texture', False,
                       'Color targets are illustrative RGB recipes, not calibrated pigments; review strands, halos and texture.'),
    'fabric_swatch': ('Simulated woven texture swatch', True,
                      'Illustrative swatch, not a garment render or measured fabric appearance.'),
    'grain': ('Simulated seeded image grain', True,
              'Digital noise approximation, not measured film or sensor behavior.'),
    'white_balance': ('Simulated whole-scene white balance', True,
                      'RGB channel adjustment intentionally changes colors; not a calibrated RAW temperature conversion.'),
    'gentlehighlight_rolloff': ('Simulated gentle highlight rolloff', True,
                               'Compresses existing highlights; cannot recover clipped source detail.'),
    'focal_fov': ('Simulated fixed-camera field-of-view crop', True,
                  'Center crop resampled into the comparison frame; fixed camera, no perspective or optical-detail claim.'),
    'focus_depth_blur': ('Simulated focus blur with declared depth assumption', True,
                         'One mask-defined depth plane; cannot recreate lost source detail or infer scene depth.'),
    'aperture_blur': ('Simulated aperture blur at constant brightness', True,
                      'One mask-defined depth plane and constant brightness; not measured bokeh, exposure or lens behavior.'),
    'motion_blur': ('Simulated directional moving-region blur', True,
                    'Only the drawn moving/swept footprint changes; shutter/exposure and physical motion are approximations.'),
    'color_grade': ('Simulated global colour grade on the original scene', True,
                    'Illustrative RGB chroma and tonal tint; all scene colours may change, with no camera or film equivalence.'),
    'contrast': ('Simulated global contrast and tone remapping', True,
                 'Remaps existing tones; no recovered detail, scene geometry or lighting reconstruction.'),
    'palette': ('Simulated global palette relationship on the original scene', True,
                'Soft hue mapping to illustrative RGB anchors; changes scene colours, without replacing garments or props.'),
    'editorial_grade': ('Simulated global editorial grade and contrast recipe', True,
                        'Applies the disclosed colour and contrast components to the original scene; no expression, garment or prop generation.'),
}
GLOBAL_METHODS = {'grain', 'white_balance', 'gentlehighlight_rolloff', 'focal_fov',
                  'color_grade', 'contrast', 'palette', 'editorial_grade'}
PARAM_DEFAULTS = {
    'masked_recolor': {}, 'fabric_swatch': {'weave_scale': 4},
    'grain': {'amount': 10, 'seed': 0, 'shadow_bias': 0, 'soften': 0}, 'white_balance': {'temperature': .2, 'tint': 0},
    'gentlehighlight_rolloff': {'strength': .5, 'threshold': .7}, 'focal_fov': {'factor': 1.5},
    'focus_depth_blur': {'radius': 2}, 'aperture_blur': {'radius': 2},
    'motion_blur': {'distance': 5, 'direction': 0}, 'reference_edit': {},
    'color_grade': {'saturation': 1, 'temperature': 0, 'tint': 0, 'lift': 0,
                    'shadow_tint': [0, 0, 0], 'highlight_tint': [0, 0, 0]},
    'contrast': {'slope': 1, 'midtones': 0, 'shadows': 0, 'highlights': 0},
    'palette': {'strength': .4, 'saturation': 1},
    'editorial_grade': {'mix': 1},
}
PARAM_KEYS = {
    'masked_recolor': {'colour', 'color', 'hex'},
    'fabric_swatch': {'colour', 'color', 'hex', 'weave_scale', 'source_crop'},
    'grain': {'amount', 'seed', 'shadow_bias', 'soften'}, 'white_balance': {'temperature', 'tint'},
    'gentlehighlight_rolloff': {'strength', 'threshold'}, 'focal_fov': {'factor'},
    'focus_depth_blur': {'radius', 'depth_assumption'},
    'aperture_blur': {'radius', 'depth_assumption'},
    'motion_blur': {'distance', 'direction', 'moving_region'}, 'reference_edit': set(),
    'color_grade': {'saturation', 'temperature', 'tint', 'lift', 'shadow_tint', 'highlight_tint'},
    'contrast': {'slope', 'midtones', 'shadows', 'highlights'},
    'palette': {'anchors', 'strength', 'saturation'},
    'editorial_grade': {'grade', 'contrast', 'mix'},
}

# The generated catalog exposes this schema to clients. It is also the engine's
# numeric validation source; sources, masks, geometry and prompts are never knobs.
PARAM_RANGES = {
    'weave_scale': (2, 32), 'amount': (0, 64), 'seed': (0, 2**32 - 1),
    'shadow_bias': (0, 1), 'soften': (0, 4), 'temperature': (-1, 1), 'tint': (-1, 1),
    'strength': (0, 1), 'threshold': (0, .99), 'factor': (1, 6), 'radius': (0, 32),
    'distance': (0, 64), 'direction': (-360, 360), 'saturation': (0, 2),
    'lift': (-64, 64), 'slope': (.25, 2), 'midtones': (-1, 1),
    'shadows': (-64, 64), 'highlights': (-64, 64), 'mix': (0, 1),
}


def local_parameter_schema(method, *, contract_assertions=True):
    """JSON-ready parameter schema for the exact catalog method/API declaration."""
    effective = METHOD_ALIASES.get(method, method)
    properties = {}
    for key in sorted(PARAM_KEYS[effective]):
        if key in PARAM_RANGES:
            low, high = PARAM_RANGES[key]
            spec = {'type': 'integer' if key == 'seed' else 'number', 'minimum': low, 'maximum': high}
        elif key in ('grade', 'contrast'):
            spec = local_parameter_schema('color_grade' if key == 'grade' else 'contrast', contract_assertions=False)
        elif key in ('shadow_tint', 'highlight_tint'):
            spec = {'type': 'array', 'minItems': 3, 'maxItems': 3,
                    'items': {'type': 'number', 'minimum': -64, 'maximum': 64}}
        elif key == 'anchors':
            spec = {'type': 'array', 'minItems': 1, 'maxItems': 8,
                    'items': {'type': 'string', 'pattern': '^#[0-9a-fA-F]{6}$'}}
        elif key == 'colour':
            spec = {'type': 'object', 'properties': {'hex': {'type': 'string', 'pattern': '^#[0-9a-fA-F]{6}$'}},
                    'required': ['hex'], 'additionalProperties': False}
        elif key == 'source_crop':
            spec = {'type': 'array', 'minItems': 4, 'maxItems': 4,
                    'items': {'type': 'number', 'minimum': 0, 'maximum': 1}}
        elif key in ('color', 'hex'):
            spec = {'type': 'string', 'pattern': '^#[0-9a-fA-F]{6}$'}
        else:
            spec = {'type': 'string', 'minLength': 1, 'maxLength': 1000}
        if key in PARAM_DEFAULTS[effective]:
            spec['default'] = PARAM_DEFAULTS[effective][key]
        properties[key] = spec
    if contract_assertions:
        for key in ('base_sha256', 'mask_sha256'):
            properties[key] = {'type': 'string', 'pattern': '^[0-9a-f]{64}$'}
    required = {'masked_recolor': ['colour'], 'fabric_swatch': ['colour'],
                'focus_depth_blur': ['depth_assumption'], 'aperture_blur': ['depth_assumption'],
                'motion_blur': ['moving_region'], 'palette': ['anchors'],
                'editorial_grade': ['grade', 'contrast']}.get(effective, [])
    return {'type': 'object', 'additionalProperties': False, 'properties': properties,
            'required': required, 'effective_method': effective,
            'applies_to': 'effective parameters after selected catalog value merge; request params may be empty',
            'parameter_precedence': 'attribute defaults, selected value, explicit request overrides'}
LOCKS = ['identity', 'face_landmarks', 'skin', 'iris', 'outfit_design', 'outfit_color',
         'background', 'pose', 'head_angle', 'gaze', 'light', 'camera', 'crop', 'non_target_traits']


def _json(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError('Expected finite JSON data') from exc


def _hash(raw):
    return hashlib.sha256(raw).hexdigest()


def _digest(value):
    return _hash(_json(value).encode())


def _text(value, field, limit=200):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or '\x00' in value:
        raise ValueError(f'Invalid {field}')
    return value


def _number(value, field, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f'{field} must be finite and between {low} and {high}')
    return value


def _safe_file(path, parent):
    """Check containment and each path component without accepting symlinks."""
    path, parent = Path(os.path.abspath(path)), Path(os.path.abspath(parent))
    try:
        path.relative_to(parent)
    except ValueError:
        raise ValueError('Image path is outside the owned root') from None
    for item in (path, *path.parents):
        if item.is_symlink():
            raise ValueError('Symlink paths are not allowed')
    if not path.is_file():
        raise ValueError('Missing image file')
    return path


def _read_file(path):
    # Open each directory relative to a pinned descriptor. An atomic symlink
    # replacement at any component must never redirect the validated read.
    path = Path(os.path.abspath(path))
    directory = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for component in path.parts[1:-1]:
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
        descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    finally:
        os.close(directory)
    with os.fdopen(descriptor, 'rb') as stream:
        metadata = os.fstat(stream.fileno())
        if not stat.S_ISREG(metadata.st_mode) or not 0 < metadata.st_size <= MAX_BYTES:
            raise ValueError('Invalid or oversized image file')
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError('Image bytes exceed the bounded decode limit')
    return raw


def _decode(raw, normalize=False):
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_BYTES:
        raise ValueError('Invalid or oversized image bytes')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as image:
                if image.format not in ('PNG', 'JPEG', 'WEBP'):
                    raise ValueError('Unsupported image format')
                width, height = image.size
                if min(width, height) < 2 or max(width, height) > MAX_SIDE or width * height > MAX_PIXELS:
                    raise ValueError('Image dimensions exceed bounded decode limits')
                if getattr(image, 'n_frames', 1) != 1:
                    raise ValueError('Animated/multiframe images are not comparison sources')
                image.load()
                if normalize:
                    image = ImageOps.exif_transpose(image)
                    alpha = image.convert('RGBA').getchannel('A')
                    icc = image.info.get('icc_profile')
                    if icc:
                        # An invalid profile fails closed rather than silently changing normalization.
                        rgb = ImageCms.profileToProfile(image.convert('RGB'),
                              ImageCms.ImageCmsProfile(io.BytesIO(icc)), ImageCms.createProfile('sRGB'), outputMode='RGB')
                        image = rgb.convert('RGBA')
                        image.putalpha(alpha)
                return image.convert('RGBA')
    except (OSError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning, ImageCms.PyCMSError, TypeError) as exc:
        raise ValueError('Invalid or unsafe image decode') from exc


def _png(image):
    out = io.BytesIO()
    image.save(out, 'PNG', optimize=False, compress_level=6)
    raw = out.getvalue()
    if len(raw) > MAX_BYTES:
        raise ValueError('Normalized PNG exceeds asset size limit')
    return raw


def _crop_box(crop, size):
    """Normalized [left, top, right, bottom], or an object with these fields."""
    if isinstance(crop, dict):
        if set(crop) != {'left', 'top', 'right', 'bottom'}:
            raise ValueError('Crop must specify left, top, right, bottom')
        crop = [crop[k] for k in ('left', 'top', 'right', 'bottom')]
    if not isinstance(crop, (tuple, list)) or len(crop) != 4:
        raise ValueError('Crop must be four normalized bounds')
    crop = [_number(x, 'crop coordinate', 0, 1) for x in crop]
    left, top, right, bottom = crop
    if left >= right or top >= bottom:
        raise ValueError('Crop must have positive area')
    w, h = size
    box = (round(left * w), round(top * h), round(right * w), round(bottom * h))
    if box[2] - box[0] < 2 or box[3] - box[1] < 2:
        raise ValueError('Crop is too small')
    return box, crop


def _scope(attribute):
    return attribute.get('preview_scope') in ('global', 'whole_image', 'wholeframe', 'whole_frame')


def _pixels(image):
    # Pillow 12.1 replaced getdata; retain compatibility with older installed Pillow.
    method = getattr(image, 'get_flattened_data', image.getdata)
    return method()


def _category_map(library):
    if not isinstance(library, dict) or not isinstance(library.get('categories'), list):
        raise ValueError('Invalid category library')
    mapped = {}
    for cat in library['categories']:
        if not isinstance(cat, dict):
            raise ValueError('Invalid category')
        ident = _text(cat.get('id'), 'category ID')
        if ident in mapped or not isinstance(cat.get('attributes'), list):
            raise ValueError('Duplicate category or invalid attributes')
        attrs = {}
        for attr in cat['attributes']:
            attr_id = _text(attr.get('id'), 'attribute ID')
            if attr_id in attrs:
                raise ValueError('Duplicate attribute ID')
            attrs[attr_id] = json.loads(_json(attr))
        mapped[ident] = {'id': ident, 'name': cat.get('name', ident), 'attributes': attrs,
                         'locked_fields': cat.get('locked_fields', LOCKS),
                         'allowed_changes': cat.get('allowed_changes', ['selected target inside its reviewed footprint only'])}
    return mapped


def list_categories(library):
    """Pure library summaries; ComparisonStore.list_categories adds stored review state."""
    return [{'id': c['id'], 'name': c['name'], 'attribute_count': len(c['attributes'])}
            for c in _category_map(library).values()]


def _declarations(value, field):
    if (not isinstance(value, list) or len(value) > 100 or
            any(not isinstance(v, str) or not v.strip() or len(v) > 1000 for v in value) or
            len(set(value)) != len(value)):
        raise ValueError('Invalid contract ' + field)
    return list(value)


def _group_definition(cat, group):
    attrs = {aid: attr for aid, attr in cat['attributes'].items() if attr.get('comparison_group') == group}
    declarations = []
    requirements = []
    for attr in attrs.values():
        contract = attr.get('preview_contract', {})
        if not isinstance(contract, dict):
            raise ValueError('Invalid target preview contract')
        locks = _declarations(contract.get('locked_fields', cat['locked_fields']), 'locked_fields')
        changes = _declarations(contract.get('allowed_changes', cat['allowed_changes']), 'allowed_changes')
        declarations.append((locks, changes))
        for requirement in _declarations(contract.get('baseline_requirements', []), 'baseline_requirements'):
            if requirement not in requirements:
                requirements.append(requirement)
    locks, changes = declarations[0]
    if any((set(ls), set(cs)) != (set(locks), set(changes)) for ls, cs in declarations[1:]):
        # Same-scene controls keep per-method target declarations. Native
        # edits sharing a record must agree: an operator cannot approve two
        # incompatible native contracts by their widened union. Local methods
        # are bounded implementations whose consequences stay in each receipt.
        methods = {}
        all_locks = set().union(*(set(ls) for ls, _ in declarations))
        for attr, (ls, cs) in zip(attrs.values(), declarations):
            method = METHOD_ALIASES.get(attr.get('preview_method'), attr.get('preview_method'))
            if method == 'simulated_optics':
                method = attr.get('effect', attr['id'])
            # Only the known local implementations can relax these explicit
            # invariants. Other differences would silently widen the group.
            relaxed = ({'crop'} if method == 'focal_fov' else
                       {'non_target_pigment', 'wardrobe_color', 'skin', 'iris', 'outfit_color'}
                       if method in {'white_balance', 'gentlehighlight_rolloff', 'color_grade',
                                     'contrast', 'palette', 'editorial_grade'} else set())
            if all_locks - set(ls) - relaxed:
                raise ValueError('Incompatible shared comparison locks')
            declaration = (set(ls), set(cs))
            if method in methods and methods[method] != declaration:
                raise ValueError('Incompatible shared comparison contracts')
            methods[method] = declaration
        locks = [lock for lock in locks if all(lock in ls for ls, _ in declarations)]
        changes = list(dict.fromkeys(change for _, cs in declarations for change in cs))
    return {**cat, 'id': cat['id'] + '::' + group, 'attributes': attrs,
            'locked_fields': locks, 'allowed_changes': changes, 'baseline_requirements': requirements}


class ComparisonStore:
    def __init__(self, root):
        self.root = Path(os.path.abspath(root))
        for parent in (self.root, *self.root.parents):
            if parent.is_symlink():
                raise ValueError('Comparison root cannot contain symlinks')
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / 'comparisons.sqlite3'
        self.output_dir = self.root / 'generated' / 'comparisons'
        for path in (self.root / 'generated', self.output_dir, self.db_path):
            if path.is_symlink():
                raise ValueError('Comparison storage cannot contain symlinks')
        self.output_dir.mkdir(parents=True, exist_ok=True)
        with self._transaction() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS categories(id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS comparison_assets(id TEXT PRIMARY KEY, sha256 TEXT NOT NULL,
                    width INTEGER NOT NULL, height INTEGER NOT NULL, role TEXT NOT NULL, pixel_sha256 TEXT);
                CREATE TABLE IF NOT EXISTS comparison_requests(category_id TEXT NOT NULL, request_key TEXT NOT NULL,
                    digest TEXT NOT NULL, contract_hash TEXT NOT NULL, status TEXT NOT NULL,
                    result TEXT, error TEXT, receipt TEXT NOT NULL, created_at REAL NOT NULL,
                    PRIMARY KEY(category_id, request_key));
                CREATE TABLE IF NOT EXISTS history(id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category_id TEXT NOT NULL, event TEXT NOT NULL, data TEXT NOT NULL, created_at REAL NOT NULL);
            ''')
            columns = {row['name'] for row in db.execute('PRAGMA table_info(comparison_assets)')}
            if 'pixel_sha256' not in columns:
                db.execute('ALTER TABLE comparison_assets ADD COLUMN pixel_sha256 TEXT')
            for row in db.execute("SELECT id FROM comparison_assets WHERE role='output' AND pixel_sha256 IS NULL").fetchall():
                raw = self._read_bytes(db, row['id'])
                if raw is None:
                    raise ValueError('Corrupt comparison output cannot be migrated')
                digest = _hash(_decode(raw).tobytes())
                db.execute('UPDATE comparison_assets SET pixel_sha256=? WHERE id=?', (digest, row['id']))
        # Read only the requested catalog files, never runtime/provider configuration.
        if (self.root / 'catalog' / 'v2' / 'library.json').is_file():
            try:
                from catalog_v2 import load_bundle
            except ImportError:
                path = self.root / 'catalog' / 'v2' / 'library.json'
                library = json.loads(_read_file(_safe_file(path, self.root)))
            else:
                library = load_bundle(self.root)['library']
            self.list_categories(library)
        elif (self.root / 'library.json').is_file():
            library = json.loads(_read_file(_safe_file(self.root / 'library.json', self.root)))
            self.list_categories(library)

    @contextmanager
    def _transaction(self, read_only=False):
        if self.db_path.is_symlink():
            raise ValueError('Comparison database cannot be a symlink')
        db = sqlite3.connect(self.db_path, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            db.execute('BEGIN' if read_only else 'BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def _get(self, db, category_id):
        _text(category_id, 'category ID')
        row = db.execute('SELECT data FROM categories WHERE id=?', (category_id,)).fetchone()
        if row is None:
            raise ValueError('Unknown comparison category')
        return json.loads(row['data'])

    def _save(self, db, record):
        db.execute('INSERT INTO categories(id,data) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data',
                   (record['id'], _json(record)))

    def _event(self, db, record, event, data):
        db.execute('INSERT INTO history(category_id,event,data,created_at) VALUES(?,?,?,?)',
                   (record['id'], event, _json(data), time.time()))

    def _contract(self, record):
        contract = {k: record[k] for k in ('id', 'definition', 'baseline', 'masks', 'locked_fields', 'allowed_changes')}
        if 'revision' in record:
            contract['revision'] = record['revision']
        return _digest(contract)

    def _invalidate(self, db, record, reason):
        self._event(db, record, reason, record)
        budget = dict(record['budget'])
        budget['cap'] = 0
        record.update(state='draft', approvals=[], artifacts=[], published_artifact_ids=[],
                      budget=budget)
        record['contract_hash'] = self._contract(record)

    def list_categories(self, library):
        categories = _category_map(library)
        definitions = dict(categories)
        for cat in categories.values():
            groups = {}
            for aid, attr in cat['attributes'].items():
                group = attr.get('comparison_group')
                if group:
                    groups.setdefault(group, {})[aid] = attr
            for group, attrs in groups.items():
                key = cat['id'] + '::' + group
                definitions[key] = _group_definition(cat, group)
        summaries = []
        with self._transaction() as db:
            for cat in definitions.values():
                row = db.execute('SELECT data FROM categories WHERE id=?', (cat['id'],)).fetchone()
                if row:
                    record = json.loads(row['data'])
                    if record['definition'] != cat:
                        record['definition'] = cat
                        record['locked_fields'] = cat['locked_fields']
                        record['allowed_changes'] = cat['allowed_changes']
                        # Changed metadata cannot adopt previously reviewed masks.
                        record['masks'] = {}
                        self._invalidate(db, record, 'catalog_changed')
                else:
                    record = dict(id=cat['id'], name=cat['name'], definition=cat, state='draft',
                                  baseline=None, masks={}, artifacts=[], approvals=[],
                                  locked_fields=cat['locked_fields'], allowed_changes=cat['allowed_changes'],
                                  budget={'cap': 0, 'used': 0}, published_artifact_ids=[])
                    record['contract_hash'] = self._contract(record)
                self._save(db, record)
                summaries.append({'id': cat['id'], 'name': cat['name'], 'state': record['state'],
                                  'attribute_count': len(cat['attributes']), 'contract_hash': record['contract_hash'],
                                  'baseline': record['baseline'], 'artifact_count': len(record['artifacts']),
                                  'budget': record['budget']})
        result = []
        for item in summaries:
            if item['id'] in categories:
                review = self.review(item['id'])
                result.append({**item, 'state': review['state'], 'groups': {group: {k: view[k] for k in
                    ('group', 'state', 'contract_hash', 'baseline', 'budget', 'cycle')} for group, view in review['groups'].items()}})
        return result

    def _target(self, db, category_id, attribute_id=None, group=None, force_group=False):
        root = self._get(db, category_id)
        attrs = root['definition']['attributes']
        if attribute_id is not None and (not isinstance(attribute_id, str) or attribute_id not in attrs):
            raise ValueError('Unknown comparison attribute')
        declared = attrs[attribute_id].get('comparison_group') if attribute_id else None
        if group is not None and (not isinstance(group, str) or group not in
                {a.get('comparison_group') for a in attrs.values()} or (declared and group != declared)):
            raise ValueError('Comparison group does not match the selected attribute')
        explicit_group = group is not None
        group = group or declared
        if not group:
            return category_id
        key = category_id + '::' + group
        record = self._get(db, key)
        # Explicit targeted bases establish group ownership. Older callers that
        # chose one category baseline continue through the compatibility contract.
        if not force_group and not explicit_group and record['baseline'] is None and root['baseline'] is not None:
            return category_id
        return key

    def review(self, category_id, attribute_id=None, group=None):
        with self._transaction(read_only=True) as db:
            key = self._target(db, category_id, attribute_id, group) if attribute_id or group else category_id
            record = self._review_record(db, key, category_id)
            if attribute_id or group:
                return record
            groups = {}
            for attr in record['definition']['attributes'].values():
                declared = attr.get('comparison_group')
                if declared and declared not in groups:
                    groups[declared] = self._review_record(db, category_id + '::' + declared, category_id)
            record['groups'] = groups
            record['compatibility_view'] = record['baseline'] is not None
            if groups and record['baseline'] is None:
                record['state'] = 'published' if all(g['state'] == 'published' for g in groups.values()) else 'draft'
                record['artifacts'] = [a for g in groups.values() for a in g['artifacts']]
                record['attempts'] = sorted([a for g in groups.values() for a in g['attempts']], key=lambda a: a['receipt']['created_at'])
                record['history'] += sorted([{**h, 'group': group} for group, g in groups.items() for h in g['history']], key=lambda h: h['created_at'])
                record['published_artifact_ids'] = [ident for g in groups.values() for ident in g['published_artifact_ids']]
                record['budget'] = {'cap': sum(g['budget']['cap'] for g in groups.values()),
                                    'used': sum(g['budget']['used'] for g in groups.values())}
            return record

    def _review_record(self, db, key, category_id):
        record = self._get(db, key)
        contract_valid = self._contract(record) == record['contract_hash']
        record['attributes'] = list(record['definition']['attributes'].values())
        record['baseline_requirements'] = self._baseline_requirements(record)
        record['history'] = [{'event': row['event'], 'created_at': row['created_at'], 'data': json.loads(row['data'])}
                             for row in db.execute('SELECT * FROM history WHERE category_id=? ORDER BY id', (key,))]
        record['attempts'] = [dict(request_key=row['request_key'], status=row['status'], error=row['error'],
                                   contract_hash=row['contract_hash'], receipt=json.loads(row['receipt']))
                              for row in db.execute('SELECT * FROM comparison_requests WHERE category_id=? ORDER BY created_at', (category_id,))
                              if json.loads(row['receipt']).get('group') == (key.split('::', 1)[1] if '::' in key else None)]
        record['category_id'] = category_id
        record['id'] = category_id
        record['group'] = key.split('::', 1)[1] if '::' in key else None
        budget = record['budget']
        record['cycle'] = {'id': budget.get('cycle_id', 0), 'cap': budget['cap'], 'used': budget.get('cycle_used', budget['used'])}
        if key == category_id:
            record['budget'] = {'cap': budget['cap'], 'used': budget['used']}
        record['baseline_integrity'] = False
        if record['baseline'] is not None and contract_valid:
            try:
                self._baseline_attestation(record)
                self._image(db, record['baseline'])
                record['baseline_integrity'] = True
            except (ValueError, OSError):
                pass
        return record

    def reopen(self, category_id, expected_contract_hash, approval_note, attribute_id=None, group=None):
        _text(approval_note, 'reopen note', 4000)
        with self._transaction() as db:
            key = self._target(db, category_id, attribute_id, group)
            record = self._get(db, key)
            if expected_contract_hash != record['contract_hash'] or self._contract(record) != record['contract_hash']:
                raise ValueError('Stale or incorrect expected contract hash')
            if record['state'] == 'draft':
                raise ValueError('Only an approved group/category can be reopened')
            previous = json.loads(_json(record))
            self._event(db, record, 'operator_reopen', {'note': approval_note, 'expected_contract_hash': expected_contract_hash, 'previous': previous})
            record['revision'] = record.get('revision', 0) + 1
            self._invalidate(db, record, 'reopened_contract_archived')
            self._save(db, record)
        return self.review(category_id, attribute_id, group)

    def publication_valid(self, category_id, artifact_id, attribute_id=None, group=None):
        with self._transaction(read_only=True) as db:
            key = self._target(db, category_id, attribute_id, group)
            record = self._get(db, key)
            try:
                if record['state'] != 'published' or artifact_id not in record['published_artifact_ids']:
                    return False
                artifact = next(a for a in record['artifacts'] if a['id'] == artifact_id)
                if not artifact['accepted']:
                    return False
                self._integrity(db, record)
                self._artifact_integrity(db, record, artifact, publishing=True)
                approval = next((a for a in reversed(record['approvals']) if a['stage'] == 'publish' and artifact_id in a['artifact_ids']), None)
                self._approval_integrity(record, approval, record['budget'].get('cycle_id', 0), artifact)
                mask = record['masks'][artifact['attribute_id']]
                return bool(approval and approval['contract_hash'] == record['contract_hash']
                    and approval['baseline_sha256'] == record['baseline']['sha256']
                    and approval['mask_hashes'].get(artifact['attribute_id']) == mask['sha256']
                    and approval['overlay_hashes'].get(artifact['attribute_id']) == mask['overlay_sha256']
                    and approval['artifact_hashes'].get(artifact_id) == artifact['receipt']['output_sha256'])
            except (ValueError, KeyError, StopIteration, TypeError, OSError):
                return False

    def _artifact_integrity(self, db, record, artifact, publishing=False):
        receipt = artifact['receipt']
        mask = record['masks'][artifact['attribute_id']]
        baseline = record['baseline']
        if (self._contract(record) != record['contract_hash'] or receipt['contract_hash'] != record['contract_hash']
                or receipt['base_sha256'] != baseline['sha256'] or receipt['mask_sha256'] != mask['sha256']
                or receipt['mask_overlay_sha256'] != mask['overlay_sha256']
                or receipt['locked_params']['base_asset_id'] != baseline['asset_id']
                or receipt['locked_params']['mask_asset_id'] != mask['asset_id']
                or receipt['outside_delta'] != 0 or receipt['inside_change']['changed_pixels'] == 0
                or artifact.get('receipt_sha256', _digest(receipt)) != _digest(receipt)):
            raise ValueError('Artifact provenance, receipt hash or target-effect mismatch')
        self._cycle_approval(record, record['budget'].get('cycle_id', 0))
        contract_approval = (self._cycle_approval(record, receipt['cycle_id'])
                             if receipt.get('approval') is not None else None)
        if receipt.get('approval') != contract_approval or (receipt.get('provider_attempt_reserved') and contract_approval is None):
            raise ValueError('Artifact contract approval provenance mismatch')
        row = db.execute('SELECT * FROM comparison_requests WHERE category_id=? AND request_key=?',
                         (receipt['target']['category_id'], receipt['request_key'])).fetchone()
        if not row or row['status'] != 'done' or _digest(json.loads(row['receipt'])) != _digest(receipt):
            raise ValueError('Stored attempt receipt mismatch')
        attr = record['definition']['attributes'][artifact['attribute_id']]
        value = next(v for v in attr['values'] if v['id'] == artifact['value_id'])
        if (receipt.get('target_contract') != attr.get('preview_contract', {}) or
                receipt.get('locked_fields') != record['locked_fields'] or
                receipt.get('allowed_changes') != record['allowed_changes'] or
                receipt.get('baseline_confirmations', []) != baseline.get('baseline_confirmations', []) or
                receipt.get('recipe_components') != value.get('recipe', {}).get('selections')):
            raise ValueError('Artifact target contract or recipe consequences mismatch')
        canonical = self._catalog_params(attr, value, artifact['method'])
        effective = receipt.get('effective_params', receipt['params'])
        comparable = lambda params: {k: v for k, v in params.items() if k not in ('base_sha256', 'mask_sha256')}
        if publishing and (canonical is None or comparable(canonical) != comparable(effective)):
            raise ValueError('Custom settings cannot publish as a canonical catalog target')
        self._image(db, {'asset_id': artifact['id'], 'sha256': receipt['output_sha256'],
                         'width': receipt['dimensions'][0], 'height': receipt['dimensions'][1]})
        if publishing:
            approval = next((a for a in reversed(record['approvals']) if a['stage'] == 'pilot' and artifact['id'] in a['artifact_ids']), None)
            self._approval_integrity(record, approval, record['budget'].get('cycle_id', 0), artifact)
            if not approval or (approval['contract_hash'] != record['contract_hash']
                    or approval['baseline_sha256'] != baseline['sha256']
                    or approval['mask_hashes'].get(artifact['attribute_id']) != mask['sha256']
                    or approval['overlay_hashes'].get(artifact['attribute_id']) != mask['overlay_sha256']
                    or approval['artifact_hashes'].get(artifact['id']) != receipt['output_sha256']):
                raise ValueError('Pilot approval provenance mismatch')

    def _asset(self, db, asset_id):
        snapshot = self._asset_snapshot(db, asset_id)
        return snapshot[0] if snapshot else None

    def _asset_snapshot(self, db, asset_id, reader=None):
        if not isinstance(asset_id, str):
            return None
        match = re.fullmatch(r'([0-9a-f]{32})(?:\.png)?', asset_id)
        if not match:
            return None
        asset_id = match.group(1)
        row = db.execute('SELECT * FROM comparison_assets WHERE id=?', (asset_id,)).fetchone()
        if row is None:
            return None
        try:
            path = _safe_file(self.output_dir / (asset_id + '.png'), self.output_dir)
            raw = (reader or _read_file)(path)
            _safe_file(path, self.output_dir)
            if not isinstance(raw, bytes) or _hash(raw) != row['sha256'] or not raw.startswith(b'\x89PNG\r\n\x1a\n'):
                return None
            image = _decode(raw)
            if image.size != (row['width'], row['height']):
                return None
            return path, raw
        except (OSError, ValueError):
            return None

    def asset(self, asset_id):
        with self._transaction(read_only=True) as db:
            return self._asset(db, asset_id)

    def _read_bytes(self, db, asset_id, reader=None):
        snapshot = self._asset_snapshot(db, asset_id, reader)
        return snapshot[1] if snapshot else None

    def read_bytes(self, asset_id, reader=None):
        """Return bounded immutable PNG bytes validated against their registration.

        Optional reader lets HTTP apply its stricter limits to the same snapshot.
        asset() remains a compatible path lookup, not a promise about later reads.
        """
        with self._transaction(read_only=True) as db:
            return self._read_bytes(db, asset_id, reader)

    def _register(self, db, image, role):
        raw = _png(image)
        ident = uuid.uuid4().hex
        path = self.output_dir / (ident + '.png')
        if self.output_dir.is_symlink() or (self.root / 'generated').is_symlink():
            raise ValueError('Comparison asset directory cannot be a symlink')
        # O_EXCL is intentional: immutable files are never replaced or re-used.
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            db.execute('INSERT INTO comparison_assets(id,sha256,width,height,role,pixel_sha256) VALUES(?,?,?,?,?,?)',
                       (ident, _hash(raw), image.width, image.height, role, _hash(image.convert('RGBA').tobytes())))
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        return {'asset_id': ident, 'url': '/api/comparisons/assets/' + ident + '.png',
                'sha256': _hash(raw), 'width': image.width, 'height': image.height}

    def _image(self, db, entry, snapshots=None):
        raw = (snapshots.get(entry['asset_id']) if snapshots is not None
               else self._read_bytes(db, entry['asset_id']))
        if raw is None or _hash(raw) != entry['sha256']:
            raise ValueError('Registered image is missing, replaced or corrupted')
        image = _decode(raw)
        if image.size != (entry['width'], entry['height']):
            raise ValueError('Registered image dimensions changed')
        return image

    def _baseline_requirements(self, record):
        definition = record['definition']
        if 'baseline_requirements' in definition:
            return _declarations(definition['baseline_requirements'], 'baseline_requirements')
        # Compatibility category callers cannot bypass declared requirements.
        return list(dict.fromkeys(requirement for attr in definition['attributes'].values()
                    for requirement in _declarations(attr.get('preview_contract', {}).get('baseline_requirements', []),
                                                      'baseline_requirements')))

    def _confirmations(self, record, confirmations):
        requirements = self._baseline_requirements(record)
        confirmations = [] if confirmations is None else _declarations(confirmations, 'baseline_confirmations')
        if set(confirmations) != set(requirements):
            raise ValueError('Exact operator baseline confirmations are required')
        return requirements

    def _baseline_attestation(self, record):
        baseline = record['baseline']
        self._confirmations(record, baseline.get('baseline_confirmations'))
        if self._baseline_requirements(record) and baseline.get('confirmation_basis') != 'operator_attestation_not_machine_proof':
            raise ValueError('Missing operator baseline attestation')

    def set_base(self, category_id, image_path, image_id, subject_id='woman-1', crop=None, attribute_id=None, group=None,
                 baseline_confirmations=None):
        _text(image_id, 'owned gallery image ID')
        _text(subject_id, 'declared adult woman subject ID')
        path = _safe_file(image_path, self.root)
        try:
            path.relative_to(self.output_dir)
        except ValueError:
            pass
        else:
            raise ValueError('Comparison masters/outputs cannot be chained into a new base')
        raw = _read_file(path)
        image = _decode(raw, normalize=True)
        original_pixel_sha256 = _hash(image.tobytes())
        normalized_crop = None
        if crop is not None:
            box, normalized_crop = _crop_box(crop, image.size)
            image = image.crop(box)
        with self._transaction() as db:
            key = self._target(db, category_id, attribute_id, group, force_group=True)
            record = self._get(db, key)
            confirmations = self._confirmations(record, baseline_confirmations)
            if record['state'] != 'draft':
                raise ValueError('Reopen this group/category before replacing its base')
            if key == category_id and record['baseline'] is None:
                for attr in record['definition']['attributes'].values():
                    declared = attr.get('comparison_group')
                    if declared and self._get(db, category_id + '::' + declared)['state'] != 'draft':
                        raise ValueError('Choose and reopen the explicit review group before replacing its base')
            # Detect copied prior masters as well as paths inside the comparison store.
            if db.execute("SELECT 1 FROM comparison_assets WHERE role='output' AND (sha256=? OR pixel_sha256=?)",
                          (_hash(raw), original_pixel_sha256)).fetchone():
                raise ValueError('An edited predecessor is not an original gallery reference')
            old = json.loads(_json(record))
            baseline = self._register(db, image, 'baseline')
            baseline.update(image_id=image_id, subject_id=subject_id,
                            baseline_confirmations=confirmations,
                            confirmation_basis='operator_attestation_not_machine_proof',
                            subject_metadata={'presentation': 'woman', 'age': 'adult',
                                              'basis': 'operator_declared_not_detected'},
                            source_sha256=_hash(raw), crop=normalized_crop,
                            normalization='EXIF orientation applied; ICC to sRGB if present; lossless RGBA PNG; metadata stripped')
            self._event(db, old, 'base_replaced_previous', old)
            record.update(baseline=baseline, masks={})
            if '::' in key:
                # Declare every global footprint before the first shared-scene
                # candidate. Later controls fork the identical reviewed contract.
                for aid, attr in record['definition']['attributes'].items():
                    if _scope(attr) and METHOD_ALIASES.get(attr.get('preview_method'), attr.get('preview_method')) in GLOBAL_METHODS | {'simulated_optics'}:
                        record['masks'][aid] = self._mask(db, record, aid,
                            [[0, 0], [1, 0], [1, 1], [0, 1]], global_effect=True)
            self._invalidate(db, record, 'base_changed')
            self._save(db, record)
        return self.review(category_id, attribute_id, group)

    def _mask(self, db, record, attribute_id, polygon, global_effect=False, swatch=False):
        attr = record['definition']['attributes'].get(attribute_id)
        if attr is None:
            raise ValueError('Unknown comparison attribute')
        if record['baseline'] is None:
            raise ValueError('Choose a baseline before drawing a mask')
        if not isinstance(polygon, (list, tuple)) or not 3 <= len(polygon) <= 256:
            raise ValueError('Mask needs 3–256 normalized polygon points')
        points = []
        for point in polygon:
            if not isinstance(point, (list, tuple)) or len(point) != 2:
                raise ValueError('Invalid normalized polygon point')
            points.append([_number(point[0], 'mask x', 0, 1), _number(point[1], 'mask y', 0, 1)])
        area = abs(sum(points[i][0] * points[(i + 1) % len(points)][1] -
                       points[(i + 1) % len(points)][0] * points[i][1] for i in range(len(points)))) / 2
        if area < .000001:
            raise ValueError('Mask polygon has zero area')
        base = self._image(db, record['baseline'])
        if global_effect or swatch:
            if swatch:
                if attr.get('preview_method') != 'fabric_swatch' or attr.get('preview_scope') != 'swatch':
                    raise ValueError('Whole swatch mask requires explicit illustrative fabric-swatch metadata')
            elif not _scope(attr) or METHOD_ALIASES.get(attr.get('preview_method'), attr.get('preview_method')) not in GLOBAL_METHODS | {'simulated_optics'}:
                raise ValueError('Wholeframe mask requires an explicitly global optical effect')
            mask = Image.new('L', base.size, 255)
        else:
            # 2x edge supersampling has bounded memory even for the largest accepted base.
            scale = 2
            mask = Image.new('L', (base.width * scale, base.height * scale), 0)
            ImageDraw.Draw(mask).polygon([(round(x * (mask.width - 1)), round(y * (mask.height - 1)))
                                         for x, y in points], fill=255)
            mask = mask.resize(base.size, Image.Resampling.LANCZOS)
        values = list(_pixels(mask))
        count = sum(p > 0 for p in values)
        coverage = count / (base.width * base.height)
        if count == 0:
            raise ValueError('Mask has no pixel footprint')
        if not _scope(attr) and not swatch and coverage >= .98:
            raise ValueError('Localized attributes cannot use a wholeframe mask')
        entry = self._register(db, mask, 'mask')
        tint = Image.new('RGBA', base.size, (255, 20, 100, 255))
        overlay = Image.composite(tint, base, mask.point(lambda x: round(x * .35)))
        # Polygon outlines make edges visible without claiming correctness or segmentation.
        ImageDraw.Draw(overlay).line([(round(x * (base.width - 1)), round(y * (base.height - 1)))
                                     for x, y in points + [points[0]]], fill=(255, 255, 0, 255), width=1)
        registered = self._register(db, overlay, 'overlay')
        entry.update(polygon=points, coverage=coverage, pixel_count=count,
                     alpha_area=sum(values) / (255 * base.width * base.height),
                     base_sha256=record['baseline']['sha256'], attribute_id=attribute_id,
                     scope='illustrative_swatch' if swatch else ('explicit_global_effect' if _scope(attr) else 'reviewed_localized_region'),
                     provenance='catalog_declared_swatch' if swatch else ('catalog_declared_global_effect' if global_effect else 'operator_drawn_normalized_polygon'),
                     overlay_asset_id=registered['asset_id'], overlay_url=registered['url'],
                     overlay_sha256=registered['sha256'], human_review_required=True,
                     correctness='Coverage and outside equality do not establish that the mask is semantically correct')
        return entry

    def set_mask(self, category_id, attribute_id, polygon, group=None):
        with self._transaction() as db:
            key = self._target(db, category_id, attribute_id, group)
            record = self._get(db, key)
            if record['state'] != 'draft':
                raise ValueError('Reopen this group/category before replacing its mask')
            old = json.loads(_json(record))
            if attribute_id not in record['definition']['attributes']:
                raise ValueError('Unknown comparison attribute')
            if isinstance(polygon, (list, tuple)) and not polygon:
                self._event(db, old, 'mask_removed_previous', old)
                record['masks'].pop(attribute_id, None)
            else:
                entry = self._mask(db, record, attribute_id, polygon)
                self._event(db, old, 'mask_replaced_previous', old)
                record['masks'][attribute_id] = entry
            self._invalidate(db, record, 'mask_changed')
            self._save(db, record)
        return self.review(category_id, attribute_id, group)

    def _integrity(self, db, record):
        if record['baseline'] is None:
            raise ValueError('A baseline is required')
        if self._contract(record) != record['contract_hash']:
            raise ValueError('Stored contract hash mismatch')
        self._baseline_attestation(record)
        snapshots = {}
        def snapshot(entry):
            raw = self._read_bytes(db, entry['asset_id'])
            if raw is None or _hash(raw) != entry['sha256']:
                raise ValueError('Registered image is missing, replaced or corrupted')
            snapshots[entry['asset_id']] = raw
            self._image(db, entry, snapshots)
        snapshot(record['baseline'])
        if not record['masks']:
            raise ValueError('Draw and visually review at least one target mask')
        for entry in record['masks'].values():
            snapshot(entry)
            raw = self._read_bytes(db, entry['overlay_asset_id'])
            if raw is None or _hash(raw) != entry['overlay_sha256']:
                raise ValueError('Mask review overlay is missing or corrupted')
            if _decode(raw).size != (entry['width'], entry['height']):
                raise ValueError('Mask review overlay dimensions changed')
            snapshots[entry['overlay_asset_id']] = raw
            if entry['base_sha256'] != record['baseline']['sha256']:
                raise ValueError('Mask belongs to a different original base')
        return snapshots

    def _approval_integrity(self, record, approval, cycle_id=None, artifact=None):
        try:
            if (not approval or approval['contract_hash'] != record['contract_hash'] or
                    approval['baseline_sha256'] != record['baseline']['sha256'] or
                    approval['mask_hashes'] != {k: v['sha256'] for k, v in record['masks'].items()} or
                    approval['overlay_hashes'] != {k: v['overlay_sha256'] for k, v in record['masks'].items()} or
                    (cycle_id is not None and approval['cycle_id'] != cycle_id) or
                    (artifact is not None and (artifact['id'] not in approval['artifact_ids'] or
                     approval['artifact_hashes'].get(artifact['id']) != artifact['receipt']['output_sha256']))):
                raise ValueError('Operator approval provenance mismatch')
        except (KeyError, TypeError, AttributeError):
            raise ValueError('Operator approval provenance mismatch') from None

    def _cycle_approval(self, record, cycle_id):
        # Validate the originating contract as well as the cycle that authorized
        # this candidate. A later approval cannot repair a corrupt earlier one.
        contract = next((a for a in record['approvals'] if a.get('stage') == 'contract'), None)
        first_cycle = record['budget'].get('cycle_id', 0) - sum(a.get('stage') == 'expansion' for a in record['approvals'])
        self._approval_integrity(record, contract, first_cycle)
        approval = next((a for a in reversed(record['approvals'])
                         if a.get('stage') in ('contract', 'expansion') and a.get('cycle_id') == cycle_id), None)
        self._approval_integrity(record, approval, cycle_id)
        if (approval['stage'] != ('contract' if cycle_id == first_cycle else 'expansion') or
                type(approval['provider_attempt_cap']) is not int or not 0 <= approval['provider_attempt_cap'] <= 3):
            raise ValueError('Operator cycle approval mismatch')
        return approval

    def approve(self, category_id, stage, expected_contract_hash, artifact_ids=None,
                provider_attempt_cap=0, approval_note='', attribute_id=None, group=None):
        if stage not in ('contract', 'pilot', 'publish', 'expansion'):
            raise ValueError('Approval stage must be contract, pilot, publish or expansion')
        if type(provider_attempt_cap) is not int or not 0 <= provider_attempt_cap <= 3:
            raise ValueError('Provider attempt cap must be an integer from 0 to 3')
        if not isinstance(approval_note, str) or len(approval_note) > 4000:
            raise ValueError('Invalid operator approval note')
        artifact_ids = [] if artifact_ids is None else artifact_ids
        if (not isinstance(artifact_ids, list) or len(artifact_ids) > 100 or
                any(not isinstance(x, str) for x in artifact_ids) or len(set(artifact_ids)) != len(artifact_ids)):
            raise ValueError('Invalid individual artifact IDs')
        with self._transaction() as db:
            key = self._target(db, category_id, attribute_id, group)
            record = self._get(db, key)
            if expected_contract_hash != record['contract_hash'] or self._contract(record) != record['contract_hash']:
                raise ValueError('Stale or incorrect expected contract hash')
            self._integrity(db, record)
            if stage == 'pilot' and record['state'] not in ('contract_approved', 'pilot_done', 'pilot_accepted'):
                raise ValueError('Reopen or approve a new cycle before accepting another pilot')
            if stage == 'publish' and record['state'] != 'pilot_accepted':
                raise ValueError('Publication requires accepted pilot state; Reopen published reviews to revise them')
            contract = any(a['stage'] == 'contract' and a['contract_hash'] == expected_contract_hash for a in record['approvals'])
            if stage != 'contract':
                self._cycle_approval(record, record['budget'].get('cycle_id', 0))
            selected = [a for a in record['artifacts'] if a['id'] in artifact_ids]
            if len(selected) != len(artifact_ids):
                raise ValueError('Artifact does not belong to the current original-base contract')
            if stage in ('contract', 'expansion'):
                if artifact_ids:
                    raise ValueError('Cycle approval cannot accept or publish artifacts')
                if stage == 'contract' and record['state'] != 'draft':
                    raise ValueError('Contract already approved; accept pilot and explicitly approve an expansion cycle')
                if stage == 'expansion':
                    _text(approval_note, 'expansion approval note', 4000)
                    if not contract or record['state'] not in ('pilot_accepted', 'published'):
                        raise ValueError('Accept the previous pilot before approving an expansion cycle')
                    if any(row['status'] == 'reserved' for row in db.execute(
                            'SELECT status FROM comparison_requests WHERE category_id=? AND contract_hash=?', (category_id, record['contract_hash']))):
                        raise ValueError('An ambiguous/in-flight reservation must remain consumed; cycle cannot expand')
                budget = record['budget']
                # Total used never decreases, including failed/ambiguous attempts.
                budget.update(cap=provider_attempt_cap, cycle_used=0, cycle_id=budget.get('cycle_id', 0) + 1)
                record['state'] = 'contract_approved'
            else:
                if not contract:
                    raise ValueError('Operator contract and mask approval is required first')
                if not selected:
                    raise ValueError('Select individual reviewed artifacts')
                for artifact in selected:
                    self._artifact_integrity(db, record, artifact, publishing=stage == 'publish')
                    receipt = artifact['receipt']
                    if (receipt['contract_hash'] != expected_contract_hash or
                            receipt['base_sha256'] != record['baseline']['sha256'] or
                            receipt['mask_sha256'] != record['masks'][artifact['attribute_id']]['sha256'] or
                            receipt['outside_delta'] != 0 or receipt['inside_change']['changed_pixels'] == 0):
                        raise ValueError('Artifact provenance or target-effect mismatch')
                    self._image(db, {'asset_id': artifact['id'], 'sha256': receipt['output_sha256'],
                                     'width': receipt['dimensions'][0], 'height': receipt['dimensions'][1]})
                    if stage == 'publish' and not artifact['accepted']:
                        raise ValueError('Publication requires individual human pilot acceptance')
                if stage == 'pilot':
                    for artifact in selected:
                        artifact['accepted'] = True
                        artifact['human_review'] = {'note': approval_note, 'reviewed_at': time.time(),
                                                    'contract_hash': expected_contract_hash,
                                                    'output_sha256': artifact['receipt']['output_sha256']}
                    record['state'] = 'pilot_accepted'
                else:
                    record['state'] = 'published'
                    record['published_artifact_ids'] = list(artifact_ids)
            approval = {'stage': stage, 'contract_hash': expected_contract_hash, 'artifact_ids': artifact_ids,
                        'cycle_id': record['budget'].get('cycle_id', 0), 'total_used': record['budget']['used'],
                        'provider_attempt_cap': record['budget']['cap'], 'approval_note': approval_note,
                        'actor': 'operator', 'created_at': time.time(),
                        'baseline_sha256': record['baseline']['sha256'],
                        'mask_hashes': {k: v['sha256'] for k, v in record['masks'].items()},
                        'overlay_hashes': {k: v['overlay_sha256'] for k, v in record['masks'].items()},
                        'artifact_hashes': {a['id']: a['receipt']['output_sha256'] for a in selected},
                        'visual_review': 'operator affirms baseline, footprint overlay and selected outputs including identity/anatomy/target effect'}
            record['approvals'].append(approval)
            self._event(db, record, 'operator_approval', approval)
            self._save(db, record)
        return self.review(category_id, attribute_id, group)

    def _catalog_params(self, attribute, value, method):
        try:
            return self._params(attribute, value, method, {})
        except ValueError:
            # Older single-category libraries may declare a method without its
            # required target settings. Such custom drafts remain inspectable,
            # but cannot become canonical thumbnails.
            return None

    def _params(self, attribute, value, method, supplied):
        if not isinstance(supplied, dict) or len(_json(supplied)) > 16000:
            raise ValueError('Invalid bounded method parameters')
        # The server supplies a library, never a client-selected source or mask.
        forbidden = {'image_path', 'image_bytes', 'image_id', 'base_url', 'source', 'mask', 'polygon',
                     'base_asset_id', 'mask_asset_id', 'output_size', 'resize', 'prompt'}
        if forbidden.intersection(supplied):
            raise ValueError('Source/mask/dimensions/prompt are contract-locked')
        params = {}
        for source in (attribute.get('preview_params', {}), value.get('preview_params', {}), value.get('params', {}), supplied):
            if not isinstance(source, dict):
                raise ValueError('Invalid catalog method parameters')
            source = dict(source)
            if method in ('masked_recolor', 'fabric_swatch'):
                if isinstance(source.get('colour'), dict) and set(source['colour']) != {'hex'}:
                    raise ValueError('RGB colour must contain only hex')
                colours = [source[k].get('hex') if isinstance(source[k], dict) else source[k]
                           for k in ('colour', 'color', 'hex') if k in source]
                if colours:
                    if any(not isinstance(c, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', c) for c in colours) or len({c.lower() for c in colours}) != 1:
                        raise ValueError('Conflicting or invalid explicit RGB aliases')
                    for alias in ('colour', 'color', 'hex'):
                        source.pop(alias, None)
                    source['colour'] = {'hex': colours[0].lower()}
            for key, val in source.items():
                if (METHOD_ALIASES.get(method, method) == 'editorial_grade' and key in ('grade', 'contrast')
                        and isinstance(params.get(key), dict) and isinstance(val, dict)):
                    params[key] = {**params[key], **val}
                else:
                    params[key] = val
        effective_method = (params.get('effect', attribute.get('effect', attribute['id'])) if method == 'simulated_optics'
                            else METHOD_ALIASES.get(method, method))
        if effective_method not in PARAM_KEYS:
            raise ValueError('Unsupported specifically labeled comparison effect')
        allowed = PARAM_KEYS[effective_method] | {'base_sha256', 'mask_sha256'}
        if method == 'simulated_optics':
            allowed.add('effect')
            params['effect'] = effective_method
        unknown = set(params) - allowed
        if unknown:
            raise ValueError('Unsupported method parameters: ' + ', '.join(sorted(unknown)))
        params = {**PARAM_DEFAULTS[effective_method], **params}
        for key, val in params.items():
            if key in PARAM_RANGES:
                _number(val, key, *PARAM_RANGES[key])
                if key == 'seed' and type(val) is not int:
                    raise ValueError('Grain seed must be a bounded integer')
        for key in ('shadow_tint', 'highlight_tint'):
            if key in params:
                vector = params[key]
                if not isinstance(vector, list) or len(vector) != 3:
                    raise ValueError('Tint must have three RGB offsets')
                for offset in vector:
                    _number(offset, key, -64, 64)
        for key in ('depth_assumption', 'moving_region'):
            if key in PARAM_KEYS[effective_method]:
                _text(params.get(key), 'explicit ' + key, 1000)
        if effective_method == 'palette':
            anchors = params.get('anchors')
            if (not isinstance(anchors, list) or not 1 <= len(anchors) <= 8 or
                    any(not isinstance(c, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', c) for c in anchors)):
                raise ValueError('Palette needs 1–8 illustrative RGB anchors')
        if effective_method == 'editorial_grade':
            for key, component in (('grade', 'color_grade'), ('contrast', 'contrast')):
                nested = params.get(key)
                if not isinstance(nested, dict) or set(nested) - PARAM_KEYS[component]:
                    raise ValueError('Invalid editorial ' + key + ' component parameters')
                params[key] = self._params({'id': component}, {}, component, nested)
        if method in ('masked_recolor', 'fabric_swatch'):
            colour = params.get('colour', value.get('colour', attribute.get('colour')))
            color = params.get('color', params.get('hex'))
            if isinstance(colour, dict):
                color = colour.get('hex', color)
            elif isinstance(colour, str):
                color = colour
            if color is None:
                color = value.get('hex', value.get('color'))
            if not isinstance(color, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', color):
                raise ValueError('Recolor/swatch needs a selected RGB colour.hex target')
            params['colour'] = {'hex': color.lower()}
            params.pop('color', None)
            params.pop('hex', None)
        return json.loads(_json(params))

    def _neutral(self, method, params):
        """Only a catalog-declared baseline with actually neutral settings is a no-op."""
        if method == 'grain':
            return params['amount'] == 0
        if method == 'white_balance':
            return params['temperature'] == params['tint'] == 0
        if method == 'gentlehighlight_rolloff':
            return params['strength'] == 0
        if method == 'focal_fov':
            return params['factor'] == 1
        if method in ('focus_depth_blur', 'aperture_blur'):
            return params['radius'] == 0
        if method == 'motion_blur':
            return params['distance'] == 0
        if method in ('color_grade', 'contrast'):
            return all(params[key] == val for key, val in PARAM_DEFAULTS[method].items())
        if method == 'editorial_grade':
            return params['mix'] == 0 or (self._neutral('color_grade', params['grade']) and
                                          self._neutral('contrast', params['contrast']))
        return False

    def _local(self, base, method, params):
        """Always start with the immutable original pixels, never another artifact."""
        pixels = list(_pixels(base))
        if self._neutral(method, params):
            return base.copy()
        if method == 'masked_recolor':
            hex_color = params['colour']['hex']
            rgb = tuple(int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
            target_luma = .2126 * rgb[0] + .7152 * rgb[1] + .0722 * rgb[2]
            lumas = sorted(.2126 * r + .7152 * g + .0722 * b for r, g, b, a in pixels)
            pivot = max(1, lumas[len(lumas) // 2])
            data = []
            for r, g, b, alpha in pixels:
                luma = .2126 * r + .7152 * g + .0722 * b
                # Preserve relative luminance/texture, permitting a lighter selected pigment.
                desired_luma = max(0, min(255, target_luma + (luma - pivot) * .85))
                data.append(tuple(round(max(0, min(255, c + desired_luma - target_luma))) for c in rgb) + (alpha,))
            result = Image.new('RGBA', base.size)
            result.putdata(data)
            return result
        if method == 'fabric_swatch':
            hex_color = params['colour']['hex']
            rgb = tuple(int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
            scale = int(_number(params.get('weave_scale', 4), 'weave_scale', 2, 32))
            source = None
            if 'source_crop' in params:
                box, _ = _crop_box(params['source_crop'], base.size)
                source = base.crop(box).resize(base.size, Image.Resampling.BICUBIC)
            data = []
            for index, (_, _, _, alpha) in enumerate(pixels):
                x, y = index % base.width, index // base.width
                weave = (9 if (x // scale + y // scale) % 2 else -9) + (4 if x % scale == 0 else 0) - (4 if y % scale == 0 else 0)
                if source:
                    r, g, b, _ = source.getpixel((x, y))
                    weave += ((r + g + b) / 3 - 128) * .25
                data.append(tuple(round(max(0, min(255, c + weave))) for c in rgb) + (alpha,))
            result = Image.new('RGBA', base.size)
            result.putdata(data)
            return result
        if method == 'grain':
            amount = _number(params.get('amount', 10), 'grain amount', 0, 64)
            seed = params.get('seed', 0)
            if type(seed) is not int or not 0 <= seed <= 2**32 - 1:
                raise ValueError('Grain seed must be a bounded integer')
            rng = random.Random(seed)
            soften = params['soften']
            shadow_bias = params['shadow_bias']
            noise_field = None
            if soften:
                noise_field = Image.new('L', base.size)
                noise_field.putdata([round(max(0, min(255, 128 + rng.gauss(0, amount)))) for _ in pixels])
                noise_field = list(_pixels(noise_field.filter(ImageFilter.GaussianBlur(soften))))
            data = []
            for index, (r, g, b, a) in enumerate(pixels):
                noise = noise_field[index] - 128 if noise_field is not None else rng.gauss(0, amount)
                luma = (.2126 * r + .7152 * g + .0722 * b) / 255
                noise *= 1 - shadow_bias * luma
                data.append(tuple(round(max(0, min(255, c + noise))) for c in (r, g, b)) + (a,))
            result = Image.new('RGBA', base.size)
            result.putdata(data)
            return result
        if method == 'white_balance':
            temperature = _number(params.get('temperature', .2), 'temperature', -1, 1)
            tint = _number(params.get('tint', 0), 'tint', -1, 1)
            gains = (1 + .25 * temperature + .1 * tint, 1 - .15 * tint, 1 - .25 * temperature + .1 * tint)
            result = Image.new('RGBA', base.size)
            result.putdata([tuple(round(max(0, min(255, c * gain))) for c, gain in zip((r, g, b), gains)) + (a,)
                            for r, g, b, a in pixels])
            return result
        if method == 'gentlehighlight_rolloff':
            strength = _number(params.get('strength', .5), 'rolloff strength', 0, 1)
            threshold = _number(params.get('threshold', .7), 'rolloff threshold', 0, .99) * 255
            def compress(c):
                if c <= threshold:
                    return c
                distance = (c - threshold) / (255 - threshold)
                return round(c - strength * distance * distance * (255 - threshold) * .5)
            result = Image.new('RGBA', base.size)
            result.putdata([(compress(r), compress(g), compress(b), a) for r, g, b, a in pixels])
            return result
        if method == 'focal_fov':
            factor = _number(params.get('factor', 1.5), 'focal crop factor', 1, 6)
            width, height = max(2, round(base.width / factor)), max(2, round(base.height / factor))
            left, top = (base.width - width) // 2, (base.height - height) // 2
            result = base.crop((left, top, left + width, top + height)).resize(base.size, Image.Resampling.LANCZOS)
            result.putalpha(base.getchannel('A'))
            return result
        if method in ('focus_depth_blur', 'aperture_blur'):
            _text(params.get('depth_assumption'), 'explicit depth assumption', 1000)
            radius = _number(params.get('radius', 2), 'blur radius', 0, 32)
            result = base.convert('RGB').filter(ImageFilter.GaussianBlur(radius)).convert('RGBA')
            result.putalpha(base.getchannel('A'))
            return result
        if method == 'motion_blur':
            _text(params.get('moving_region'), 'moving region and swept footprint', 1000)
            distance = _number(params.get('distance', 5), 'motion distance', 0, 64)
            angle = math.radians(_number(params.get('direction', 0), 'motion direction degrees', -360, 360))
            steps = min(65, max(1, math.ceil(distance) + 1))
            offsets = [(round(math.cos(angle) * distance * (i / max(1, steps - 1) - .5)),
                        round(math.sin(angle) * distance * (i / max(1, steps - 1) - .5))) for i in range(steps)]
            data = []
            for index, (_, _, _, alpha) in enumerate(pixels):
                x, y = index % base.width, index // base.width
                samples = [pixels[min(base.height - 1, max(0, y + dy)) * base.width + min(base.width - 1, max(0, x + dx))]
                           for dx, dy in offsets]
                data.append(tuple(round(sum(p[c] for p in samples) / steps) for c in range(3)) + (alpha,))
            result = Image.new('RGBA', base.size)
            result.putdata(data)
            return result
        if method == 'color_grade':
            gains = (1 + .25 * params['temperature'] + .1 * params['tint'],
                     1 - .15 * params['tint'], 1 - .25 * params['temperature'] + .1 * params['tint'])
            data = []
            for r, g, b, a in pixels:
                luma = .2126 * r + .7152 * g + .0722 * b
                shadow, highlight = (1 - luma / 255) ** 2, (luma / 255) ** 2
                data.append(tuple(round(max(0, min(255,
                    (luma + (c - luma) * params['saturation']) * gain + params['lift'] +
                    params['shadow_tint'][i] * shadow + params['highlight_tint'][i] * highlight)))
                    for i, (c, gain) in enumerate(zip((r, g, b), gains))) + (a,))
            result = Image.new('RGBA', base.size)
            result.putdata(data)
            return result
        if method == 'contrast':
            def curve(c):
                x = c / 255
                return round(max(0, min(255, 127.5 + (c - 127.5) * params['slope'] +
                    params['midtones'] * (x - .5) * x * (1 - x) * 255 +
                    params['shadows'] * (1 - x) ** 2 + params['highlights'] * x ** 2)))
            result = Image.new('RGBA', base.size)
            result.putdata([(curve(r), curve(g), curve(b), a) for r, g, b, a in pixels])
            return result
        if method == 'palette':
            hues = [colorsys.rgb_to_hsv(*(int(c[i:i + 2], 16) / 255 for i in (1, 3, 5)))[0]
                    for c in params['anchors']]
            data = []
            for r, g, b, a in pixels:
                hue, saturation, brightness = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
                delta = min(((target - hue + .5) % 1 - .5 for target in hues), key=abs)
                rgb = colorsys.hsv_to_rgb((hue + delta * params['strength']) % 1,
                                         min(1, saturation * params['saturation']), brightness)
                data.append(tuple(round(c * 255) for c in rgb) + (a,))
            result = Image.new('RGBA', base.size)
            result.putdata(data)
            return result
        if method == 'editorial_grade':
            # The two disclosed recipe operations compose in memory, starting from
            # this same original. No artifact/reference chaining is involved.
            graded = self._local(base, 'color_grade', params['grade'])
            toned = self._local(graded, 'contrast', params['contrast'])
            return Image.blend(base, toned, params['mix'])
        raise ValueError('Unsupported local comparison method')

    def render(self, category_id, attribute_id, value_id, method, params, request_key, library, provider=None, group=None):
        _text(request_key, 'request key', 200)
        _text(attribute_id, 'attribute ID')
        _text(value_id, 'value ID')
        declared_method = method
        if method not in LOCAL_METHODS and method not in METHOD_ALIASES and method not in ('reference_edit', 'simulated_optics'):
            raise ValueError('Unsupported comparison method; no text-generation fallback')
        categories = _category_map(library)
        cat = categories.get(category_id)
        attribute = cat['attributes'].get(attribute_id) if cat else None
        if attribute is None or attribute.get('preview_method') != method:
            raise ValueError('Method must match the catalog-declared target attribute')
        if attribute.get('preview_method') == 'control_only' or attribute.get('preview_scope') == 'control_only':
            raise ValueError('Control-only attributes have no image comparison')
        value = next((v for v in attribute.get('values', []) if v['id'] == value_id), None)
        if value is None:
            raise ValueError('Unknown catalog target value')
        catalog_params = self._catalog_params(attribute, value, method)
        effective = self._params(attribute, value, method, params)
        custom = {k: v for k, v in effective.items() if k not in ('base_sha256', 'mask_sha256')} != catalog_params
        method = METHOD_ALIASES.get(method, method)
        if method == 'simulated_optics':
            method = effective.get('effect', attribute.get('effect', attribute_id))
            if method not in GLOBAL_METHODS | {'focus_depth_blur', 'aperture_blur', 'motion_blur'}:
                raise ValueError('Choose a supported, specifically labeled optical simulation')
        global_effect = _scope(attribute)
        intentional_baseline = value.get('preview_baseline') is True and self._neutral(method, effective)
        if global_effect and method not in GLOBAL_METHODS:
            raise ValueError('This method requires a localized drawn region')
        request_digest = _digest({'category': category_id, 'attribute': attribute_id, 'value': value_id,
                                  'method': declared_method, 'params': effective, 'definition': cat})
        with self._transaction() as db:
            record_key = self._target(db, category_id, attribute_id, group)
            record = self._get(db, record_key)
            if '::' in record_key:
                cat = _group_definition(cat, record_key.split('::', 1)[1])
            if record['definition'] != cat:
                raise ValueError('Catalog changed: refresh category contracts before rendering')
            # Every key remains a tombstone even after a contract changes.
            prior = db.execute('SELECT * FROM comparison_requests WHERE category_id=? AND request_key=?', (category_id, request_key)).fetchone()
            if prior:
                if prior['digest'] != request_digest or prior['contract_hash'] != record['contract_hash']:
                    raise ValueError('Request key already belongs to different parameters or contract')
                if prior['status'] == 'done':
                    result = json.loads(prior['result'])
                    if self._asset(db, result['id']) is None:
                        raise ValueError('Idempotent artifact was corrupted or removed; no automatic retry')
                    return result
                if prior['status'] == 'failed' and prior['result']:
                    return json.loads(prior['result'])
                raise ValueError(prior['error'] or 'Attempt is reserved/in flight; no automatic retry')
            if record['state'] == 'published':
                raise ValueError('Reopen the published group/category before rendering new candidates')
            swatch = method == 'fabric_swatch' and attribute.get('preview_scope') == 'swatch'
            if record['baseline'] is None and swatch:
                reference = self._register(db, Image.new('RGBA', (256, 256), (128, 128, 128, 255)), 'baseline')
                reference.update(image_id=None, subject_id='fabric-swatch',
                                 subject_metadata={'basis': 'synthetic_neutral_texture_reference', 'presentation': 'no_person'},
                                 source_sha256=reference['sha256'], crop=None,
                                 normalization='Synthetic neutral lossless RGBA PNG for illustrative texture swatches')
                record['baseline'] = reference
                self._invalidate(db, record, 'illustrative_swatch_reference_added')
            if record['baseline'] is None:
                raise ValueError('Choose an original baseline before rendering')
            for key, expected in (('base_sha256', record['baseline']['sha256']),):
                if key in effective and effective[key] != expected:
                    raise ValueError('Wrong original base hash')
            if attribute_id not in record['masks']:
                if record['state'] != 'draft':
                    raise ValueError('Reopen before adding a target mask to an approved contract')
                if not global_effect and not swatch:
                    raise ValueError('Localized target has no independently drawn mask')
                record['masks'][attribute_id] = self._mask(db, record, attribute_id,
                        [[0, 0], [1, 0], [1, 1], [0, 1]], global_effect=global_effect, swatch=swatch)
                self._invalidate(db, record, 'explicit_global_mask_added')
            mask_entry = record['masks'][attribute_id]
            if 'mask_sha256' in effective and effective['mask_sha256'] != mask_entry['sha256']:
                raise ValueError('Wrong mask hash')
            if mask_entry['base_sha256'] != record['baseline']['sha256']:
                raise ValueError('Mask belongs to a different original base')
            snapshots = self._integrity(db, record)
            base = self._image(db, record['baseline'], snapshots)
            mask = self._image(db, mask_entry, snapshots).convert('L')
            contract_approval = next((a for a in reversed(record['approvals']) if a['stage'] in ('contract', 'expansion')
                                      and a['contract_hash'] == record['contract_hash']), None)
            if record['state'] != 'draft':
                contract_approval = self._cycle_approval(record, record['budget'].get('cycle_id', 0))
            if method == 'reference_edit':
                metadata = record['baseline'].get('subject_metadata', {})
                if metadata.get('presentation') != 'woman' or metadata.get('age') != 'adult' or metadata.get('basis') == 'synthetic_neutral_texture_reference':
                    raise ValueError('Reference edit requires an operator-reviewed adult woman reference; no-person baselines are forbidden')
                if not callable(provider):
                    raise ValueError('Reference editing adapter unavailable; no fallback')
                if contract_approval is None:
                    raise ValueError('Operator contract, baseline and mask approval required before provider call')
                contract_approval = self._cycle_approval(record, record['budget'].get('cycle_id', 0))
                if contract_approval['provider_attempt_cap'] != record['budget']['cap']:
                    raise ValueError('Provider cycle budget approval mismatch')
                if (contract_approval['baseline_sha256'] != record['baseline']['sha256'] or
                        contract_approval['mask_hashes'].get(attribute_id) != mask_entry['sha256']):
                    raise ValueError('Provider mask/base approval mismatch')
                if not 0 < record['budget']['cap'] <= 3 or record['budget'].get('cycle_used', record['budget']['used']) >= record['budget']['cap']:
                    raise ValueError('Approved provider attempt budget exhausted or absent')
                record['budget']['cycle_used'] = record['budget'].get('cycle_used', record['budget']['used']) + 1
                record['budget']['used'] += 1
            baseline = record['baseline']
            contract_hash = record['contract_hash']
            original_bytes = snapshots[baseline['asset_id']]
            locked = {'base_asset_id': baseline['asset_id'], 'base_sha256': baseline['sha256'],
                      'mask_asset_id': mask_entry['asset_id'], 'mask_sha256': mask_entry['sha256'],
                      'dimensions': list(base.size), 'crop': baseline['crop'], 'subject_id': baseline['subject_id']}
            receipt = {'method': declared_method, 'effective_method': method, 'method_version': METHOD_VERSION, 'params': effective,
                       'catalog_params': catalog_params, 'supplied_overrides': json.loads(_json(params)),
                       'effective_params': effective, 'custom_override': custom,
                       'group': record_key.split('::', 1)[1] if '::' in record_key else None,
                       'cycle_id': record['budget'].get('cycle_id', 0), 'total_used': record['budget']['used'],
                       'locked_params': locked, 'target': {'category_id': category_id, 'attribute_id': attribute_id,
                                                         'value_id': value_id, 'steers': value.get('steers', '')},
                       'base_sha256': baseline['sha256'], 'mask_sha256': mask_entry['sha256'],
                       'contract_hash': contract_hash, 'dimensions': list(base.size), 'request_key': request_key,
                       'mask_scope': mask_entry['scope'], 'mask_overlay_sha256': mask_entry['overlay_sha256'],
                       'approval': contract_approval, 'human_review_required': True,
                       'target_contract': attribute.get('preview_contract', {}),
                       'locked_fields': record['locked_fields'], 'allowed_changes': record['allowed_changes'],
                       'baseline_confirmations': baseline.get('baseline_confirmations', []),
                       'provider_attempt_reserved': method == 'reference_edit', 'no_automatic_retry': True,
                       'created_at': time.time()}
            if 'recipe' in value:
                receipt['recipe_components'] = value['recipe']['selections']
            if method == 'reference_edit':
                receipt.update(method_label='Reference-conditioned geometry edit, composited to approved footprint',
                               allowed_effects=attribute.get('preview_contract', {}).get('allowed_changes', record['allowed_changes']),
                               simulated=False,
                               limitations=['Outside compositing equality does not prove correct geometry or identity inside the mask.',
                                            'Operator must review silhouette, occlusion/reveal, anatomy, facial landmarks and target effect at 1x/2x.',
                                            'Provider pixels outside the approved footprint are discarded; no unapproved expansion.'])
            else:
                label, simulated, limitation = LOCAL_METHODS[method]
                receipt.update(method_label=label, simulated=simulated,
                               limitations=[limitation, 'Mask coverage and zero outside delta require independent human visual review.'])
                receipt['allowed_effects'] = (['global colour and tone'] if global_effect and method in
                    {'white_balance', 'gentlehighlight_rolloff', 'color_grade', 'contrast', 'palette', 'editorial_grade'}
                    else attribute.get('preview_contract', {}).get('allowed_changes', [attribute_id]))
                receipt['effect_role'] = 'baseline' if intentional_baseline else 'target_effect'
                if intentional_baseline:
                    receipt['method_label'] += ' — baseline: original unchanged'
            receipt.update(status='reserved', output_sha256=None, outside_delta=None, inside_change=None)
            db.execute('INSERT INTO comparison_requests VALUES(?,?,?,?,?,?,?,?,?)',
                       (category_id, request_key, request_digest, contract_hash, 'reserved', None, None, _json(receipt), time.time()))
            self._save(db, record)
        # Paid work is outside the DB lock; reservation was committed before invocation.
        try:
            provider_delta = 0
            if method == 'reference_edit':
                prompt = ('Edit this ORIGINAL approved reference only. Target: ' + value.get('steers', value.get('name', value_id)) +
                          '. Preserve these approved record locks: ' + _json(record['locked_fields']) +
                          '. Shared record allowances, restricted to each declared target: ' + _json(record['allowed_changes']) +
                          '. This edit may only apply these selected target consequences: ' + _json(receipt['allowed_effects']) +
                          '. Target contract: ' + _json(receipt['target_contract']) +
                          '. Recipe consequences: ' + _json(value.get('recipe', {})) +
                          '. Keep original dimensions and alpha; modify only approved target footprint. ' +
                          'Footprint normalized polygon: ' + _json(mask_entry['polygon']) +
                          '. Reference SHA256: ' + baseline['sha256'] + '; mask SHA256: ' + mask_entry['sha256'])
                prompt += '. ' + REFERENCE_AESTHETIC_LOCK
                receipt['provider_prompt_sha256'] = _hash(prompt.encode())
                divisor = math.gcd(base.width, base.height)
                try:
                    encoded_image, mime = provider(prompt, original_bytes, 'image/png',
                                                   f'{base.width // divisor}:{base.height // divisor}')
                except Exception:
                    raise RuntimeError('Provider failure; original exception withheld to preserve credentials') from None
                if mime not in ('image/png', 'image/jpeg', 'image/webp'):
                    raise ValueError('Provider returned unsupported image MIME')
                if not isinstance(encoded_image, str) or len(encoded_image) > (MAX_BYTES * 4 // 3 + 8):
                    raise ValueError('Provider image exceeds bounded decode limit')
                try:
                    output_raw = base64.b64decode(encoded_image, validate=True)
                except (ValueError, UnicodeError) as exc:
                    raise ValueError('Invalid provider base64 image') from exc
                candidate = _decode(output_raw)
                if candidate.size != base.size:
                    raise ValueError('Provider changed reference dimensions; resize is forbidden')
                if candidate.getchannel('A').tobytes() != base.getchannel('A').tobytes():
                    raise ValueError('Provider changed locked alpha coverage')
                receipt['provider_raw_sha256'] = _hash(output_raw)
                provider_delta = sum(p != q for p, q, m in zip(_pixels(base), _pixels(candidate), _pixels(mask)) if m == 0)
            else:
                candidate = self._local(base, method, effective)
            if candidate.size != base.size:
                raise ValueError('Comparison changed locked dimensions')
            output = Image.composite(candidate, base, mask)
            output.putalpha(base.getchannel('A'))
            outside = inside = total_delta = maximum_delta = 0
            footprint = 0
            for before, after, m in zip(_pixels(base), _pixels(output), _pixels(mask)):
                if m == 0:
                    outside += before != after
                else:
                    footprint += 1
                    inside += before != after
                    delta = sum(abs(before[c] - after[c]) for c in range(3))
                    total_delta += delta
                    maximum_delta = max(maximum_delta, max(abs(before[c] - after[c]) for c in range(3)))
            if outside != 0:
                raise ValueError('Nonzero outside-mask pixel delta')
            if inside == 0 and not intentional_baseline:
                raise ValueError('Target effect is empty: unchanged masked pixels')
            receipt.update(outside_delta=outside, provider_outside_changed_pixels=provider_delta,
                           outside_mask_changed_pixels=outside, target_changed_pixels=inside,
                           provider_outside_mask_changed_pixels=provider_delta, status='baseline' if intentional_baseline else 'staged',
                           inside_change={'changed_pixels': inside, 'footprint_pixels': footprint,
                                          'fraction': inside / footprint, 'mean_absolute_rgb_delta': total_delta / (3 * footprint),
                                          'max_channel_delta': maximum_delta},
                           outside_check='Exact decoded RGBA pixel equality on lossless PNG; not semantic mask validation',
                           completed_at=time.time())
            with self._transaction() as db:
                current = self._get(db, record_key)
                if current['contract_hash'] != contract_hash:
                    raise ValueError('Base/mask/contract changed during render; output withheld, attempt remains consumed')
                self._image(db, baseline, snapshots)
                self._image(db, mask_entry, snapshots)
                asset = self._register(db, output, 'baseline_comparison' if intentional_baseline else 'output')
                receipt['output_sha256'] = asset['sha256']
                artifact = {'id': asset['asset_id'], 'url': asset['url'], 'base_url': baseline['url'],
                            'attribute_id': attribute_id, 'value_id': value_id, 'method': declared_method,
                            'receipt': receipt, 'receipt_sha256': _digest(receipt), 'custom': custom, 'accepted': False}
                current['artifacts'].append(artifact)
                if current['state'] == 'contract_approved':
                    current['state'] = 'pilot_done'
                self._save(db, current)
                db.execute("UPDATE comparison_requests SET status='done', result=?, receipt=? WHERE category_id=? AND request_key=?",
                           (_json(artifact), _json(receipt), category_id, request_key))
                self._event(db, current, 'render_completed', artifact)
            return artifact
        except Exception as exc:
            # Do not persist provider exception strings: they can include URLs/credentials.
            message = str(exc) if isinstance(exc, ValueError) else 'Provider/render failure or ambiguous billed response; no automatic retry'
            receipt.update(failed_at=time.time(), failure=message, no_automatic_retry=True, status='failed')
            failure = {'id': None, 'url': None, 'base_url': baseline['url'], 'attribute_id': attribute_id,
                       'value_id': value_id, 'method': declared_method, 'receipt': receipt, 'receipt_sha256': _digest(receipt), 'custom': custom, 'accepted': False}
            with self._transaction() as db:
                db.execute("UPDATE comparison_requests SET status='failed', error=?, receipt=?, result=? WHERE category_id=? AND request_key=?",
                           (message, _json(receipt), _json(failure) if method == 'reference_edit' else None, category_id, request_key))
            if method == 'reference_edit':
                return failure
            raise ValueError(message) from None
