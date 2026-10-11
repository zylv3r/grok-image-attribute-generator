"""Regression controls for the operator-approved final council amendment."""
import json
import unittest
from pathlib import Path

import server
import test_server


class SamplingAmendmentTests(unittest.TestCase):
    def test_seven_four_value_whitelists_all_vary_reproducibly(self):
        catalog = server.Catalog.load(server.ROOT / 'library.json')
        aids = ['age', 'aperture', 'background_prop', 'bag_style', 'belt_style', 'blush_placement', 'body_build']
        whitelist = {aid: [v['id'] for v in catalog.attributes[aid]['values'][:4]] for aid in aids}
        payload = {'mode': 'variations', 'n': 24, 'seed': 3, 'whitelist': whitelist}
        result = catalog.preview(payload)
        self.assertEqual(result, catalog.preview(payload))
        self.assertEqual(len({json.dumps(p['selections'], sort_keys=True) for p in result['plans']}), 24)
        for aid in aids:
            self.assertGreaterEqual(len({tuple(p['selections'][aid]) for p in result['plans']}), 2, aid)
        self.assertTrue(all(catalog.conflict(p['selections']) is None for p in result['plans']))

    def test_full_catalog_whitelists_do_not_freeze_early_attributes(self):
        catalog = server.Catalog.load(server.ROOT / 'library.json')
        whitelist = {aid: [v['id'] for v in a['values']] for aid, a in catalog.attributes.items()}
        payload = {'mode': 'variations', 'n': 24, 'seed': 2, 'whitelist': whitelist}
        result = catalog.preview(payload)
        self.assertEqual(result, catalog.preview(payload))
        for aid, ids in whitelist.items():
            if len(ids) > 1:
                self.assertGreaterEqual(len({tuple(p['selections'][aid]) for p in result['plans']}), 2, aid)
        self.assertTrue(all(catalog.conflict(p['selections']) is None for p in result['plans']))


class BoundaryAmendmentTests(unittest.TestCase):
    setUp = test_server.HTTPTests.setUp
    tearDown = test_server.HTTPTests.tearDown
    request = test_server.HTTPTests.request

    def test_transfer_encoding_empty_or_duplicate_is_rejected_before_provider(self):
        for value in ['', '\r\nTransfer-Encoding: chunked', 'chunked', 'identity\r\nTransfer-Encoding:']:
            for endpoint in ['/api/jobs', '/api/generate']:
                payload = {} if endpoint == '/api/jobs' else {'prompt': 'fixture'}
                with self.subTest(value=value, endpoint=endpoint):
                    self.assertEqual(self.request('POST', endpoint, payload, headers={'Transfer-Encoding': value})[0], 400)
        self.provider.assert_not_called()
        self.assertEqual(self.app.store.health()['image_count'], 0)

    def test_active_external_or_oversized_registered_svg_is_denied_for_get_and_head(self):
        bad = [
            '<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
            '<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"><rect width="10" height="10"/></svg>',
            '<svg xmlns="http://www.w3.org/2000/svg"><image href="https://example.invalid/a.png"/></svg>',
            '<svg xmlns="http://www.w3.org/2000/svg"><rect style="fill:url(https://example.invalid/a)"/></svg>',
            '<!DOCTYPE svg [<!ENTITY x "fixture">]><svg xmlns="http://www.w3.org/2000/svg">&x;</svg>',
            '<svg xmlns="http://www.w3.org/2000/svg">' + ' ' * 300000 + '</svg>',
        ]
        target = self.root / 'thumbnails' / 'color' / 'red.svg'
        for source in bad:
            target.write_text(source)
            for method in ['GET', 'HEAD']:
                with self.subTest(source=source[:70], method=method):
                    self.assertEqual(self.request(method, '/thumbnails/color/red.svg')[0], 404)

    def test_inert_svg_serves_with_restrictive_policy_and_entire_catalog_is_valid(self):
        self.assertEqual(self.request('GET', '/thumbnails/color/red.svg')[0], 200)
        for method in ['GET', 'HEAD']:
            headers = self.request(method, '/thumbnails/color/red.svg')[2]
            self.assertIn("default-src 'none'", headers.get('Content-Security-Policy', ''))
            self.assertIn('sandbox', headers['Content-Security-Policy'])
        catalog = server.Catalog.load(server.ROOT / 'library.json')
        for url in catalog.thumbnail_paths:
            self.assertTrue(server.safe_svg((server.ROOT / url.lstrip('/')).read_bytes()), url)


if __name__ == '__main__':
    unittest.main()
