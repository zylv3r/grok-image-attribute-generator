"""Isolated fixture tests for photographic preview checkpoints; no provider calls."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('photo_worker', ROOT / 'scripts' / 'generate_photographic_previews.py')
assert spec is not None and spec.loader is not None
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


class PhotoWorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR'))
        self.root = Path(self.temp.name)
        self.out = self.root / 'generated'; self.out.mkdir()
        (self.root / 'library.json').write_bytes((ROOT / 'library.json').read_bytes())
        self.patches = [patch.object(worker, 'ROOT', self.root), patch.object(worker, 'OUT', self.out),
                        patch.object(worker, 'MANIFEST', self.out / 'photographic-previews.json'),
                        patch.object(worker, 'ATLAS', self.out / 'preview-atlases')]
        for p in self.patches: p.start()

    def tearDown(self):
        for p in self.patches: p.stop()
        self.temp.cleanup()

    def fixture(self, aid='hair_color', vid='golden_blonde'):
        image_id = '1' * 32
        for suffix, size in [('.jpg', (128, 128)), ('-thumb.jpg', (64, 64))]:
            Image.new('RGB', size, '#c8a466').save(self.out / (image_id + suffix), 'JPEG')
        return {'id': image_id, 'selections': {aid: [vid]}, 'url': '/generated/' + image_id + '.jpg',
                'thumbnail_url': '/generated/' + image_id + '-thumb.jpg', 'width': 128, 'height': 128}

    def initialize(self):
        with patch.object(worker, 'api') as api, patch('sys.argv', ['worker', '--limit', '0']):
            worker.main(); api.assert_not_called()
        return json.loads(worker.MANIFEST.read_text())

    def test_inventory_is_exact_and_empty_run_makes_no_paid_calls(self):
        state = self.initialize()
        self.assertEqual((state['total'], len(state['tasks']), state['completed'], state['failed']), (893, 893, 0, 0))
        self.assertEqual(state['status'], 'paused')
        self.assertEqual(state['attributes'], {})

    def test_negative_limit_fails_before_any_request_or_checkpoint(self):
        with patch.object(worker, 'api') as api, patch('sys.argv', ['worker', '--limit', '-1']):
            with self.assertRaises(SystemExit) as stopped:
                worker.main()
            self.assertEqual(stopped.exception.code, 2)
            api.assert_not_called()
        self.assertFalse(worker.MANIFEST.exists())

    def test_actual_bytes_tags_urls_dimensions_and_symlinks_are_verified(self):
        record = self.fixture()
        self.assertTrue(worker.verified_record(record, 'hair_color', 'golden_blonde'))
        self.assertFalse(worker.verified_record(record, 'hair_color', 'platinum'))
        self.assertFalse(worker.verified_record(dict(record, width=999), 'hair_color', 'golden_blonde'))
        self.assertFalse(worker.verified_record(dict(record, url='/server.py'), 'hair_color', 'golden_blonde'))
        thumb = self.out / (record['id'] + '-thumb.jpg'); thumb.write_bytes(b'invalid-image')
        self.assertFalse(worker.verified_record(record, 'hair_color', 'golden_blonde'))

    def test_known_completed_job_is_reconciled_without_resubmission(self):
        state = self.initialize(); record = self.fixture(); key = 'hair_color:golden_blonde'
        state['tasks'][key].update(status='failed', job_id='2'*32, error='prior polling transport failed')
        worker.atomic_json(worker.MANIFEST, state)
        with patch.object(worker, 'api', return_value={'status': 'completed', 'results': [record]}) as api, patch('sys.argv', ['worker', '--limit', '0']):
            worker.main()
        self.assertEqual(api.call_count, 1)
        self.assertEqual(api.call_args.args[1], '/api/jobs/' + '2'*32)
        self.assertEqual(len(api.call_args.args), 2)
        result = json.loads(worker.MANIFEST.read_text()); self.assertEqual(result['completed'], 1)
        self.assertEqual(result['tasks'][key]['status'], 'completed')
        self.assertNotIn('error', result['tasks'][key])
        self.assertEqual(result['attributes']['hair_color']['values']['golden_blonde']['image_id'], record['id'])
        with Image.open(worker.ATLAS / 'hair_color.jpg') as atlas: self.assertEqual(atlas.size, (320, 240))

    def test_unknown_submission_is_ambiguous_not_blindly_retried(self):
        state = self.initialize(); state['tasks']['hair_color:golden_blonde']['status'] = 'running'
        worker.atomic_json(worker.MANIFEST, state)
        with patch.object(worker, 'api') as api, patch('sys.argv', ['worker', '--limit', '0']):
            worker.main(); api.assert_not_called()
        result = json.loads(worker.MANIFEST.read_text())
        self.assertEqual(result['tasks']['hair_color:golden_blonde']['status'], 'ambiguous')
        self.assertEqual(result['failed'], 1)

    def test_completed_checkpoint_is_checked_and_never_charged_again(self):
        state = self.initialize(); record = self.fixture(); key = 'hair_color:golden_blonde'
        state['tasks'][key].update(status='completed', image_id=record['id'], thumbnail_url=record['thumbnail_url'], example_url=record['url'])
        worker.atomic_json(worker.MANIFEST, state)
        with patch.object(worker, 'api', return_value=record) as api, patch('sys.argv', ['worker', '--limit', '0']):
            worker.main()
        self.assertEqual(api.call_args.args[1], '/api/images/' + record['id'])
        self.assertEqual(len(api.call_args.args), 2)
        self.assertEqual(json.loads(worker.MANIFEST.read_text())['completed'], 1)

    def test_target_age_is_not_overridden_and_examples_are_photographic(self):
        self.assertNotIn('28 years old', worker.framing('age', 'technical'))
        self.assertIn('No illustration', worker.framing('hair_color', 'hair'))
        self.assertIn('head through toes', worker.framing('pose', 'pose'))
        import server
        catalog = server.Catalog.load(ROOT / 'library.json')
        plan = catalog.preview({'selections': {'light_quality': ['hard']}, 'extra_prompt': worker.framing('light_quality', 'lighting')})['plans'][0]
        self.assertIn('crisp shadow edges', plan['prompt'])
        self.assertNotIn('soft shadow edges', plan['prompt'])


if __name__ == '__main__': unittest.main()
