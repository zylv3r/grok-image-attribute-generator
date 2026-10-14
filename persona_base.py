"""Persona reference packs. latest is the served working set; a numbered pack stays hash-pinned."""
import hashlib, io, json, pathlib, re, stat, warnings
from PIL import Image
import latest_sheet
MAX_BYTES = 32 * 1024 * 1024

def _read(root, relative, limit=MAX_BYTES):
    parts = relative.split('/')
    if not relative or any(not part or part.startswith('.') or part in ('.', '..') for part in parts):
        raise ValueError('invalid persona path')
    target = pathlib.Path(root)
    for part in parts:
        target = target / part
        if target.is_symlink():
            raise ValueError('symlink persona asset forbidden')
    if not target.is_file() or not stat.S_ISREG(target.stat().st_mode) or not 0 < target.stat().st_size <= limit:
        raise ValueError('persona asset unavailable')
    raw = target.read_bytes()
    if len(raw) > limit:
        raise ValueError('persona asset too large')
    return raw

def _decode_image(raw):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as image:
                image.load()
                if image.width * image.height > 25_000_000 or image.format not in ('JPEG', 'PNG'):
                    raise ValueError('invalid persona image')
    except (OSError, Image.DecompressionBombError):
        raise ValueError('invalid persona image')

def _pack(root):
    base = pathlib.Path(root) / 'base-personas'
    pointer = base / 'current.json'
    if not pointer.exists():
        return None
    selected = json.loads(_read(base, 'current.json', 65536))
    pid = selected.get('id')
    if not isinstance(pid, str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]*', pid):
        raise ValueError('invalid persona identity')
    if selected.get('slot') == 'latest':
        expected = pid + '/latest/persona.json'
        if selected.get('manifest') != expected:
            raise ValueError('invalid persona manifest pointer')
        pack = json.loads(_read(base, expected, 2 * 1024 * 1024))
        if pack.get('id') != pid or pack.get('slot') != 'latest' or not isinstance(pack.get('assets'), dict):
            raise ValueError('invalid persona pack')
        for key in ('title', 'status', 'future_image_model', 'keywords', 'canonical_face', 'canonical_body', 'overview', 'caveats', 'iteration_rule', 'selected_views'):
            if key not in pack:
                raise ValueError('invalid persona pack')
        if not isinstance(pack['keywords'], list) or not isinstance(pack['caveats'], list) or not isinstance(pack['selected_views'], dict):
            raise ValueError('invalid persona pack')
        return base, pid + '/latest/', pack, False
    revision = selected.get('revision')
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise ValueError('invalid persona identity')
    expected = pid + '/v' + str(revision) + '/persona.json'
    if selected.get('manifest') != expected:
        raise ValueError('invalid persona manifest pointer')
    sha = selected.get('manifest_sha256')
    if not isinstance(sha, str) or not re.fullmatch(r'[a-f0-9]{64}', sha):
        raise ValueError('invalid persona manifest hash')
    raw = _read(base, expected, 2 * 1024 * 1024)
    if hashlib.sha256(raw).hexdigest() != sha:
        raise ValueError('persona manifest integrity failed')
    pack = json.loads(raw)
    if pack.get('id') != pid or pack.get('revision') != revision or not isinstance(pack.get('assets'), dict):
        raise ValueError('invalid persona pack')
    return base, pid + '/v' + str(revision) + '/', pack, True

def _media_type(name, raw):
    suffix = pathlib.Path(name).suffix.lower()
    if suffix in ('.jpg', '.jpeg', '.png'):
        _decode_image(raw)
        return 'image/png' if suffix == '.png' else 'image/jpeg'
    if suffix == '.pdf' and raw.startswith(b'%PDF-'):
        return 'application/pdf'
    if suffix == '.json':
        json.loads(raw)
        return 'application/json; charset=utf-8'
    raise ValueError('unsupported persona asset type')

def summary(root):
    found = _pack(root)
    if found is None:
        return {'available': False}
    base, prefix, pack, pinned = found
    url = lambda name: '/base-personas/' + prefix + name
    def live_sha(name):
        return hashlib.sha256(_bytes(base, prefix, pack, name)).hexdigest()
    assets = {}
    for name, metadata in pack['assets'].items():
        info = dict(metadata)
        info['sha256'] = live_sha(name) if not pinned else metadata['sha256']
        assets[url(name)] = info
    result = {
        'available': True, 'id': pack['id'], 'slot': pack.get('slot') or ('v' + str(pack.get('revision'))),
        'revision': pack.get('revision'), 'title': pack['title'], 'status': pack['status'],
        'identity_reference_selected': bool(pack.get('identity_reference_selected')),
        'controlled_masks_approved': False, 'comparison_publication_approved': False,
        'future_image_model': pack['future_image_model'], 'keywords': pack['keywords'],
        'canonical_face_url': url(pack['canonical_face']),
        'canonical_face_sha256': live_sha(pack['canonical_face']) if not pinned else pack['canonical_face_sha256'],
        'canonical_body_url': url(pack['canonical_body']),
        'canonical_body_sha256': live_sha(pack['canonical_body']) if not pinned else pack['canonical_body_sha256'],
        'overview_url': url(pack['overview']), 'caveats': pack['caveats'], 'iteration_rule': pack['iteration_rule'],
        'selected_views': {key: url(name) for key, name in pack['selected_views'].items()}, 'assets': assets}
    if pack.get('selected_at'):
        result['selected_at'] = pack['selected_at']
    if pack.get('pdf'):
        result['pdf_url'] = url(pack['pdf'])
    return result

def _bytes(base, prefix, pack, name):
    if pack.get('slot') == 'latest' and name == pack.get('overview'):
        return latest_sheet.render_latest_sheet(base / prefix)
    return _read(base, prefix + name)

def asset(root, relative):
    found = _pack(root)
    if found is None:
        raise ValueError('no saved persona')
    base, prefix, pack, pinned = found
    if not relative.startswith(prefix):
        raise ValueError('persona version not selected')
    name = relative[len(prefix):]
    if name not in pack['assets']:
        raise ValueError('persona asset not allowlisted')
    raw = _bytes(base, prefix, pack, name)
    metadata = pack['assets'][name]
    if pinned and hashlib.sha256(raw).hexdigest() != metadata['sha256']:
        raise ValueError('persona asset integrity failed')
    return raw, _media_type(name, raw)
