"""Socket-free v2 backend contract tests. All provider traffic is mocked."""
import base64
import copy
import io
import json
import shutil
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from types import ModuleType
from unittest.mock import Mock, patch

from PIL import Image

import server
import test_server as legacy_tests
from test_server import LIBRARY
from test_gallery import image_bytes
from gallery import Gallery, save_image


class V2PlannerTests(unittest.TestCase):
    def rules(self):
        library = copy.deepcopy(LIBRARY)
        library['catalog_version'] = 2
        library['categories'][0]['attributes'][2]['type'] = 'exclusive'
        library['compatibility_rules'] = [{'when': {'color': ['red']}, 'requires': {'pose': ['a']},
                                         'message': 'Red requires standing pose.'}]
        return library

    def test_required_components_are_checked_at_complete_plans_not_search_prefix(self):
        library = self.rules()
        catalog = server.Catalog(library, bundle={'library': library})
        result = catalog.preview({'mode': 'variations', 'n': 3, 'seed': 1,
                                  'whitelist': {'color': ['red', 'blue'], 'pose': ['a', 'b']}})
        self.assertEqual(result['combination_count'], 3)
        self.assertTrue(all(not (p['selections']['color'] == ['red'] and p['selections']['pose'] == ['b']) for p in result['plans']))
        locked = catalog.preview({'mode': 'variations', 'n': 1, 'selections': {'color': ['red']}, 'whitelist': {'pose': ['a', 'b']}})
        self.assertEqual(locked['plans'][0]['selections']['pose'], ['a'])

    def test_recipe_components_reach_authoritative_prompt_and_gallery_snapshot(self):
        library = self.rules()
        library['categories'][0]['attributes'].append({'id': 'recipe', 'name': 'Recipe', 'type': 'exclusive', 'values': [
            {'id': 'red_standing', 'name': 'Red standing', 'steers': 'coordinated editorial recipe',
             'recipe': {'selections': {'color': ['red'], 'pose': ['a']}}}]})
        catalog = server.Catalog(library, bundle={'library': library})
        plan = catalog.preview({'selections': {'recipe': ['red_standing']}})['plans'][0]
        self.assertEqual(plan['selections']['color'], ['red'])
        self.assertIn('red garment', plan['prompt'])
        self.assertEqual(plan['resolved_selection_snapshot']['pose']['values'][0]['id'], 'a')
        with self.assertRaisesRegex(ValueError, 'recipe.*conflicts'):
            catalog.preview({'selections': {'recipe': ['red_standing'], 'color': ['blue']}})

    def test_recipe_completes_explicit_subset_of_multi_components(self):
        library = copy.deepcopy(LIBRARY)
        attrs = library['categories'][0]['attributes']
        attrs.append({'id': 'recipe', 'name': 'Recipe', 'type': 'exclusive', 'values': [
            {'id': 'both', 'name': 'Both', 'steers': 'coordinated pose recipe', 'recipe': {'selections': {'pose': ['a', 'b']}}}]})
        catalog = server.Catalog(library, bundle={'library': library})
        plan = catalog.preview({'selections': {'recipe': ['both'], 'pose': ['a']}})['plans'][0]
        self.assertEqual(plan['selections']['pose'], ['a', 'b'])
        self.assertIn('smiling', plan['prompt'])

    def test_gender_default_is_server_authority_and_explicit_selection_wins(self):
        library = copy.deepcopy(LIBRARY)
        library['catalog_version'] = 2
        library['categories'][0]['attributes'].append({
            'id': 'gender', 'name': 'Gender', 'type': 'exclusive', 'default': 'woman',
            'control': 'select', 'preview_method': 'control_only', 'values': [
                {'id': 'woman', 'name': 'Woman', 'steers': 'adult woman'},
                {'id': 'man', 'name': 'Man', 'steers': 'adult man'}]})
        catalog = server.Catalog(library)
        plan = catalog.preview({})['plans'][0]
        self.assertEqual(plan['selections']['gender'], ['woman'])
        self.assertIn('adult woman', plan['prompt'])
        self.assertEqual(catalog.preview({'selections': {'gender': ['man']}})['plans'][0]['selections']['gender'], ['man'])

    def test_numeric_age_is_discrete_canonical_id_not_untrusted_prompt(self):
        library = copy.deepcopy(LIBRARY)
        library['categories'][0]['attributes'].append({
            'id': 'age', 'name': 'Age', 'type': 'exclusive', 'control': 'range',
            'range': {'min': 21, 'max': 85, 'step': 1}, 'values': [
                {'id': f'age_{n}', 'name': str(n), 'steers': f'adult aged {n} years'} for n in range(21, 86)]})
        catalog = server.Catalog(library)
        self.assertIn('adult aged 85 years', catalog.preview({'selections': {'age': ['age_85']}})['plans'][0]['prompt'])
        for invalid in ('85', 'age_20', 'age_86', 85):
            with self.assertRaises(ValueError):
                catalog.preview({'selections': {'age': [invalid]}})


class V2HTTPTests(legacy_tests.HTTPTests):
    # Inherit the established HTTP parser/fixture, not duplicate its existing tests.
    def test_catalog_versions_legacy_fixture_no_catalog_required(self):
        status, result, _ = self.request('GET', '/api/catalog/versions')
        self.assertEqual(status, 200)
        self.assertEqual(result['active_version'], 1)
        self.assertEqual(result['effective_counts']['attributes'], 3)
        self.provider.assert_not_called()

    def test_resolve_preserves_raw_draft_requires_origin_and_never_calls_provider(self):
        draft = {'selections': {'unknown_old': ['raw']}, 'note': 'keep', 'future': {'a': 2}}
        self.assertEqual(self.request('POST', '/api/catalog/resolve', {'draft': draft})[0], 403)
        status, result, _ = self.request('POST', '/api/catalog/resolve', {'draft': draft},
                                       headers={'Origin': 'http://127.0.0.1:8123'})
        self.assertEqual(status, 200)
        self.assertEqual(result['draft'], draft)
        self.assertTrue(result['unresolved'])
        self.provider.assert_not_called()


class NativeEditTests(unittest.TestCase):
    def modules(self, response):
        requests = Mock()
        requests.post.return_value.json.return_value = response
        requests.post.return_value.iter_content.return_value = [json.dumps(response).encode()]
        config = ModuleType('hermes_cli.config')
        config.load_config = Mock(return_value={'image_gen': {'xai': {}}})
        xai = ModuleType('tools.xai_http')
        xai.resolve_xai_http_credentials = Mock(return_value={'api_key': 'private-token', 'base_url': 'https://mock.invalid/v1'})
        xai.hermes_xai_user_agent = Mock(return_value='Hermes-test')
        return requests, {'requests': requests, 'hermes_cli.config': config, 'tools.xai_http': xai}

    def test_json_edit_uses_owned_data_uri_explicit_model_and_validates_pixels(self):
        raw = base64.b64decode(image_bytes())
        requests, modules = self.modules({'data': [{'b64_json': image_bytes()}]})
        with patch.dict(sys.modules, modules):
            encoded, mime = server.edit_native_image('change hair only', raw, 'image/png', '9:16')
        call = requests.post.call_args
        self.assertTrue(call.args[0].endswith('/images/edits'))
        self.assertEqual(call.kwargs['json']['model'], 'grok-imagine-image-2.0')
        self.assertEqual(call.kwargs['json']['image']['url'], 'data:image/png;base64,' + base64.b64encode(raw).decode())
        self.assertEqual(call.kwargs['headers']['User-Agent'], 'Hermes-test')
        self.assertNotIn('files', call.kwargs)
        with Image.open(io.BytesIO(base64.b64decode(encoded))) as result:
            self.assertEqual(result.size, (90, 160))

    def test_bad_output_wrong_ratio_and_request_errors_are_sanitized(self):
        for response in ({'data': [{'b64_json': 'not-an-image'}]},
                         {'data': [{'b64_json': image_bytes((160, 90))}]},
                         {'data': [{'url': 'https://untrusted.invalid/private'}]}):
            requests, modules = self.modules(response)
            with patch.dict(sys.modules, modules):
                with self.assertRaisesRegex(RuntimeError, server.SAFE_PROVIDER_ERROR):
                    server.edit_native_image('edit', base64.b64decode(image_bytes()), 'image/png', '9:16')
            requests.get.assert_not_called()

    def test_request_errors_never_echo_credentials_or_provider_text(self):
        requests, modules = self.modules({})
        requests.post.side_effect = RuntimeError('Authorization Bearer private-token')
        with patch.dict(sys.modules, modules):
            with self.assertRaises(RuntimeError) as result:
                server.edit_native_image('edit', base64.b64decode(image_bytes()), 'image/png', '9:16')
        self.assertEqual(str(result.exception), server.SAFE_PROVIDER_ERROR)

    def test_cropped_reference_keeps_its_actual_ratio_without_resize_instruction(self):
        requests, modules = self.modules({'data': [{'b64_json': image_bytes((32, 40))}]})
        with patch.dict(sys.modules, modules):
            result = server.edit_native_image('edit', base64.b64decode(image_bytes((32, 40))), 'image/png', '4:5')
        self.assertNotIn('aspect_ratio', requests.post.call_args.kwargs['json'])
        self.assertEqual(Image.open(io.BytesIO(base64.b64decode(result[0]))).size, (32, 40))


class EditConcurrencyTests(unittest.TestCase):
    def test_edits_and_normal_generation_share_four_global_slots(self):
        lock = threading.Lock()
        full, release = threading.Event(), threading.Event()
        counts = {'active': 0, 'peak': 0}
        def fake(*args):
            with lock:
                counts['active'] += 1
                counts['peak'] = max(counts['peak'], counts['active'])
                if counts['active'] == 4:
                    full.set()
            try:
                release.wait(3)
                return image_bytes(), 'image/png'
            finally:
                with lock:
                    counts['active'] -= 1
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(server.invoke_provider, 'ordinary', '9:16', fake) for _ in range(4)]
            futures += [pool.submit(server.invoke_edit_provider, 'edit', b'owned bytes', 'image/png', '9:16', fake) for _ in range(4)]
            try:
                self.assertTrue(full.wait(2))
                self.assertEqual(counts['peak'], 4)
            finally:
                release.set()
            for future in futures:
                future.result(timeout=3)
        self.assertLessEqual(counts['peak'], 4)


class RealCatalogIntegrationTests(unittest.TestCase):
    def test_every_declared_local_preview_method_accepts_real_catalog_targets(self):
        bundle = server.catalog_v2.load_bundle(server.ROOT)
        self.assertIsNotNone(bundle)
        with tempfile.TemporaryDirectory() as directory:
            from pathlib import Path
            root = Path(directory)
            shutil.copytree(server.ROOT / 'catalog', root / 'catalog')
            shutil.copyfile(server.ROOT / 'library.json', root / 'library.json')
            provider = Mock(side_effect=AssertionError('Local previews must never invoke a provider'))
            app = server.Application(root, provider=provider, edit_provider=provider)
            try:
                image = Image.new('RGB', (90, 160))
                image.putdata([(40+(x*3)%180, 30+(y*2)%190, 60+(x+y)%150) for y in range(160) for x in range(90)])
                data = io.BytesIO()
                image.save(data, 'PNG')
                record = save_image(base64.b64encode(data.getvalue()).decode(), app.store.output_dir, '9:16')
                owned = app.store.add_image(record, 'Local comparison fixture', {})
                failures = []
                for cat in app.catalog.library['categories']:
                    local = [a for a in cat['attributes'] if a['preview_method'] not in ('reference_edit', 'control_only')]
                    if not local:
                        continue
                    groups = set()
                    for attr in local:
                        if attr['comparison_group'] not in groups:
                            review = app.comparisons.review(cat['id'], attribute_id=attr['id'])
                            body = {'image_id': owned['id'], 'attribute_id': attr['id']}
                            # Simulated-human fixture attestation, no live approval.
                            if review['baseline_requirements']:
                                body['baseline_confirmations'] = list(review['baseline_requirements'])
                            app.comparison_post(cat['id'], 'base', body)
                            groups.add(attr['comparison_group'])
                        value = next((v for v in attr['values'] if v['id'] not in ('none', 'off', 'neutral', 'natural')), attr['values'][0])
                        global_scope = attr['preview_scope'] in ('global', 'whole_image', 'wholeframe', 'whole_frame')
                        polygon = [[0,0],[1,0],[1,1],[0,1]] if global_scope else [[.05,.05],[.6,.05],[.6,.7],[.05,.7]]
                        try:
                            app.comparison_post(cat['id'], 'mask', {'attribute_id': attr['id'], 'polygon': polygon})
                            result = app.comparison_post(cat['id'], 'preview', {
                                'attribute_id': attr['id'], 'value_id': value['id'], 'method': attr['preview_method'],
                                'params': {}, 'request_key': 'real-catalog-local-' + attr['id']})
                            if not result.get('url'):
                                failures.append(attr['id'] + ': ' + str(result.get('receipt', {}).get('failure', result.get('error', 'no staged PNG'))))
                            else:
                                self.assertTrue(app.comparisons.asset(result['id']))
                        except ValueError as exc:
                            failures.append(attr['id'] + ': ' + str(exc))
                provider.assert_not_called()
                self.assertEqual(failures, [], 'Catalog/engine local preview contracts must align: ' + '; '.join(failures))
            finally:
                app.close()

    def test_published_control_bundle_loads_in_private_fixture_without_provider_reads(self):
        # Clone catalog files only: private images, databases, presets and runtime
        # configuration are deliberately absent from this fixture installation.
        bundle = server.catalog_v2.load_bundle(server.ROOT)
        self.assertIsNotNone(bundle, 'Catalog owner must finish catalog/v2/library.json before integration is complete')
        with tempfile.TemporaryDirectory() as directory:
            from pathlib import Path
            root = Path(directory)
            shutil.copytree(server.ROOT / 'catalog', root / 'catalog')
            shutil.copyfile(server.ROOT / 'library.json', root / 'library.json')
            provider = Mock(side_effect=AssertionError('provider must not be invoked'))
            app = server.Application(root, provider=provider, edit_provider=provider)
            try:
                self.assertEqual(app.catalog_versions()['active_version'], 2)
                self.assertEqual(app.catalog_versions()['effective_counts']['attributes'], len(app.catalog.attributes))
                self.assertEqual(app.catalog.preview({})['plans'][0]['selections']['gender'], ['woman'])
                plan = app.catalog.preview({'selections': {'age': ['age_85'], 'gender': ['man']}})['plans'][0]
                self.assertIn('85', plan['prompt'])
                self.assertEqual(plan['selections']['gender'], ['man'])
                resolution = app.resolve_draft({'selections': {'age': ['24']}, 'future_field': {'keep': True}})
                self.assertEqual(resolution['draft']['selections']['age'], ['age_24'])
                self.assertEqual(resolution['raw_draft']['selections']['age'], ['24'])
                self.assertEqual(resolution['draft']['future_field'], {'keep': True})
                library, mode, progress = app.thumbnail_library()
                self.assertEqual(mode, 'mixed')
                self.assertTrue(library['historical_library'])
                self.assertTrue(progress['review_required'])
                for cat in library['categories']:
                    for attr in cat['attributes']:
                        if attr['id'] in ('age', 'gender') or attr['control'] == 'swatch':
                            self.assertTrue(all(not value['thumbnail_url'] for value in attr['values']))
                self.assertEqual(len(app.comparisons.list_categories(app.catalog.library)), len(library['categories']))
                provider.assert_not_called()
            finally:
                app.close()


class ComparisonHTTPTests(legacy_tests.HTTPTests):
    def setUp(self):
        super().setUp()
        self.app.close()
        library = copy.deepcopy(LIBRARY)
        library['catalog_version'] = 2
        attrs = library['categories'][0]['attributes']
        for attr in attrs:
            attr.update(control='cards', preview_method='reference_edit', preview_scope='localized', comparison_group='test')
        attrs[0]['preview_method'] = 'masked_recolor'
        for val in attrs[0]['values']:
            val['color'] = {'red': '#cc1122', 'blue': '#1122cc', 'green': '#11bb22'}[val['id']]
        archive = copy.deepcopy(LIBRARY)
        archive['categories'].append({'id': 'retired_category', 'name': 'Archived category', 'attributes': [
            {'id': 'retired', 'name': 'Historic name', 'type': 'exclusive', 'values': [
                {'id': 'old', 'name': 'Historic option', 'steers': 'historic direction'}]}]})
        bundle = {'library': library, 'legacy_library': archive, 'aliases': {}, 'retired': {}, 'coverage': {}}
        self.edits = Mock(return_value=(image_bytes(color='blue'), 'image/png'))
        self.app = server.Application(self.root, catalog=server.Catalog(library, bundle=bundle),
                                      provider=self.provider, edit_provider=self.edits)
        self.httpd.app = self.app
        record = save_image(image_bytes(), self.app.store.output_dir, '9:16')
        self.image = self.app.store.add_image(record, 'owned original', {'color': ['red']})
        self.origin = {'Origin': 'http://127.0.0.1:8123'}

    def post(self, action, payload):
        return self.request('POST', '/api/comparisons/test/' + action, payload, headers=self.origin)

    def base(self):
        status, review, _ = self.post('base', {'image_id': self.image['id']})
        self.assertEqual(status, 200, review)
        return review

    def mask(self, attr='color'):
        status, review, _ = self.post('mask', {'attribute_id': attr,
                                             'polygon': [[.05, .05], [.45, .05], [.45, .65], [.05, .65]]})
        self.assertEqual(status, 200, review)
        return review

    def test_category_review_and_strict_origin_owned_id_body_guards(self):
        status, result, _ = self.request('GET', '/api/comparisons/categories')
        self.assertEqual(status, 200)
        self.assertEqual([c['id'] for c in result['categories']], ['test'])
        self.assertEqual(self.request('GET', '/api/comparisons/test')[1]['state'], 'draft')
        for action, payload in [('base', {'image_id': self.image['id']}), ('mask', {'attribute_id': 'color', 'polygon': []}),
                                ('approve', {'stage': 'contract', 'expected_contract_hash': 'a'*64}),
                                ('preview', {'attribute_id': 'pose', 'value_id': 'a', 'method': 'reference_edit', 'request_key': 'x'})]:
            self.assertEqual(self.request('POST', '/api/comparisons/test/' + action, payload)[0], 403)
            self.assertEqual(self.request('POST', '/api/comparisons/test/' + action, payload,
                                          headers={'Origin': 'https://evil.invalid'})[0], 403)
        for payload in ({'image_path': '/private/photo.jpg'}, {'image_id': '../private'},
                        {'image_id': self.image['id'], 'url': self.image['url']}):
            self.assertEqual(self.post('base', payload)[0], 400)
        self.assertEqual(self.request('POST', '/api/comparisons/missing/base', {'image_id': self.image['id']}, headers=self.origin)[0], 404)
        self.assertEqual(self.post('mask', {'attribute_id': 'unknown', 'polygon': []})[0], 400)
        for params in ({'url': 'https://private.invalid/photo'}, {'nested': {'image_path': '/private/photo'}},
                       {'prompt': 'browser prompt must not replace catalog target'}):
            self.assertEqual(self.post('preview', {'attribute_id': 'pose', 'value_id': 'a', 'method': 'reference_edit',
                                                  'request_key': 'unsafe', 'params': params})[0], 400)
        self.edits.assert_not_called()

    def test_comparison_duplicate_origin_json_keys_and_body_guards(self):
        payload = {'image_id': self.image['id']}
        status = self.request('POST', '/api/comparisons/test/base', payload,
                              headers={**self.origin, 'origin': self.origin['Origin']})[0]
        self.assertEqual(status, 403)
        status = self.request('POST', '/api/comparisons/test/base', headers=self.origin,
                              raw=b'{"image_id":"a","image_id":"b"}')[0]
        self.assertEqual(status, 400)
        self.assertEqual(self.request('POST', '/api/comparisons/test/base', payload,
                                      headers={**self.origin, 'Content-Type': 'text/plain'})[0], 415)
        self.assertEqual(self.request('POST', '/api/comparisons/test/base?extra=1', payload, headers=self.origin)[0], 400)
        self.assertEqual(self.request('POST', '/api/comparisons/test/unknown', {}, headers=self.origin)[0], 404)
        self.edits.assert_not_called()

    def test_registered_png_get_head_corruption_and_no_source_exposure(self):
        review = self.base()
        url = review['baseline']['url']
        status, raw, headers = self.request('GET', url)
        self.assertEqual(status, 200)
        self.assertEqual(headers['Content-Type'], 'image/png')
        self.assertEqual(Image.open(io.BytesIO(raw)).format, 'PNG')
        status, raw_head, head = self.request('HEAD', url)
        self.assertEqual((status, raw_head, head['Content-Length']), (200, b'', str(len(raw))))
        self.assertNotIn(str(self.root), json.dumps(review))
        for path in ('/comparisons.sqlite3', '/generated/comparisons/' + review['baseline']['asset_id'] + '.png',
                     '/api/comparisons/assets/' + 'a'*32 + '.png', '/api/comparisons/assets/../server.py'):
            self.assertEqual(self.request('GET', path)[0], 404)
        asset = self.app.comparisons.asset(review['baseline']['asset_id'])
        asset.write_bytes(b'corrupted')
        self.assertEqual(self.request('GET', url)[0], 404)

    def test_owned_gallery_storage_outside_catalog_root_can_anchor_without_source_rewrite(self):
        with tempfile.TemporaryDirectory() as directory:
            from pathlib import Path
            output = Path(directory) / 'private-photos'
            self.app.store = Gallery(self.app.store.db_path, output)
            record = save_image(image_bytes(), output, '9:16')
            self.image = self.app.store.add_image(record, 'owned external storage', {'color': ['red']})
            source = output / record['filename']
            original = source.read_bytes()
            review = self.base()
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(review['baseline']['image_id'], self.image['id'])
            self.assertNotIn(directory, json.dumps(review))
            self.assertEqual(self.request('GET', review['baseline']['url'])[0], 200)

    def test_preview_unapproved_has_zero_calls_then_contract_budget_and_idempotent_receipt(self):
        self.base()
        payload = {'attribute_id': 'pose', 'value_id': 'a', 'method': 'reference_edit', 'request_key': 'provider-pilot'}
        self.assertEqual(self.post('preview', payload)[0], 400)
        self.edits.assert_not_called()
        review = self.mask('pose')
        self.assertEqual(self.post('preview', payload)[0], 400)
        self.edits.assert_not_called()
        status, review, _ = self.post('approve', {'stage': 'contract', 'expected_contract_hash': review['contract_hash'],
                                                'provider_attempt_cap': 1, 'approval_note': 'Operator reviewed reference and footprint.'})
        self.assertEqual(status, 200, review)
        status, result, _ = self.post('preview', payload)
        self.assertEqual(status, 200, result)
        self.assertTrue(result.get('url'), result)
        self.assertEqual(self.edits.call_count, 1)
        self.assertEqual(self.post('preview', payload)[1], result)
        self.assertEqual(self.edits.call_count, 1)
        self.assertEqual(self.post('preview', dict(payload, request_key='exhausted'))[0], 400)
        self.assertEqual(self.edits.call_count, 1)

    def test_local_draft_is_pending_until_reviewed_publication(self):
        self.base()
        review = self.mask()
        request = {'attribute_id': 'color', 'value_id': 'blue', 'method': 'masked_recolor', 'request_key': 'local-blue'}
        status, draft, _ = self.post('preview', request)
        self.assertEqual(status, 200, draft)
        values = self.request('GET', '/api/library')[1]['categories'][0]['attributes'][0]['values']
        self.assertEqual(next(v for v in values if v['id'] == 'blue')['thumbnail_url'], '')
        status = self.request('GET', '/api/thumbnail-status')[1]
        self.assertEqual(status['status'], 'paused')
        self.assertTrue(status['review_required'])
        status, review, _ = self.post('approve', {'stage': 'contract', 'expected_contract_hash': review['contract_hash'],
                                                'approval_note': 'Operator reviewed original and color mask.'})
        self.assertEqual(status, 200, review)
        # Re-render with the reviewed contract, rather than adopting a draft blindly.
        status, artifact, _ = self.post('preview', dict(request, request_key='reviewed-blue'))
        self.assertEqual(status, 200, artifact)
        for stage in ('pilot', 'publish'):
            status, review, _ = self.post('approve', {'stage': stage, 'expected_contract_hash': review['contract_hash'],
                                                    'artifact_ids': [artifact['id']], 'approval_note': 'Operator accepted texture, target effect and locked identity.'})
            self.assertEqual(status, 200, review)
        values = self.request('GET', '/api/library')[1]['categories'][0]['attributes'][0]['values']
        selected = next(v for v in values if v['id'] == 'blue')
        self.assertEqual(selected['thumbnail_url'], artifact['url'])
        self.assertEqual(selected['thumbnail_source'], 'approved_comparison')
        self.edits.assert_not_called()

    def test_historical_gallery_filters_and_labels_new_generation_origin(self):
        record = save_image(image_bytes(), self.app.store.output_dir, '9:16')
        old = self.app.store.add_image(record, 'old retired', {'retired': ['old']})
        from urllib.parse import urlencode
        query = urlencode({'filters': json.dumps({'retired': ['old']})})
        status, gallery, _ = self.request('GET', '/api/gallery?' + query)
        self.assertEqual(status, 200)
        self.assertEqual(gallery['total'], 1)
        detail = self.request('GET', '/api/images/' + old['id'])[1]
        self.assertEqual(detail['resolved_selection_snapshot']['retired']['values'][0]['name'], 'Historic option')
        self.assertEqual(self.request('POST', '/api/preview', {'selections': {'retired': ['old']}})[0], 400)
        self.assertEqual(self.request('POST', '/api/jobs', {})[0], 403)
        historical = self.request('GET', '/api/library')[1]['historical_library']
        archived = next(c for c in historical['categories'] if c['id'] == 'retired_category')
        self.assertTrue(archived['historical_only'])
        self.provider.assert_not_called()

    def test_legacy_registry_is_only_same_semantic_ids_and_independent_label(self):
        manifest = {'version': 1, 'status': 'completed', 'attributes': {'color': {'values': {'red': {
            'status': 'ready', 'image_id': self.image['id'], 'example_url': self.image['url'],
            'thumbnail_url': self.image['thumbnail_url']}}}}}
        (self.app.store.output_dir / 'photographic-previews.json').write_text(json.dumps(manifest))
        library = self.request('GET', '/api/library')[1]
        red = library['categories'][0]['attributes'][0]['values'][0]
        self.assertEqual(red['thumbnail_url'], self.image['thumbnail_url'])
        self.assertEqual(red['thumbnail_source'], 'legacy_independent')
        self.app.catalog.attributes['color']['values'][0]['steers'] = 'semantically different new red recipe'
        library = self.request('GET', '/api/library')[1]
        red = library['categories'][0]['attributes'][0]['values'][0]
        self.assertEqual(red['thumbnail_url'], '')
        self.assertEqual(red['thumbnail_status'], 'pending')

    def test_failed_reference_edit_consumes_budget_and_sanitizes_receipt(self):
        self.base()
        review = self.mask('pose')
        self.post('approve', {'stage': 'contract', 'expected_contract_hash': review['contract_hash'],
                             'provider_attempt_cap': 1, 'approval_note': 'Operator approves this bounded attempt.'})
        self.edits.side_effect = RuntimeError('private provider Bearer secret-token')
        payload = {'attribute_id': 'pose', 'value_id': 'a', 'method': 'reference_edit', 'request_key': 'fail-once'}
        status, result, _ = self.post('preview', payload)
        self.assertEqual(status, 200)
        self.assertFalse(result.get('url'))
        self.assertNotIn('secret-token', json.dumps(result))
        review = self.request('GET', '/api/comparisons/test')[1]
        self.assertEqual(review['budget'], {'cap': 1, 'used': 1})
        self.assertEqual(self.post('preview', dict(payload, request_key='retry-fail'))[0], 400)
        self.assertEqual(self.edits.call_count, 1)


# Avoid inherited old test methods in this module's test loader.
for _name in dir(legacy_tests.HTTPTests):
    if _name.startswith('test_') and _name not in V2HTTPTests.__dict__:
        setattr(V2HTTPTests, _name, None)
    if _name.startswith('test_') and _name not in ComparisonHTTPTests.__dict__:
        setattr(ComparisonHTTPTests, _name, None)

if __name__ == '__main__':
    unittest.main()
