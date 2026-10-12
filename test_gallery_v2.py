import os
import tempfile
import unittest
from pathlib import Path

from gallery import Gallery, save_image
from test_gallery import image_bytes


class GalleryV2Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = Gallery(self.root / 'gallery.sqlite3', self.root / 'generated')

    def tearDown(self):
        self.tmp.cleanup()

    def test_owned_image_requires_registered_canonical_regular_jpeg(self):
        record = save_image(image_bytes(), self.store.output_dir, '9:16')
        public = self.store.add_image(record, 'old portrait', {'age': ['age_24']})
        self.assertEqual(self.store.owned_image(public['id']), self.store.output_dir / record['filename'])
        self.assertIsNone(self.store.owned_image('../private'))
        self.assertIsNone(self.store.owned_image('a' * 32))
        path = self.store.output_dir / record['filename']
        path.unlink()
        path.symlink_to(self.root / 'private.jpg')
        self.assertIsNone(self.store.owned_image(public['id']))

    def test_historic_snapshot_and_discrete_age_tags_survive_reopen(self):
        record = save_image(image_bytes(), self.store.output_dir, '9:16')
        snap = {'age': {'name': 'Age at capture', 'type': 'exclusive', 'values': [{'id': 'age_24', 'name': 'Twenty four', 'steers': '24 years old'}]}}
        job = self.store.create_job([{'prompt': 'portrait', 'selections': {'age': ['age_24']},
                                    'resolved_selection_snapshot': snap}], '9:16')
        self.store.claim(job, 0)
        image = self.store.complete_plan(job, 0, record)
        reopened = Gallery(self.store.db_path, self.store.output_dir)
        self.assertEqual(reopened.image(image['id'])['resolved_selection_snapshot'], snap)
        self.assertEqual(reopened.query(filters={'age': ['age_24']})['total'], 1)
        self.assertEqual(reopened.query(filters={'age': ['age_2']})['total'], 0)

    def test_canonical_age_24_filter_reads_legacy_24_without_retagging(self):
        record = save_image(image_bytes(), self.store.output_dir, '9:16')
        old = self.store.add_image(record, 'legacy adult', {'age': ['24']})
        self.assertEqual(self.store.query(filters={'age': ['age_24']})['total'], 1)
        self.assertEqual(self.store.image(old['id'])['selections'], {'age': ['24']})
        with self.store.connect() as db:
            self.assertEqual([r['value'] for r in db.execute('SELECT value FROM image_tags')], ['24'])

if __name__ == '__main__':
    unittest.main()
