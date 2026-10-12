"""Installation-wide archival presets. Independent of generation/catalog validation."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import uuid

DRAFT_LIMIT = 65_536
IMPORT_LIMIT = 180_000
FORBIDDEN = {'__proto__', 'prototype', 'constructor'}


class PresetError(ValueError):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def bounded_json(value, limit):
    nodes = 0
    def visit(item, depth=0):
        nonlocal nodes
        nodes += 1
        if depth > 16 or nodes > 10_000:
            raise ValueError('preset structure is too large or deep')
        if isinstance(item, dict):
            if len(item) > 512:
                raise ValueError('too many preset fields')
            for key, child in item.items():
                if not isinstance(key, str) or len(key) > 256 or key in FORBIDDEN:
                    raise ValueError('unsafe preset field')
                visit(child, depth + 1)
        elif isinstance(item, list):
            if len(item) > 1024:
                raise ValueError('preset array is too large')
            for child in item:
                visit(child, depth + 1)
        elif isinstance(item, float) and not math.isfinite(item):
            raise ValueError('invalid preset number')
        elif item is not None and not isinstance(item, (str, bool, int, float)):
            raise ValueError('invalid preset value')
    visit(value)
    encoded = canonical(value)
    if len(encoded.encode()) > limit:
        raise ValueError('preset data is too large')
    return encoded


def validate_record(name, draft):
    if not isinstance(name, str) or not name.strip() or len(name) > 80 or any(ord(c) < 32 for c in name):
        raise ValueError('preset name must be 1–80 characters without control characters')
    if not isinstance(draft, dict):
        raise ValueError('preset draft must be an object')
    encoded = bounded_json(draft, DRAFT_LIMIT)
    # Validate structure, never require known IDs or a generatable combination.
    for field in ('selections', 'whitelist'):
        choices = draft.get(field, {})
        if not isinstance(choices, dict):
            raise ValueError(f'{field} must be an object')
        for aid, ids in choices.items():
            if not aid or len(aid) > 128 or not isinstance(ids, list) or len(ids) > 512 or any(not isinstance(v, str) or not v or len(v) > 128 for v in ids):
                raise ValueError(f'invalid {field} IDs')
    return name, encoded


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


class Presets:
    def __init__(self, path, catalog_hash):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.catalog_hash = catalog_hash
        with self._connection() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS presets (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, draft TEXT NOT NULL,
                    schema_version INTEGER NOT NULL, catalog_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS requests (
                    request_key TEXT PRIMARY KEY, digest TEXT NOT NULL, preset_id TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS imports (
                    digest TEXT PRIMARY KEY, preset_id TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS archives (
                    digest TEXT PRIMARY KEY, envelope TEXT NOT NULL, warnings TEXT NOT NULL);
            ''')

    @contextmanager
    def _connection(self, write=False):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            if write:
                db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _record(row):
        if row is None:
            return None
        record = dict(row)
        record['draft'] = json.loads(record['draft'])
        return record

    def _insert(self, db, name, encoded, schema_version=1, catalog_hash=None):
        pid = uuid.uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        db.execute('INSERT INTO presets VALUES (?,?,?,?,?,?,?)',
                   (pid, name, encoded, schema_version, catalog_hash if catalog_hash is not None else self.catalog_hash, now, now))
        return self._record(db.execute('SELECT * FROM presets WHERE id=?', (pid,)).fetchone())

    def list(self):
        with self._connection() as db:
            return [self._record(row) for row in db.execute('SELECT * FROM presets ORDER BY created_at, id')]

    def create(self, payload):
        if set(payload) != {'name', 'draft', 'request_key'}:
            raise ValueError('name, draft and request_key are required')
        name, encoded = validate_record(payload['name'], payload['draft'])
        key = payload['request_key']
        if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', key):
            raise ValueError('request_key must be 1–128 safe characters')
        fingerprint = digest({'name': name, 'draft': payload['draft']})
        with self._connection(write=True) as db:
            prior = db.execute('SELECT * FROM requests WHERE request_key=?', (key,)).fetchone()
            if prior:
                if prior['digest'] != fingerprint:
                    raise PresetError(409, 'request_key was used with different preset data')
                preset = self._record(db.execute('SELECT * FROM presets WHERE id=?', (prior['preset_id'],)).fetchone())
                if preset is None:
                    raise PresetError(410, 'This saved preset was deleted; retry cannot restore it.')
                return preset, False
            preset = self._insert(db, name, encoded)
            db.execute('INSERT INTO requests VALUES (?,?,?)', (key, fingerprint, preset['id']))
            return preset, True

    def delete(self, pid):
        if not re.fullmatch(r'[0-9a-f]{32}', pid):
            raise PresetError(404, 'preset not found')
        with self._connection(write=True) as db:
            db.execute('DELETE FROM presets WHERE id=?', (pid,))
            # Ledgers remain as tombstones: late saves/imports cannot resurrect.

    def import_legacy(self, payload):
        if set(payload) - {'presets', 'raw_text'} or not isinstance(payload.get('presets'), list) or len(payload['presets']) > 256:
            raise ValueError('import requires a bounded presets array')
        if 'raw_text' in payload and not isinstance(payload['raw_text'], str):
            raise ValueError('raw_text must be a string')
        envelope = bounded_json(payload, IMPORT_LIMIT)
        warnings = []
        records = []
        if 'raw_text' in payload:
            try:
                raw = json.loads(payload['raw_text'])
                if not isinstance(raw, list) or raw != payload['presets']:
                    warnings.append('Legacy raw text was archived; its envelope needs attention.')
            except (ValueError, RecursionError):
                warnings.append('Malformed legacy text was archived; the browser original is retained.')
        for index, record in enumerate(payload['presets']):
            try:
                if not isinstance(record, dict) or not isinstance(record.get('id'), str) or not 0 < len(record['id']) <= 128:
                    raise ValueError('missing or invalid legacy ID')
                name, encoded = validate_record(record.get('name'), record.get('draft'))
                version = record.get('schema_version', 1)
                catalog_hash = record.get('catalog_hash', self.catalog_hash)
                if type(version) is not int or not 1 <= version <= 1_000_000 or not isinstance(catalog_hash, str) or len(catalog_hash) > 128:
                    raise ValueError('unsupported legacy metadata')
                records.append((digest(record), name, encoded, version, catalog_hash))
            except ValueError as exc:
                warnings.append(f'Legacy record {index + 1} archived for recovery: {exc}')
        # Raw text/envelopes survive, while semantic record digests ignore JSON key order.
        with self._connection(write=True) as db:
            db.execute('INSERT OR IGNORE INTO archives VALUES (?,?,?)', (digest(payload), envelope, canonical(warnings)))
            for fingerprint, name, encoded, version, catalog_hash in records:
                prior = db.execute('SELECT preset_id FROM imports WHERE digest=?', (fingerprint,)).fetchone()
                if prior:
                    continue
                preset = self._insert(db, name, encoded, version, catalog_hash)
                db.execute('INSERT INTO imports VALUES (?,?)', (fingerprint, preset['id']))
        return {'presets': self.list(), 'warnings': warnings}

    def archives(self):
        with self._connection() as db:
            return [{'envelope': json.loads(row['envelope']), 'warnings': json.loads(row['warnings'])}
                    for row in db.execute('SELECT * FROM archives ORDER BY rowid')]
