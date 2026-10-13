import base64
import copy
import hashlib
import http.client
import io
import json
import os
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlencode

from PIL import Image

import server
from gallery import SAFE_PROVIDER_ERROR, save_image
from test_gallery import image_bytes


LIBRARY = {'base_locks': 'Authoritative realism', 'always_on': 'opaque fabric', 'categories': [
    {'id': 'test', 'name': 'Test', 'attributes': [
        {'id': 'color', 'name': 'Color', 'type': 'exclusive', 'thumbnail': '/thumbnails/color/_attribute.svg', 'values': [
            {'id': 'red', 'name': 'Red', 'steers': 'red garment', 'thumbnail': '/thumbnails/color/red.svg'},
            {'id': 'blue', 'name': 'Blue', 'steers': 'blue garment'},
            {'id': 'green', 'name': 'Green', 'steers': 'green garment'}]},
        {'id': 'lock', 'name': 'Lock', 'type': 'boolean', 'values': [
            {'id': 'on', 'name': 'On', 'steers': 'natural pores'},
            {'id': 'off', 'name': 'Off', 'steers': 'soft skin'}]},
        {'id': 'pose', 'name': 'Pose', 'type': 'multi', 'values': [
            {'id': 'a', 'name': 'A', 'steers': 'standing'},
            {'id': 'b', 'name': 'B', 'steers': 'smiling'},
            {'id': 'c', 'name': 'C', 'steers': 'leaning'}]}
    ]}]}


def wait_job(store, job_id, timeout=8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = store.job(job_id)
        if result['status'] in {'completed', 'partial', 'failed'}:
            return result
        time.sleep(.01)
    raise AssertionError('job did not finish')


class PlannerTests(unittest.TestCase):
    def setUp(self):
        self.catalog = server.Catalog(LIBRARY)

    def test_authoritative_prompts_locked_multis_and_boolean_off(self):
        result = self.catalog.preview({'selections': {'color': ['red'], 'lock': ['off'], 'pose': ['b', 'a']}, 'extra_prompt': 'garden'})
        self.assertEqual(result['combination_count'], 1)
        plan = result['plans'][0]
        self.assertEqual(plan['selections'], {'color': ['red'], 'lock': ['off'], 'pose': ['a', 'b']})
        from prompt_policy import ADULT_AESTHETIC_DIRECTION
        self.assertEqual(plan['prompt'], 'Authoritative realism. red garment. soft skin. standing. smiling. opaque fabric. garden. ' + ADULT_AESTHETIC_DIRECTION)

    def test_seeded_distinct_variations_honor_locks_and_whitelist_subsets(self):
        payload = {'mode': 'variations', 'n': 12, 'seed': 42, 'selections': {'lock': ['on']},
                   'whitelist': {'color': ['red', 'blue'], 'pose': ['a', 'b', 'c']}}
        result = self.catalog.preview(payload)
        self.assertEqual(result['combination_count'], 12)
        self.assertEqual(result, self.catalog.preview(payload))
        self.assertEqual(len({json.dumps(p['selections'], sort_keys=True) for p in result['plans']}), 12)
        for plan in result['plans']:
            self.assertEqual(plan['selections']['lock'], ['on'])
            self.assertEqual(len(plan['selections']['color']), 1)
            self.assertIn(plan['selections']['color'][0], ['red', 'blue'])
            self.assertTrue(1 <= len(plan['selections']['pose']) <= 2)
        self.assertNotEqual(result, self.catalog.preview(dict(payload, seed=43)))

    def test_impossible_variations_repeat_and_single_are_distinct(self):
        with self.assertRaisesRegex(ValueError, 'distinct.*combinations'):
            self.catalog.preview({'mode': 'variations', 'n': 2})
        result = self.catalog.preview({'mode': 'repeat', 'n': 24, 'selections': {'color': ['red']}})
        self.assertEqual(result['combination_count'], 1)
        self.assertEqual(len(result['plans']), 24)
        self.assertTrue(all(plan['selections'] == result['plans'][0]['selections'] for plan in result['plans']))
        self.assertEqual([p['plan_index'] for p in result['plans']], list(range(24)))
        with self.assertRaisesRegex(ValueError, 'single mode'):
            self.catalog.preview({'n': 2})

    def test_rejects_invalid_ids_cardinality_types_overlap_and_counts(self):
        bad = [None, [], {'prompt': 'client authority'}, {'mode': []}, {'mode': 'unknown'},
               {'selections': []}, {'whitelist': []}, {'selections': {'unknown': ['red']}},
               {'selections': {'color': ['on']}}, {'selections': {'color': 'red'}},
               {'selections': {'color': [True]}}, {'selections': {'color': ['red', 'blue']}},
               {'selections': {'lock': ['on', 'off']}}, {'selections': {'lock': [False]}},
               {'selections': {'pose': ['a', 'a']}}, {'whitelist': {'pose': []}, 'mode': 'variations'},
               {'selections': {'color': []}, 'whitelist': {'color': ['red']}, 'mode': 'variations'},
               {'whitelist': {'color': ['red']}}, {'aspect_ratio': []}, {'aspect_ratio': '8:3'},
               {'extra_prompt': True}, {'extra_prompt': 'x' * 10001}, {'seed': True}, {'seed': '1'},
               {'seed': 2**63}, *[{'n': n} for n in [0, 25, True, 1.5, '2']]]
        for payload in bad:
            with self.subTest(payload=str(payload)[:100]):
                with self.assertRaises(ValueError):
                    self.catalog.preview(payload)

    def test_boolean_whitelist_chooses_exactly_one_and_library_metadata_present(self):
        result = self.catalog.preview({'mode': 'variations', 'n': 2, 'whitelist': {'lock': ['on', 'off']}})
        self.assertEqual({tuple(p['selections']['lock']) for p in result['plans']}, {('on',), ('off',)})
        with self.assertRaisesRegex(ValueError, '6 distinct compatible'):
            self.catalog.preview({'mode': 'variations', 'n': 7, 'whitelist': {
                'color': ['red', 'blue', 'green'], 'lock': ['on', 'off']}})
        for category in self.catalog.library['categories']:
            for attribute in category['attributes']:
                self.assertIn('description', attribute)
                self.assertIn('thumbnail_url', attribute)
                for value in attribute['values']:
                    self.assertIn('description', value)
                    self.assertIn('thumbnail_url', value)

    def test_huge_combination_space_is_sampled_without_materializing_product(self):
        catalog = server.Catalog.load(server.ROOT / 'library.json')
        whitelist = {aid: [v['id'] for v in attribute['values']] for aid, attribute in catalog.attributes.items()}
        result = catalog.preview({'whitelist': whitelist, 'mode': 'variations', 'n': 24, 'seed': 2})
        self.assertGreater(result['combination_count_metadata']['unrestricted_product_count'], 2**63)
        self.assertFalse(result['combination_count_exact'])
        self.assertEqual(result['combination_count_metadata']['method'], 'bounded_search_lower_bound')
        self.assertLessEqual(result['combination_count_metadata']['visited_nodes'], server.PLANNER_NODE_LIMIT)
        self.assertEqual(len(result['plans']), 24)
        self.assertEqual(len({json.dumps(p['selections'], sort_keys=True) for p in result['plans']}), 24)
        self.assertTrue(all(catalog.conflict(p['selections']) is None for p in result['plans']))

    def test_actual_cross_attribute_locks_and_100_seeded_safe_plans(self):
        catalog = server.Catalog.load(server.ROOT / 'library.json')
        self.assertEqual(catalog.library_hash, hashlib.sha256((server.ROOT / 'library.json').read_bytes()).hexdigest())
        for length in ['shaved', 'buzz_cut']:
            for aid, vid in [('hair_style', 'low_bun'), ('hair_style', 'high_ponytail'),
                             ('hair_style', 'twin_braids'), ('hair_fringe', 'wispy_fringe')]:
                with self.assertRaisesRegex(ValueError, f'hair_length:{length}'):
                    catalog.preview({'selections': {'hair_length': [length], aid: [vid]}})
        payload = {'mode': 'variations', 'n': 2, 'selections': {'micro_texture': ['on']},
                   'whitelist': {'hair_length': ['shaved', 'buzz_cut', 'waist_length'],
                                 'hair_style': ['low_bun', 'low_ponytail', 'twin_braids', 'soft_waves'],
                                 'hair_fringe': ['open_forehead', 'wispy_fringe']}}
        for seed in range(100):
            result = catalog.preview(dict(payload, seed=seed))
            self.assertEqual(result['combination_count'], 10)
            self.assertTrue(result['combination_count_exact'])
            for plan in result['plans']:
                self.assertIsNone(catalog.conflict(plan['selections']))
                self.assertEqual(plan['selections']['micro_texture'], ['on'])
                for aid, ids in payload['whitelist'].items():
                    self.assertTrue(set(plan['selections'][aid]) <= set(ids))
        with self.assertRaisesRegex(ValueError, '10 distinct compatible'):
            catalog.preview(dict(payload, n=11))
        locked = catalog.preview({'mode': 'variations', 'n': 1, 'selections': {'hair_length': ['shaved']},
                                  'whitelist': {'hair_style': ['low_bun', 'soft_waves']}})
        self.assertEqual(locked['combination_count'], 1)
        self.assertEqual(locked['plans'][0]['selections']['hair_style'], ['soft_waves'])

    def test_optional_excludes_exact_counts_multi_conflicts_and_bounded_exhaustion(self):
        library = copy.deepcopy(LIBRARY)
        attrs = library['categories'][0]['attributes']
        attrs[0]['values'][0]['excludes'] = ['pose:a']
        attrs[2]['values'][0]['excludes'] = ['pose:b']
        catalog = server.Catalog(library)
        result = catalog.preview({'mode': 'variations', 'n': 12, 'seed': 3,
                                  'whitelist': {'color': ['red', 'blue', 'green'], 'pose': ['a', 'b', 'c']}})
        self.assertEqual(result['combination_count'], 13)
        self.assertTrue(all(catalog.conflict(p['selections']) is None for p in result['plans']))
        with self.assertRaisesRegex(ValueError, 'color:red.*pose:a'):
            catalog.preview({'selections': {'color': ['red'], 'pose': ['a']}})
        with patch.object(server, 'EXACT_PRODUCT_LIMIT', 1), patch.object(server, 'PLANNER_NODE_LIMIT', 1):
            with self.assertRaisesRegex(ValueError, 'bounded planner'):
                catalog.preview({'mode': 'variations', 'whitelist': {'color': ['red', 'blue']}})
        attrs[0]['values'][0]['excludes'] = ['missing:unknown']
        with self.assertRaisesRegex(ValueError, 'excludes reference'):
            server.Catalog(library)

    def test_actual_library_every_attribute_and_value_can_be_planned(self):
        catalog = server.Catalog.load(server.ROOT / 'library.json')
        for aid, attribute in catalog.attributes.items():
            for value in attribute['values']:
                plan = catalog.preview({'selections': {aid: [value['id']]}})['plans'][0]
                self.assertEqual(plan['selections'][aid], [value['id']])
                if value['steers']:
                    self.assertIn(value['steers'].rstrip('.'), plan['prompt'])
                self.assertEqual(catalog.validate_map({aid: [value['id']]}, 'filters'), {aid: [value['id']]})


class NativeGenerationTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR', '/tmp'))
        self.output_dir = Path(self.tempdir.name)

    def tearDown(self):
        self.tempdir.cleanup()

    def test_native_url_branch_with_mock_credentials_and_verified_pixels(self):
        # Stub imported modules so neither Hermes config nor credentials are read.
        resolver = unittest.mock.Mock(return_value={'api_key': 'MOCK_ONLY', 'base_url': 'https://mock.invalid/v1'})
        requests = unittest.mock.Mock()
        requests.post.return_value.json.return_value = {'data': [{'url': 'https://mock.invalid/image'}]}
        requests.get.return_value.content = base64.b64decode(image_bytes())
        requests.get.return_value.headers = {'Content-Type': 'image/jpeg'}
        modules = {'requests': requests,
                   'hermes_cli.config': SimpleNamespace(load_config=unittest.mock.Mock(return_value={})),
                   'tools.xai_http': SimpleNamespace(resolve_xai_http_credentials=resolver,
                                                    hermes_xai_user_agent=lambda: 'mock-agent')}
        with patch.dict('sys.modules', modules):
            result = server.generate_batch({'prompt': 'URL regression'}, self.output_dir)
            resolver.assert_called_once_with()
            requests.get.assert_called_once_with('https://mock.invalid/image', timeout=60)
            self.assertNotIn('seed', requests.post.call_args.kwargs['json'])
            with Image.open(self.output_dir / result['data'][0]['url'].split('/')[-1]) as image:
                self.assertEqual(image.size, (90, 160))
                image.verify()
            requests.get.return_value.content = b'fake-image-bytes'
            with self.assertRaises(RuntimeError):
                server.generate_batch({'prompt': 'invalid URL output'}, self.output_dir)

    def test_generate_batch_saves_only_verified_images_and_passes_ratio(self):
        with patch.object(server, 'generate_native_image', return_value=(image_bytes(), 'image/jpeg')) as generate:
            body = server.generate_batch({'prompt': 'garden portrait', 'n': 2}, self.output_dir)
        self.assertEqual(len(body['data']), 2)
        self.assertEqual(generate.call_count, 2)
        generate.assert_called_with('garden portrait', '9:16')
        self.assertEqual(len(list(self.output_dir.glob('*-thumb.jpg'))), 2)
        for record in body['data']:
            self.assertTrue(record['url'].startswith('/generated/'))
            with Image.open(self.output_dir / record['url'].split('/')[-1]) as image:
                self.assertEqual(image.size, (90, 160))
                image.verify()

    def test_legacy_partial_success_preserves_valid_images_and_sanitizes_errors(self):
        with patch.object(server, 'generate_native_image', side_effect=[(image_bytes(), 'image/png'), RuntimeError('secret bearer TOKEN')]):
            result = server.generate_batch({'prompt': 'portrait', 'n': 2}, self.output_dir)
        self.assertEqual(len(result['data']), 1)
        self.assertEqual(result['errors'], [{'index': 1, 'error': SAFE_PROVIDER_ERROR}])

    def test_unverified_provider_bytes_wrong_aspect_and_invalid_request_rejected(self):
        for encoded in [base64.b64encode(b'fake bytes').decode(), image_bytes((160, 90))]:
            with patch.object(server, 'generate_native_image', return_value=(encoded, 'image/png')):
                with self.assertRaises(RuntimeError):
                    server.generate_batch({'prompt': 'portrait'}, self.output_dir)
        self.assertEqual(list(self.output_dir.iterdir()), [])
        for payload in [{'prompt': ' '}, {'prompt': True}, {'prompt': 'portrait', 'n': 5}, {'prompt': 'portrait', 'n': True}]:
            with self.assertRaises(ValueError):
                server.generate_batch(payload, self.output_dir)


class MemorySocket:
    """Raw HTTP transport adapter: run the real parser without opening sockets."""
    def __init__(self, data):
        self.incoming = io.BytesIO(data)
        self.outgoing = io.BytesIO()

    def makefile(self, mode, *args):
        return self.incoming

    def sendall(self, data):
        self.outgoing.write(data)

    def settimeout(self, timeout):
        pass


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR', '/tmp'))
        self.root = Path(self.tmp.name)
        (self.root / 'dist' / 'assets').mkdir(parents=True)
        (self.root / 'dist' / 'index.html').write_text('<html>compiled app</html>')
        (self.root / 'dist' / 'assets' / 'app.js').write_text('console.log("app")')
        (self.root / 'dist' / 'assets' / 'debug.py').write_text('secret source')
        (self.root / 'server.py').write_text('private source')
        (self.root / 'thumbnails' / 'color').mkdir(parents=True)
        for filename in ['_attribute.svg', 'red.svg', 'unregistered.svg']:
            (self.root / 'thumbnails' / 'color' / filename).write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
        (self.root / '.git').mkdir()
        (self.root / '.git' / 'config').write_text('private git')
        self.provider = unittest.mock.Mock(return_value=(image_bytes(), 'image/jpeg'))
        self.app = server.Application(self.root, catalog=server.Catalog(LIBRARY), provider=self.provider)
        self.port = 8123
        self.httpd = SimpleNamespace(app=self.app, server_port=self.port)

    def tearDown(self):
        self.app.close()
        self.tmp.cleanup()

    def request(self, method, path, payload=None, headers=None, raw=None):
        body = raw if raw is not None else json.dumps(payload).encode() if payload is not None else b''
        request_headers = {'Host': f'127.0.0.1:{self.port}', 'Content-Type': 'application/json', **(headers or {})}
        if body and 'Content-Length' not in request_headers:
            request_headers['Content-Length'] = str(len(body))
        wire = f'{method} {path} HTTP/1.1\r\n'
        wire += ''.join(f'{key}: {value}\r\n' for key, value in request_headers.items())
        transport = MemorySocket(wire.encode('ascii') + b'\r\n' + body)
        server.AppHandler(transport, ('127.0.0.1', 12345), self.httpd)
        response = http.client.HTTPResponse(MemorySocket(transport.outgoing.getvalue()), method=method)
        response.begin()
        data = response.read()
        status, response_headers = response.status, dict(response.getheaders())
        response.close()
        if response_headers.get('Content-Type', '').startswith('application/json') and method != 'HEAD':
            data = json.loads(data)
        return status, data, response_headers

    def test_full_preview_job_gallery_details_and_image_asset_flow(self):
        payload = {'mode': 'variations', 'n': 2, 'seed': 2, 'selections': {'lock': ['on']},
                   'whitelist': {'color': ['red', 'blue']}, 'extra_prompt': 'garden'}
        status, preview, _ = self.request('POST', '/api/preview', payload)
        self.assertEqual(status, 200)
        self.provider.assert_not_called()
        status, created, _ = self.request('POST', '/api/jobs', payload)
        self.assertEqual(status, 202)
        job = wait_job(self.app.store, created['id'])
        status, job_http, _ = self.request('GET', '/api/jobs/' + created['id'])
        self.assertEqual(status, 200)
        self.assertEqual(job_http, job)
        self.assertEqual((job['status'], job['total'], job['completed'], job['failed']), ('completed', 2, 2, 0))
        _, health, _ = self.request('GET', '/api/health')
        self.assertEqual((health['image_count'], health['pending_images'], health['job_counts']['completed']), (2, 0, 1))
        self.assertEqual({r['prompt'] for r in job['results']}, {p['prompt'] for p in preview['plans']})
        for record, plan in zip(job['results'], preview['plans']):
            for key in ('library_hash', 'plan_index', 'selection_sampling_seed',
                        'requested_selection_snapshot', 'resolved_selection_snapshot'):
                self.assertEqual(record[key], plan[key])
        query = urlencode({'q': 'garden', 'filters': json.dumps({'color': ['red', 'blue'], 'lock': ['on']}), 'aspect_ratio': '9:16', 'page_size': 1})
        status, gallery, _ = self.request('GET', '/api/gallery?' + query)
        self.assertEqual(status, 200)
        self.assertEqual((gallery['total'], gallery['pages'], len(gallery['items'])), (2, 2, 1))
        record = gallery['items'][0]
        self.assertEqual(self.request('GET', '/api/images/' + record['id'])[:2], (200, record))
        for url in [record['url'], record['thumbnail_url']]:
            status, raw, _ = self.request('GET', url)
            self.assertEqual(status, 200)
            with Image.open(io.BytesIO(raw)) as image:
                image.verify()
        self.assertEqual(self.request('GET', '/api/library')[:2], (200, self.app.catalog.library))

    def test_health_counts_without_prompts_paths_credentials_or_provider_reads(self):
        status, body, _ = self.request('GET', '/api/health')
        self.assertEqual(status, 200)
        self.assertEqual(body['status'], 'ok')
        self.assertEqual(body['pending_images'], 0)
        job = self.app.store.create_job([{'prompt': 'PRIVATE_PROMPT', 'selections': {}}], '9:16')
        self.assertEqual(self.request('GET', '/api/health')[1]['job_counts']['queued'], 1)
        self.app.store.claim(job, 0)
        self.assertEqual(self.request('GET', '/api/health')[1]['pending_images'], 1)
        self.app.store.complete_plan(job, 0, error='PRIVATE_ERROR')
        _, body, _ = self.request('GET', '/api/health')
        self.assertEqual(body['job_counts']['failed'], 1)
        self.assertEqual(body['pending_limit'], 24)
        self.assertNotIn('PRIVATE', json.dumps(body))
        self.assertNotIn(str(self.root), json.dumps(body))
        self.provider.assert_not_called()
        self.assertEqual(self.request('HEAD', '/api/health')[0], 200)

    def test_actual_hair_conflicts_return_specific_400_before_provider(self):
        self.app.catalog = server.Catalog.load(server.ROOT / 'library.json')
        for route in ('/api/preview', '/api/jobs'):
            status, body, _ = self.request('POST', route, {'selections': {
                'hair_length': ['buzz_cut'], 'hair_style': ['high_bun']}})
            self.assertEqual(status, 400)
            self.assertIn('hair_length:buzz_cut', body['error'])
            self.assertIn('hair_style:high_bun', body['error'])
        self.provider.assert_not_called()

    def test_partial_and_failed_jobs_never_claim_invalid_bytes_successful(self):
        self.provider.side_effect = [(image_bytes(), 'wrong/mime'), RuntimeError('Authorization: secret'), (image_bytes((160, 90)), 'image/png')]
        status, body, _ = self.request('POST', '/api/jobs', {'mode': 'repeat', 'n': 3})
        self.assertEqual(status, 202)
        job = wait_job(self.app.store, body['id'])
        self.assertEqual((job['status'], job['completed'], job['failed']), ('partial', 1, 2))
        self.assertEqual(len(job['results']), 1)
        self.assertNotIn('secret', json.dumps(job))
        self.assertEqual(self.app.store.query()['total'], 1)
        self.provider.side_effect = RuntimeError('secret')
        _, body, _ = self.request('POST', '/api/jobs', {})
        self.assertEqual(wait_job(self.app.store, body['id'])['status'], 'failed')

    def test_legacy_compatibility_persists_empty_tags_and_sanitizes_failure(self):
        status, body, _ = self.request('POST', '/api/generate', {'prompt': 'legacy garden', 'n': 2})
        self.assertEqual(status, 200)
        self.assertEqual(len(body['data']), 2)
        self.assertTrue(all(item['selections'] == {} for item in body['data']))
        self.assertTrue(all(item['library_hash'] == self.app.catalog.library_hash for item in body['data']))
        self.assertTrue(all(item['selection_sampling_seed'] is None for item in body['data']))
        self.assertEqual([item['plan_index'] for item in body['data']], [0, 1])
        self.assertEqual(self.app.store.query()['total'], 2)
        self.provider.side_effect = RuntimeError('secret token')
        status, body, _ = self.request('POST', '/api/generate', {'prompt': 'portrait'})
        self.assertEqual((status, body), (502, {'error': SAFE_PROVIDER_ERROR}))
        self.assertEqual(self.request('POST', '/api/generate', {'prompt': 'portrait', 'n': 5})[0], 400)

    def test_explicit_assets_only_for_get_and_head(self):
        for path in ['/', '/index.html', '/assets/app.js', '/thumbnails/color/_attribute.svg', '/thumbnails/color/red.svg']:
            self.assertEqual(self.request('GET', path)[0], 200)
        denied = ['/server.py', '/gallery.py', '/library.json', '/gallery.sqlite3', '/.git/config', '/generated/', '/assets/', '/assets/debug.py',
                  '/thumbnails/', '/thumbnails/color/unregistered.svg', '/thumbnails/../server.py', '/assets/../index.html', '/assets/%2e%2e/%2e%2e/server.py', '/assets/.hidden.js', '/generated/../server.py']
        for path in denied:
            for method in ['GET', 'HEAD']:
                with self.subTest(path=path, method=method):
                    self.assertEqual(self.request(method, path)[0], 404)
        (self.root / 'dist' / 'assets' / 'escape.js').symlink_to(self.root / 'server.py')
        self.assertEqual(self.request('GET', '/assets/escape.js')[0], 404)
        self.assertEqual(self.request('GET', '/api/jobs/' + '0' * 32)[0], 404)
        self.assertEqual(self.request('GET', '/api/images/nope')[0], 404)

    def test_csrf_host_origin_and_cross_site_reject_paid_requests_before_provider(self):
        for path in ['/api/jobs', '/api/generate']:
            for headers in [{'Host': f'evil.example:{self.port}'}, {'Host': '127.0.0.1:1'},
                            {'Origin': 'https://evil.example'}, {'Origin': 'null'},
                            {'Origin': f'http://localhost:{self.port}'}, {'Sec-Fetch-Site': 'cross-site'}]:
                with self.subTest(headers=headers, path=path):
                    self.assertEqual(self.request('POST', path, {}, headers)[0], 403)
        self.provider.assert_not_called()
        self.assertEqual(self.request('POST', '/api/jobs', {}, {'Origin': f'http://127.0.0.1:{self.port}'})[0], 202)
        with self.assertRaises(ValueError):
            server.create_server(self.app, '0.0.0.0', 0)

    def test_malformed_json_body_cap_types_and_query_validation(self):
        for raw in [b'{', b'[]', b'null', b'\xff', b'{"n":1,"n":2}', b'{"seed":NaN}']:
            with self.subTest(raw=raw):
                self.assertEqual(self.request('POST', '/api/jobs', raw=raw)[0], 400)
        self.assertEqual(self.request('POST', '/api/jobs', raw=b'{}', headers={'Content-Length': '200001'})[0], 413)
        self.assertEqual(self.request('POST', '/api/jobs', raw=b'{}', headers={'Content-Length': '-2'})[0], 400)
        self.assertEqual(self.request('POST', '/api/jobs', raw=b'{}', headers={'Content-Type': 'text/plain'})[0], 415)
        self.assertEqual(self.request('POST', '/api/jobs', raw=b'{}', headers={'Transfer-Encoding': 'chunked'})[0], 400)
        for query in ['page=0', 'page_size=101', 'page=1.2', 'page=1&page=2', 'filters=[]', 'filters=%7B', 'aspect_ratio=8:3', 'q=' + 'x' * 501,
                      urlencode({'filters': json.dumps({'color': ['on']})}), urlencode({'filters': json.dumps({'lock': [True]})})]:
            with self.subTest(query=query):
                self.assertEqual(self.request('GET', '/api/gallery?' + query)[0], 400)
        self.provider.assert_not_called()

    def test_queue_limit_applies_to_async_and_legacy_and_max_four_active_calls(self):
        release = threading.Event()
        entered = threading.Event()
        mutex = threading.Lock()
        counters = {'active': 0, 'max': 0, 'calls': 0}

        def provider(prompt, aspect):
            with mutex:
                counters['active'] += 1
                counters['calls'] += 1
                counters['max'] = max(counters['max'], counters['active'])
                if counters['active'] == 4:
                    entered.set()
            try:
                release.wait(8)
                return image_bytes(), 'image/png'
            finally:
                with mutex:
                    counters['active'] -= 1
        self.app.jobs.provider = provider
        self.app.provider = provider
        try:
            status, body, _ = self.request('POST', '/api/jobs', {'mode': 'repeat', 'n': 24})
            self.assertEqual(status, 202)
            self.assertTrue(entered.wait(3))
            self.assertEqual(self.request('POST', '/api/jobs', {})[0], 429)
            self.assertEqual(self.request('POST', '/api/generate', {'prompt': 'portrait'})[0], 429)
            self.assertEqual(counters['max'], 4)
        finally:
            release.set()
        job = wait_job(self.app.store, body['id'])
        self.assertEqual(job['completed'], 24)
        self.assertEqual(counters['max'], 4)
        self.assertEqual(counters['calls'], 24)


class GlobalConcurrencyTests(unittest.TestCase):
    def test_recovery_fails_interrupted_paid_work_without_provider_retry(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR', '/tmp')) as tmp:
            app = server.Application(Path(tmp), catalog=server.Catalog(LIBRARY), provider=unittest.mock.Mock())
            plan = app.catalog.preview({'seed': 7})['plans'][0]
            job = app.store.create_job([plan, plan], '9:16')
            app.store.claim(job, 0)
            app.store.complete_plan(job, 0, save_image(image_bytes(), app.store.output_dir, '9:16'))
            app.store.claim(job, 1)
            app.close()
            provider = unittest.mock.Mock()
            restarted = server.Application(Path(tmp), catalog=server.Catalog(LIBRARY), provider=provider)
            try:
                result = restarted.store.job(job)
                self.assertEqual((result['status'], result['completed'], result['failed']), ('partial', 1, 1))
                self.assertEqual(result['results'][0]['selection_sampling_seed'], 7)
                provider.assert_not_called()
            finally:
                restarted.close()

    def test_native_calls_share_global_four_call_limit_across_managers_and_legacy(self):
        release, four = threading.Event(), threading.Event()
        mutex = threading.Lock()
        active, maximum = 0, 0

        def provider(prompt, aspect):
            nonlocal active, maximum
            with mutex:
                active += 1
                maximum = max(maximum, active)
                if active == 4:
                    four.set()
            try:
                release.wait(5)
                return image_bytes(), 'image/png'
            finally:
                with mutex:
                    active -= 1

        with tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR', '/tmp')) as tmp:
            root = Path(tmp)
            apps = [server.Application(root / str(i), catalog=server.Catalog(LIBRARY), provider=provider) for i in range(2)]
            pool = ThreadPoolExecutor(max_workers=2)
            try:
                plan = {'prompt': 'portrait', 'selections': {}}
                ids = [app.jobs.submit([plan] * 4, '9:16') for app in apps]
                futures = [pool.submit(server.generate_batch, {'prompt': 'legacy'}, root / f'legacy{i}', None, provider) for i in range(2)]
                self.assertTrue(four.wait(3))
                time.sleep(.05)
                self.assertEqual(maximum, 4)
                release.set()
                for app, jid in zip(apps, ids):
                    self.assertEqual(wait_job(app.store, jid)['completed'], 4)
                for future in futures:
                    self.assertEqual(len(future.result()['data']), 1)
                self.assertEqual(maximum, 4)
            finally:
                release.set()
                pool.shutdown()
                for app in apps:
                    app.close()


if __name__ == '__main__':
    unittest.main()
