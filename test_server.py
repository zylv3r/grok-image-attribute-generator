import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import server


class NativeGenerationTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.output_dir = Path(self.tempdir.name)

    def tearDown(self):
        self.tempdir.cleanup()

    def test_generate_batch_returns_one_local_image_url_per_successful_native_generation(self):
        raw = base64.b64encode(b'fake-image-bytes').decode()
        with patch.object(server, 'generate_native_image', return_value=(raw, 'image/jpeg')) as generate:
            body = server.generate_batch({'prompt': 'garden portrait', 'n': 2}, self.output_dir)

        self.assertEqual(len(body['data']), 2)
        self.assertEqual(generate.call_count, 2)
        self.assertTrue(all(item['url'].startswith('/generated/') for item in body['data']))
        self.assertEqual(len(list(self.output_dir.glob('*.jpg'))), 2)

    def test_generate_batch_passes_the_selected_xai_aspect_ratio_to_native_generation(self):
        raw = base64.b64encode(b'fake-image-bytes').decode()
        with patch.object(server, 'generate_native_image', return_value=(raw, 'image/jpeg')) as generate:
            server.generate_batch({'prompt': 'garden portrait', 'n': 1, 'aspect_ratio': '9:16'}, self.output_dir)

        generate.assert_called_once_with('garden portrait', '9:16')

    def test_generate_batch_rejects_empty_prompt(self):
        with self.assertRaisesRegex(ValueError, 'prompt'):
            server.generate_batch({'prompt': '   ', 'n': 1}, self.output_dir)

    def test_generate_batch_caps_batch_at_four(self):
        with self.assertRaisesRegex(ValueError, 'between 1 and 4'):
            server.generate_batch({'prompt': 'garden portrait', 'n': 5}, self.output_dir)


if __name__ == '__main__':
    unittest.main()
