"""SQLite job/gallery persistence and verified local image storage."""
from __future__ import annotations

import base64
import io
import json
import math
import os
import re
import sqlite3
import tempfile
import warnings
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_PENDING_IMAGES = 24
MAX_IMAGE_BYTES = 32 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
SAFE_PROVIDER_ERROR = 'Image generation failed or returned an invalid image.'


class QueueFull(Exception):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


def save_image(encoded, output_dir, aspect_ratio=None):
    """Decode and validate actual pixels; metadata/MIME claims are never trusted."""
    if not isinstance(encoded, str) or len(encoded) > (MAX_IMAGE_BYTES * 4 // 3 + 4):
        raise ValueError('invalid image bytes')
    try:
        raw = base64.b64decode(encoded, validate=True)
        if not raw or len(raw) > MAX_IMAGE_BYTES:
            raise ValueError('invalid image bytes')
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as source:
                if source.width * source.height > MAX_IMAGE_PIXELS:
                    raise ValueError('image is too large')
                source.verify()
            with Image.open(io.BytesIO(raw)) as source:
                image = ImageOps.exif_transpose(source).convert('RGB')
                image.load()
    except (ValueError, OSError, UnidentifiedImageError, Image.DecompressionBombError,
            Image.DecompressionBombWarning) as exc:
        raise ValueError('invalid image bytes') from exc
    width, height = image.size
    if aspect_ratio:
        left, right = map(int, aspect_ratio.split(':'))
        # Permit integer pixel rounding and at most 2% provider ratio drift.
        if abs(width / height - left / right) > max(left / right * .02, 1 / height):
            raise ValueError('provider image has the wrong aspect ratio')
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    image_id = uuid4().hex
    filename, thumbnail = image_id + '.jpg', image_id + '-thumb.jpg'
    paths = [output_dir / filename, output_dir / thumbnail]
    temporary = []
    try:
        for index, path in enumerate(paths):
            if index:
                image.thumbnail((320, 320), Image.Resampling.LANCZOS)
            with tempfile.NamedTemporaryFile(dir=output_dir, prefix='.image-', suffix='.tmp', delete=False) as handle:
                temporary.append(Path(handle.name))
                image.save(handle, format='JPEG', quality=82 if index else 94)
                handle.flush()
                os.fsync(handle.fileno())
        for temp, path in zip(temporary, paths):
            os.replace(temp, path)
    except Exception:
        for path in paths:
            path.unlink(missing_ok=True)
        raise
    finally:
        for path in temporary:
            path.unlink(missing_ok=True)
    return {'id': image_id, 'filename': filename, 'thumbnail': thumbnail,
            'width': width, 'height': height,
            'aspect_ratio': aspect_ratio or f'{width // math.gcd(width, height)}:{height // math.gcd(width, height)}'}


class Gallery:
    def __init__(self, db_path, output_dir):
        self.db_path = Path(db_path)
        self.output_dir = Path(output_dir)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, status TEXT NOT NULL, total INTEGER NOT NULL,
                    completed INTEGER NOT NULL DEFAULT 0, failed INTEGER NOT NULL DEFAULT 0,
                    aspect_ratio TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS plans (
                    job_id TEXT NOT NULL REFERENCES jobs(id), ordinal INTEGER NOT NULL,
                    selections TEXT NOT NULL, prompt TEXT NOT NULL, status TEXT NOT NULL,
                    image_id TEXT, error TEXT,
                    PRIMARY KEY(job_id, ordinal)
                );
                CREATE TABLE IF NOT EXISTS images (
                    id TEXT PRIMARY KEY, filename TEXT NOT NULL UNIQUE,
                    thumbnail TEXT NOT NULL, prompt TEXT NOT NULL, selections TEXT NOT NULL,
                    width INTEGER NOT NULL, height INTEGER NOT NULL,
                    created_at TEXT NOT NULL, aspect_ratio TEXT NOT NULL,
                    job_id TEXT REFERENCES jobs(id), ordinal INTEGER
                );
                CREATE TABLE IF NOT EXISTS image_tags (
                    image_id TEXT NOT NULL REFERENCES images(id) ON DELETE CASCADE,
                    attribute TEXT NOT NULL, value TEXT NOT NULL,
                    PRIMARY KEY(image_id, attribute, value)
                );
                CREATE INDEX IF NOT EXISTS tags_filter ON image_tags(attribute, value, image_id);
                CREATE INDEX IF NOT EXISTS images_date ON images(created_at DESC, id DESC);
                CREATE INDEX IF NOT EXISTS images_aspect ON images(aspect_ratio, created_at DESC, id DESC);
                CREATE INDEX IF NOT EXISTS images_thumbnail ON images(thumbnail);
                CREATE INDEX IF NOT EXISTS images_job ON images(job_id, ordinal);
                CREATE INDEX IF NOT EXISTS jobs_status ON jobs(status);
                CREATE VIRTUAL TABLE IF NOT EXISTS images_search USING fts5(image_id UNINDEXED, prompt);
                CREATE TABLE IF NOT EXISTS legacy_imports (filename TEXT PRIMARY KEY);
            ''')
            # Additive migration: old records retain explicit unknown provenance.
            for table in ('plans', 'images'):
                columns = {row['name'] for row in db.execute(f'PRAGMA table_info({table})')}
                for name, kind in (('library_hash', 'TEXT'), ('selection_sampling_seed', 'INTEGER'),
                                   ('requested_selection_snapshot', 'TEXT'), ('resolved_selection_snapshot', 'TEXT')):
                    if name not in columns:
                        db.execute(f'ALTER TABLE {table} ADD COLUMN {name} {kind}')
            db.execute('CREATE INDEX IF NOT EXISTS plans_status ON plans(status,job_id)')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(str(self.db_path), timeout=15)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA busy_timeout=15000')
        try:
            with db:
                yield db
        finally:
            db.close()

    def create_job(self, plans, aspect_ratio):
        if not 1 <= len(plans) <= MAX_PENDING_IMAGES:
            raise ValueError('jobs require between 1 and 24 image plans')
        job_id = uuid4().hex
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            pending = db.execute("SELECT COALESCE(SUM(total-completed-failed),0) FROM jobs WHERE status IN ('queued','running')").fetchone()[0]
            if pending + len(plans) > MAX_PENDING_IMAGES:
                raise QueueFull('generation queue is full; try again later')
            db.execute('INSERT INTO jobs(id,status,total,aspect_ratio,created_at) VALUES (?,?,?,?,?)',
                       (job_id, 'queued', len(plans), aspect_ratio, now()))
            db.executemany('''INSERT INTO plans(job_id,ordinal,selections,prompt,status,library_hash,
                           selection_sampling_seed,requested_selection_snapshot,resolved_selection_snapshot)
                           VALUES (?,?,?,?,?,?,?,?,?)''',
                           [(job_id, i, json.dumps(p['selections']), p['prompt'], 'queued', p.get('library_hash'),
                             p.get('selection_sampling_seed'), json.dumps(p.get('requested_selection_snapshot')),
                             json.dumps(p.get('resolved_selection_snapshot'))) for i, p in enumerate(plans)])
        return job_id

    def recover(self):
        """Finalize interrupted work, retaining successes without retrying paid calls."""
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            ids = db.execute("SELECT id FROM jobs WHERE status IN ('queued','running')").fetchall()
            for row in ids:
                db.execute("UPDATE plans SET status='failed',error=? WHERE job_id=? AND status IN ('queued','running')",
                           ('Generation interrupted by server shutdown; submit a new job to retry.', row['id']))
                self._finish_job(db, row['id'])

    def claim(self, job_id, ordinal):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            cursor = db.execute("UPDATE plans SET status='running' WHERE job_id=? AND ordinal=? AND status='queued'", (job_id, ordinal))
            if cursor.rowcount:
                db.execute("UPDATE jobs SET status='running' WHERE id=?", (job_id,))
            return bool(cursor.rowcount)

    def _insert_image(self, db, record, prompt, selections, job_id=None, ordinal=None, provenance=None):
        provenance = dict(provenance or {})
        record = dict(record, prompt=prompt, selections=selections, created_at=now(), ordinal=ordinal,
                      **{key: provenance.get(key) for key in ('library_hash', 'selection_sampling_seed',
                         'requested_selection_snapshot', 'resolved_selection_snapshot')})
        db.execute('''INSERT INTO images(id,filename,thumbnail,prompt,selections,width,height,created_at,
                   aspect_ratio,job_id,ordinal,library_hash,selection_sampling_seed,
                   requested_selection_snapshot,resolved_selection_snapshot) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                   (record['id'], record['filename'], record['thumbnail'], prompt, json.dumps(selections),
                    record['width'], record['height'], record['created_at'], record['aspect_ratio'], job_id, ordinal,
                    record['library_hash'], record['selection_sampling_seed'],
                    record['requested_selection_snapshot'], record['resolved_selection_snapshot']))
        db.executemany('INSERT INTO image_tags(image_id,attribute,value) VALUES (?,?,?)',
                       [(record['id'], attribute, value) for attribute, values in selections.items() for value in values])
        db.execute('INSERT INTO images_search(image_id,prompt) VALUES (?,?)', (record['id'], prompt))
        return self._public(record)

    @staticmethod
    def _public(row):
        row = dict(row)
        return {'id': row['id'], 'url': '/generated/' + row['filename'],
                'thumbnail_url': '/generated/' + row['thumbnail'], 'prompt': row['prompt'],
                'selections': json.loads(row['selections']) if isinstance(row['selections'], str) else row['selections'],
                'width': row['width'], 'height': row['height'], 'created_at': row['created_at'],
                'aspect_ratio': row['aspect_ratio'], 'plan_index': row.get('ordinal'),
                'library_hash': row.get('library_hash'), 'selection_sampling_seed': row.get('selection_sampling_seed'),
                **{key: json.loads(row[key]) if isinstance(row.get(key), str) else row.get(key)
                   for key in ('requested_selection_snapshot', 'resolved_selection_snapshot')}}

    def cleanup_image(self, record):
        for key in ('filename', 'thumbnail'):
            (self.output_dir / record[key]).unlink(missing_ok=True)

    def add_image(self, record, prompt, selections):
        try:
            with self.connect() as db:
                return self._insert_image(db, record, prompt, selections)
        except Exception:
            self.cleanup_image(record)
            raise

    def complete_plan(self, job_id, ordinal, record=None, error=None):
        try:
            return self._complete_plan(job_id, ordinal, record, error)
        except Exception:
            if record:
                self.cleanup_image(record)
            raise

    def _complete_plan(self, job_id, ordinal, record=None, error=None):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            plan = db.execute('SELECT * FROM plans WHERE job_id=? AND ordinal=?', (job_id, ordinal)).fetchone()
            if plan is None or plan['status'] != 'running':
                raise RuntimeError('plan is not running')
            public = None
            if record:
                public = self._insert_image(db, record, plan['prompt'], json.loads(plan['selections']), job_id, ordinal, plan)
                db.execute("UPDATE plans SET status='completed',image_id=? WHERE job_id=? AND ordinal=?", (record['id'], job_id, ordinal))
            else:
                db.execute("UPDATE plans SET status='failed',error=? WHERE job_id=? AND ordinal=?", (error or SAFE_PROVIDER_ERROR, job_id, ordinal))
            self._finish_job(db, job_id)
        return public

    def health(self):
        with self.connect() as db:
            db.execute('BEGIN')
            jobs = {status: 0 for status in ('queued', 'running', 'completed', 'partial', 'failed')}
            jobs.update(dict(db.execute('SELECT status,COUNT(*) FROM jobs GROUP BY status').fetchall()))
            pending = db.execute("SELECT COUNT(*) FROM plans WHERE status IN ('queued','running')").fetchone()[0]
            images = db.execute('SELECT COUNT(*) FROM images').fetchone()[0]
        return {'status': 'ok', 'job_counts': jobs, 'pending_images': pending,
                'image_count': images, 'pending_limit': MAX_PENDING_IMAGES, 'provider_concurrency_limit': 4}

    @staticmethod
    def _finish_job(db, job_id):
        counts = dict(db.execute('SELECT status, COUNT(*) FROM plans WHERE job_id=? GROUP BY status', (job_id,)).fetchall())
        completed, failed = counts.get('completed', 0), counts.get('failed', 0)
        pending = counts.get('queued', 0) + counts.get('running', 0)
        status = 'running' if pending else ('partial' if completed and failed else 'completed' if completed else 'failed')
        db.execute('UPDATE jobs SET status=?,completed=?,failed=? WHERE id=?', (status, completed, failed, job_id))

    def job(self, job_id):
        with self.connect() as db:
            db.execute('BEGIN')
            job = db.execute('SELECT id,status,total,completed,failed FROM jobs WHERE id=?', (job_id,)).fetchone()
            if job is None:
                return None
            result = dict(job)
            result['results'] = [self._public(row) for row in db.execute('SELECT * FROM images WHERE job_id=? ORDER BY ordinal', (job_id,))]
            result['errors'] = [{'index': row['ordinal'], 'error': row['error']} for row in db.execute("SELECT ordinal,error FROM plans WHERE job_id=? AND status='failed' ORDER BY ordinal", (job_id,))]
            return result

    def image(self, image_id):
        with self.connect() as db:
            row = db.execute('SELECT * FROM images WHERE id=?', (image_id,)).fetchone()
            return self._public(row) if row else None

    def asset(self, filename):
        with self.connect() as db:
            row = db.execute('SELECT 1 FROM images WHERE filename=? OR thumbnail=? LIMIT 1', (filename, filename)).fetchone()
        return self.output_dir / filename if row else None

    def owned_image(self, image_id):
        """Resolve only registered original JPEGs; browser paths are never accepted."""
        if not isinstance(image_id, str) or not re.fullmatch(r'[0-9a-f]{32}', image_id):
            return None
        filename = image_id + '.jpg'
        with self.connect() as db:
            row = db.execute('SELECT filename FROM images WHERE id=?', (image_id,)).fetchone()
        if not row or row['filename'] != filename or self.output_dir.is_symlink():
            return None
        path = self.output_dir / filename
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(self.output_dir.resolve()):
            return None
        return path

    def set_filter_aliases(self, aliases):
        """Expand only safe one-to-one moves; preserve archived tags and recipes."""
        self.filter_aliases = {}
        for old, alias in aliases.items():
            targets = alias.get('targets', [])
            if alias.get('disposition') != 'move' or len(targets) != 1:
                continue
            target = targets[0]
            canonical = (target['attribute_id'], target['value_id'])
            self.filter_aliases.setdefault(canonical, set()).add(tuple(old.split(':', 1)))

    def query(self, q='', page=1, page_size=24, filters=None, aspect_ratio=''):
        if isinstance(page, bool) or not isinstance(page, int) or not 1 <= page <= 10000:
            raise ValueError('page must be between 1 and 10000')
        if isinstance(page_size, bool) or not isinstance(page_size, int) or not 1 <= page_size <= 100:
            raise ValueError('page_size must be between 1 and 100')
        if not isinstance(q, str) or len(q) > 500:
            raise ValueError('q must be at most 500 characters')
        where, args = [], []
        if q.strip():
            terms = ['"' + word.replace('"', '""') + '"' for word in q.split()]
            where.append('i.id IN (SELECT image_id FROM images_search WHERE images_search MATCH ?)')
            args.append(' AND '.join(terms))
        if aspect_ratio:
            where.append('i.aspect_ratio=?')
            args.append(aspect_ratio)
        for attribute, values in (filters or {}).items():
            if not values:
                continue
            # Exact legacy 24 alias, without rewriting historic tags or lexical
            # comparisons (age_2 must never match age_24).
            if attribute == 'age' and ('age_24' in values or '24' in values):
                values = list(dict.fromkeys([*values, 'age_24', '24']))
            pairs = {(attribute, value) for value in values}
            for value in values:
                pairs.update(getattr(self, 'filter_aliases', {}).get((attribute, value), set()))
            pairs = sorted(pairs)
            where.append('i.id IN (SELECT image_id FROM image_tags WHERE ' +
                         ' OR '.join('(attribute=? AND value=?)' for _ in pairs) + ')')
            args.extend(part for pair in pairs for part in pair)
        clause = ' WHERE ' + ' AND '.join(where) if where else ''
        with self.connect() as db:
            db.execute('BEGIN')
            total = db.execute('SELECT COUNT(*) FROM images i' + clause, args).fetchone()[0]
            rows = db.execute('SELECT i.* FROM images i' + clause + ' ORDER BY i.created_at DESC,i.id DESC LIMIT ? OFFSET ?',
                              [*args, page_size, (page - 1) * page_size]).fetchall()
        return {'items': [self._public(row) for row in rows], 'total': total, 'page': page,
                'page_size': page_size, 'pages': math.ceil(total / page_size)}

    def import_legacy(self):
        """Opt-in import of verified files, with empty prompts/tags when unknown."""
        imported = 0
        for path in self.output_dir.iterdir():
            if path.is_symlink() or not path.is_file() or path.suffix.lower() not in {'.png', '.jpg', '.jpeg', '.webp'} or path.name.endswith('-thumb.jpg'):
                continue
            with self.connect() as db:
                known = db.execute('SELECT 1 FROM images WHERE filename=? UNION SELECT 1 FROM legacy_imports WHERE filename=?', (path.name, path.name)).fetchone()
            if known or path.stat().st_size > MAX_IMAGE_BYTES:
                continue
            try:
                record = save_image(base64.b64encode(path.read_bytes()).decode('ascii'), self.output_dir)
            except ValueError:
                continue
            try:
                with self.connect() as db:
                    self._insert_image(db, record, '', {})
                    db.execute('INSERT INTO legacy_imports(filename) VALUES (?)', (path.name,))
            except Exception:
                self.cleanup_image(record)
                raise
            imported += 1
        return imported
