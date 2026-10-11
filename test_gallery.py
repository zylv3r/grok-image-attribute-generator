import base64
import io
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from gallery import Gallery, QueueFull, save_image


def image_bytes(size=(90, 160), color='red', fmt='PNG'):
    buffer = io.BytesIO()
    Image.new('RGB', size, color).save(buffer, format=fmt)
    return base64.b64encode(buffer.getvalue()).decode('ascii')


class GalleryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR', '/tmp'))
        self.root = Path(self.tmp.name)
        self.store = Gallery(self.root / 'gallery.sqlite3', self.root / 'generated')

    def tearDown(self):
        self.tmp.cleanup()

    def add(self, prompt, selections, aspect='9:16'):
        size = (90, 160) if aspect == '9:16' else (160, 90)
        record = save_image(image_bytes(size), self.store.output_dir, aspect)
        return self.store.add_image(record, prompt, selections)

    def test_verified_pixels_dimensions_and_smaller_thumbnail(self):
        record = save_image(image_bytes((900, 1600)), self.store.output_dir, '9:16')
        self.assertEqual((record['width'], record['height']), (900, 1600))
        with Image.open(self.store.output_dir / record['filename']) as full:
            self.assertEqual(full.size, (900, 1600))
            full.verify()
        with Image.open(self.store.output_dir / record['thumbnail']) as thumb:
            self.assertEqual(thumb.size, (180, 320))
            thumb.verify()

    def test_atomic_replacements_and_cleanup_after_second_replace_failure(self):
        replace = os.replace
        calls = []

        def fail_second(source, destination):
            self.assertEqual(Path(source).parent, self.store.output_dir)
            self.assertEqual(Path(destination).parent, self.store.output_dir)
            self.assertTrue(Path(source).is_file())
            calls.append(destination)
            if len(calls) == 2:
                raise OSError('mock interrupted thumbnail rename')
            return replace(source, destination)

        with patch('gallery.os.replace', side_effect=fail_second):
            with self.assertRaises(OSError):
                save_image(image_bytes(), self.store.output_dir, '9:16')
        self.assertEqual(len(calls), 2)
        self.assertEqual(list(self.store.output_dir.iterdir()), [])
        with patch('gallery.os.replace', wraps=replace) as atomic:
            record = save_image(image_bytes(), self.store.output_dir, '9:16')
        self.assertEqual(atomic.call_count, 2)
        self.assertEqual(set(p.name for p in self.store.output_dir.iterdir()), {record['filename'], record['thumbnail']})

    def test_database_failure_rolls_back_tags_and_cleans_full_image_and_thumbnail(self):
        with self.store.connect() as db:
            db.execute("CREATE TRIGGER reject_image BEFORE INSERT ON images BEGIN SELECT RAISE(ABORT, 'mock disk failure'); END")
        for async_plan in (False, True):
            record = save_image(image_bytes(), self.store.output_dir, '9:16')
            with self.assertRaises(sqlite3.IntegrityError):
                if async_plan:
                    job = self.store.create_job([{'prompt': 'portrait', 'selections': {'camera': ['on']}}], '9:16')
                    self.store.claim(job, 0)
                    self.store.complete_plan(job, 0, record)
                else:
                    self.store.add_image(record, 'portrait', {'camera': ['on']})
            self.assertEqual(list(self.store.output_dir.iterdir()), [])
            self.assertEqual(self.store.query()['total'], 0)
            if async_plan:
                self.store.complete_plan(job, 0, error='safe failure')
                self.assertEqual(self.store.job(job)['status'], 'failed')

    def test_old_sqlite_schema_migrates_and_persists_new_provenance_with_explicit_columns(self):
        old_db = self.root / 'old.sqlite3'
        record = save_image(image_bytes(), self.store.output_dir, '9:16')
        with sqlite3.connect(old_db) as db:
            db.execute('''CREATE TABLE images (id TEXT PRIMARY KEY,filename TEXT NOT NULL UNIQUE,
                       thumbnail TEXT NOT NULL,prompt TEXT NOT NULL,selections TEXT NOT NULL,
                       width INTEGER NOT NULL,height INTEGER NOT NULL,created_at TEXT NOT NULL,
                       aspect_ratio TEXT NOT NULL,job_id TEXT,ordinal INTEGER)''')
            db.execute('''CREATE TABLE plans (job_id TEXT NOT NULL,ordinal INTEGER NOT NULL,
                       selections TEXT NOT NULL,prompt TEXT NOT NULL,status TEXT NOT NULL,
                       image_id TEXT,error TEXT,PRIMARY KEY(job_id,ordinal))''')
            db.execute('INSERT INTO images VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                       (record['id'], record['filename'], record['thumbnail'], 'old prompt', '{"removed":["old-id"]}',
                        90, 160, '2020-01-01', '9:16', None, None))
        migrated = Gallery(old_db, self.store.output_dir)
        old = migrated.image(record['id'])
        self.assertEqual(old['selections'], {'removed': ['old-id']})
        self.assertIsNone(old['library_hash'])
        self.assertIsNone(old['selection_sampling_seed'])
        self.assertIsNone(old['requested_selection_snapshot'])
        snapshot = {'hair': {'name': 'Historical Hair', 'type': 'exclusive',
                             'values': [{'id': 'old', 'name': 'Old hair', 'steers': 'historical steer'}]}}
        plan = {'prompt': 'new prompt', 'selections': {'hair': ['old']}, 'library_hash': 'a' * 64,
                'selection_sampling_seed': 123, 'requested_selection_snapshot': {'selections': snapshot, 'whitelist': {}},
                'resolved_selection_snapshot': snapshot}
        job = migrated.create_job([plan, plan], '9:16')
        for index in range(2):
            migrated.claim(job, index)
            migrated.complete_plan(job, index, save_image(image_bytes(), migrated.output_dir, '9:16'))
        reopened = Gallery(old_db, migrated.output_dir)
        for index, item in enumerate(reopened.job(job)['results']):
            self.assertEqual(item['plan_index'], index)
            self.assertEqual(item['library_hash'], plan['library_hash'])
            self.assertEqual(item['selection_sampling_seed'], 123)
            self.assertEqual(item['resolved_selection_snapshot'], snapshot)
            self.assertEqual(item['requested_selection_snapshot'], plan['requested_selection_snapshot'])
        self.assertEqual(reopened.query()['total'], 3)
        self.assertEqual(reopened.image(record['id']), old)

    def test_invalid_truncated_bytes_and_wrong_aspect_never_saved(self):
        for raw in ('invalid base64!', 'é', '!!!!', None, b'YWJj', base64.b64encode(b'fake-image-bytes').decode(), image_bytes((160, 90))):
            with self.subTest(raw=str(raw)[:30]):
                with self.assertRaises(ValueError):
                    save_image(raw, self.store.output_dir, '9:16')
        truncated = base64.b64encode(base64.b64decode(image_bytes())[:30]).decode()
        with self.assertRaises(ValueError):
            save_image(truncated, self.store.output_dir, '9:16')
        self.assertEqual(list(self.store.output_dir.iterdir()), [])

    def test_or_within_attribute_and_across_all_attributes_and_prompt_search(self):
        a = self.add('Golden garden portrait', {'skin': ['fair'], 'hair': ['red'], 'pose': ['seated', 'smile'], 'camera': ['on']})
        self.add('Golden garden portrait', {'skin': ['tan'], 'hair': ['red'], 'pose': ['standing'], 'camera': ['off']})
        self.add('Evening indoor portrait', {'skin': ['fair'], 'hair': ['black'], 'pose': ['seated'], 'camera': ['on']})
        result = self.store.query(q='golden garden', filters={'skin': ['fair', 'tan'], 'hair': ['red'], 'pose': ['seated', 'smile'], 'camera': ['on']})
        self.assertEqual([r['id'] for r in result['items']], [a['id']])
        self.assertEqual(self.store.query(q='" OR * --')['total'], 0)
        self.assertEqual(self.store.query(filters={'skin': ["' OR 1=1 --"]})['total'], 0)
        with self.store.connect() as db:
            indexes = {row['name'] for row in db.execute("PRAGMA index_list('image_tags')")}
        self.assertIn('tags_filter', indexes)

    def test_pagination_details_aspect_and_reopening_persistence(self):
        items = [self.add('portrait', {'value': [str(i)]}) for i in range(5)]
        self.add('landscape', {}, '16:9')
        result = self.store.query(page=2, page_size=2, aspect_ratio='9:16')
        self.assertEqual((result['total'], result['pages'], len(result['items'])), (5, 3, 2))
        self.assertEqual([r['id'] for r in result['items']], [items[2]['id'], items[1]['id']])
        reopened = Gallery(self.store.db_path, self.store.output_dir)
        self.assertEqual(reopened.image(items[0]['id']), items[0])
        self.assertEqual(reopened.query()['total'], 6)
        self.assertEqual(reopened.query(page=9)['items'], [])
        self.assertIsNone(reopened.image('missing'))
        self.assertIsNone(reopened.asset('gallery.sqlite3'))
        for kwargs in ({'page': 0}, {'page': 10001}, {'page_size': 0}, {'page_size': 101}, {'q': 'x' * 501}):
            with self.assertRaises(ValueError):
                reopened.query(**kwargs)

    def test_bounded_queue_partial_success_and_recovery(self):
        plans = [{'selections': {'camera': ['on']}, 'prompt': 'portrait'}] * 24
        job = self.store.create_job(plans, '9:16')
        self.assertEqual(self.store.job(job)['status'], 'queued')
        with self.assertRaises(QueueFull):
            self.store.create_job(plans[:1], '9:16')
        self.assertTrue(self.store.claim(job, 0))
        self.assertFalse(self.store.claim(job, 0))
        record = save_image(image_bytes(), self.store.output_dir, '9:16')
        self.store.complete_plan(job, 0, record=record)
        self.store.claim(job, 1)
        recovered = Gallery(self.store.db_path, self.store.output_dir)
        recovered.recover()
        status = recovered.job(job)
        self.assertEqual((status['status'], status['completed'], status['failed']), ('partial', 1, 23))
        self.assertEqual(status['results'][0]['selections'], {'camera': ['on']})
        self.assertEqual(len(status['errors']), 23)
        recovered.recover()
        self.assertEqual(recovered.job(job), status)
        self.assertIsNotNone(recovered.create_job(plans, '9:16'))

    def test_all_failure_recovery_and_completed_jobs_preserved(self):
        plans = [{'prompt': 'portrait', 'selections': {}}]
        interrupted = self.store.create_job(plans, '9:16')
        success = self.store.create_job(plans, '9:16')
        self.store.claim(success, 0)
        self.store.complete_plan(success, 0, save_image(image_bytes(), self.store.output_dir, '9:16'))
        self.store.recover()
        self.assertEqual(self.store.job(interrupted)['status'], 'failed')
        self.assertEqual(self.store.job(success)['status'], 'completed')

    def test_optional_legacy_import_has_no_invented_tags_and_is_idempotent(self):
        (self.store.output_dir / 'legacy.png').write_bytes(base64.b64decode(image_bytes()))
        (self.store.output_dir / 'broken.jpg').write_bytes(b'broken')
        self.assertEqual(self.store.query()['total'], 0)
        self.assertEqual(self.store.import_legacy(), 1)
        self.assertEqual(self.store.import_legacy(), 0)
        imported = self.store.query()['items'][0]
        self.assertEqual(imported['selections'], {})
        self.assertEqual(imported['prompt'], '')
        self.assertEqual((imported['width'], imported['height']), (90, 160))


if __name__ == '__main__':
    unittest.main()
