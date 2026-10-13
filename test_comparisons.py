import base64
import hashlib
import io
import json
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import patch
from pathlib import Path

from PIL import Image, ImageChops

from comparisons import ComparisonStore


def png(image):
    out = io.BytesIO()
    image.save(out, 'PNG')
    return out.getvalue()


def library():
    return {'categories': [
        {'id': 'hair', 'name': 'Hair', 'attributes': [
            {'id': 'hair_color', 'name': 'Hair color', 'type': 'exclusive', 'preview_method': 'masked_recolor',
             'preview_scope': 'localized', 'values': [{'id': 'red', 'name': 'Red', 'color': '#a63d21'},
                                                   {'id': 'black', 'name': 'Black', 'color': '#18191a'}]},
            {'id': 'hair_cut', 'name': 'Cut', 'type': 'exclusive', 'preview_method': 'reference_edit',
             'preview_scope': 'localized', 'values': [{'id': 'bob', 'name': 'Bob', 'steers': 'short bob haircut'}]},
        ]},
        {'id': 'photography', 'name': 'Photography', 'attributes': [
            {'id': 'grain', 'name': 'Grain', 'type': 'exclusive', 'preview_method': 'simulated_optics',
             'preview_scope': 'global', 'values': [{'id': 'fine', 'name': 'Fine grain'}]},
        ]},
        {'id': 'wardrobe', 'name': 'Wardrobe', 'attributes': [
            {'id': 'garment_color', 'name': 'Color', 'type': 'exclusive', 'preview_method': 'fabric_swatch',
             'preview_scope': 'swatch', 'values': [{'id': 'red', 'name': 'Red', 'color': '#a63d21'}]},
        ]},
        {'id': 'age', 'name': 'Age', 'attributes': [
            {'id': 'age', 'type': 'exclusive', 'preview_method': 'control_only', 'values': [{'id': 'age_24'}]},
        ]},
    ]}


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.lib = library()
        self.store = ComparisonStore(self.root)
        self.store.list_categories(self.lib)
        # An owned source fixture, never a production photograph.
        self.source = self.root / 'generated' / 'owned.jpg'
        self.source.parent.mkdir(exist_ok=True)
        image = Image.new('RGB', (32, 40))
        image.putdata([(60 + (x * 3) % 100, 70 + (y * 2) % 100, 80) for y in range(40) for x in range(32)])
        image.save(self.source, 'JPEG')
        self.mask = [[0.05, 0.05], [0.45, 0.05], [0.45, 0.65], [0.05, 0.65]]

    def tearDown(self):
        self.tmp.cleanup()

    def prepared(self, category='hair', attr='hair_color', approve=False, cap=0):
        review = self.store.set_base(category, self.source, 'owned', 'woman-1')
        review = self.store.set_mask(category, attr, self.mask)
        if approve:
            review = self.store.approve(category, 'contract', review['contract_hash'], provider_attempt_cap=cap,
                                        approval_note='Operator approves original reference and reviewed mask')
        return review

    def render(self, attr='hair_color', value='red', method='masked_recolor', key='r1', params=None, provider=None, category='hair'):
        return self.store.render(category, attr, value, method, params or {}, key, self.lib, provider)

    def test_category_review_shapes_and_unknown_categories(self):
        summaries = self.store.list_categories(self.lib)
        self.assertEqual({c['id'] for c in summaries}, {'hair', 'photography', 'wardrobe', 'age'})
        review = self.store.review('hair')
        for field in ('state', 'contract_hash', 'baseline', 'masks', 'artifacts', 'budget', 'locked_fields', 'allowed_changes'):
            self.assertIn(field, review)
        self.assertEqual(review['state'], 'draft')
        with self.assertRaises(ValueError):
            self.store.review('../hair')

    def test_base_is_lossless_immutable_registered_and_source_is_private(self):
        review = self.prepared()
        base = review['baseline']
        path = self.store.asset(base['asset_id'])
        self.assertEqual(path.suffix, '.png')
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), base['sha256'])
        self.assertEqual((base['width'], base['height']), (32, 40))
        self.assertNotIn(str(self.root), json.dumps(review))
        self.assertEqual(self.store.asset('../owned.jpg'), None)
        self.assertEqual(self.store.asset('a' * 32), None)
        original = path.read_bytes()
        Image.new('RGB', (32, 40), 'white').save(self.source, 'JPEG')
        self.assertEqual(path.read_bytes(), original)
        with Image.open(path) as image:
            self.assertEqual(image.format, 'PNG')
            image.verify()

    def test_crop_pins_normalized_reference(self):
        review = self.store.set_base('hair', self.source, 'owned', crop=[0.25, 0.25, 0.75, 0.75])
        self.assertEqual((review['baseline']['width'], review['baseline']['height']), (16, 20))
        with self.assertRaises(ValueError):
            self.store.set_base('hair', self.source, 'owned', crop=[0, 0, 2, 1])

    def test_masks_require_independent_normalized_nonwholeframe_polygon(self):
        self.store.set_base('hair', self.source, 'owned')
        for polygon in ([[]], [[0, 0], [1, 1]], [[-1, 0], [0.5, 0], [0.2, 1]],
                        [[0, 0], [1, 0], [1, 1], [0, 1]], [[0, 0], [0.1, 0.1], [0.2, 0.2]]):
            with self.subTest(polygon=polygon), self.assertRaises(ValueError):
                self.store.set_mask('hair', 'hair_color', polygon)
        with self.assertRaises(ValueError):
            self.store.set_mask('hair', 'grain', self.mask)
        review = self.store.set_mask('hair', 'hair_color', self.mask)
        mask = review['masks']['hair_color']
        self.assertIn('sha256', mask)
        self.assertIn('coverage', mask)
        self.assertIn('overlay_url', mask)

    def test_contract_gate_locks_reference_mask_and_cap(self):
        draft = self.prepared()
        with self.assertRaises(ValueError):
            self.store.approve('hair', 'contract', '0' * 64, provider_attempt_cap=3)
        review = self.store.approve('hair', 'contract', draft['contract_hash'], provider_attempt_cap=2,
                                    approval_note='Approved mask and reference')
        self.assertEqual(review['state'], 'contract_approved')
        self.assertEqual(review['budget'], {'cap': 2, 'used': 0})
        self.assertEqual(review['cycle'], {'id': 1, 'cap': 2, 'used': 0})
        for edit in (lambda: self.store.set_mask('hair', 'hair_color', self.mask),
                     lambda: self.store.set_base('hair', self.source, 'owned')):
            with self.assertRaisesRegex(ValueError, 'Reopen'):
                edit()
            self.assertEqual(self.store.review('hair'), review)
        for digest, note in ((review['contract_hash'], ''), (review['contract_hash'], '   '),
                             ('0' * 64, 'Revise footprint')):
            with self.subTest(digest=digest, note=note), self.assertRaises(ValueError):
                self.store.reopen('hair', digest, note)
            self.assertEqual(self.store.review('hair'), review)
        note = 'Explicitly reopen to revise the footprint and original reference'
        reopened = self.store.reopen('hair', review['contract_hash'], note)
        self.assertEqual(reopened['state'], 'draft')
        self.assertEqual(reopened['approvals'], [])
        self.assertEqual(reopened['budget'], {'cap': 0, 'used': 0})
        self.assertNotEqual(reopened['contract_hash'], review['contract_hash'])
        self.assertEqual(reopened['revision'], review.get('revision', 0) + 1)
        self.assertEqual(reopened['baseline'], review['baseline'])
        self.assertEqual(reopened['masks'], review['masks'])
        event = reopened['history'][-2]
        self.assertEqual(event['event'], 'operator_reopen')
        self.assertEqual(event['data']['note'], note)
        self.assertEqual(event['data']['expected_contract_hash'], review['contract_hash'])
        for field in ('state', 'contract_hash', 'baseline', 'masks', 'approvals', 'artifacts'):
            self.assertEqual(event['data']['previous'][field], review[field])
        self.assertEqual(event['data']['previous']['budget'],
                         {'cap': 2, 'used': 0, 'cycle_id': 1, 'cycle_used': 0})
        self.assertEqual(reopened['history'][-1]['event'], 'reopened_contract_archived')
        with self.assertRaisesRegex(ValueError, 'Only an approved'):
            self.store.reopen('hair', reopened['contract_hash'], 'Already in draft')
        changed = self.store.set_mask('hair', 'hair_color', self.mask)
        self.assertEqual(changed['state'], 'draft')
        self.assertEqual(changed['approvals'], [])
        self.assertTrue(changed['history'])
        self.assertEqual(changed['history'][-2]['event'], 'mask_replaced_previous')
        self.assertEqual(changed['history'][-2]['data']['masks'], reopened['masks'])
        changed = self.store.set_base('hair', self.source, 'owned')
        self.assertEqual(changed['state'], 'draft')
        self.assertEqual(changed['masks'], {})
        self.assertEqual(changed['history'][-2]['event'], 'base_replaced_previous')
        with self.assertRaisesRegex(ValueError, 'integer from 0 to 3'):
            self.store.approve('hair', 'contract', review['contract_hash'], provider_attempt_cap=12)

        # Explicit group selectors must agree and reopening one cannot unlock another.
        for attr in self.lib['categories'][0]['attributes']:
            attr['comparison_group'] = 'hair:' + attr['id']
        self.store.list_categories(self.lib)
        groups = {}
        for attr in ('hair_color', 'hair_cut'):
            group = 'hair:' + attr
            self.store.set_base('hair', self.source, 'owned', attribute_id=attr, group=group)
            draft = self.store.set_mask('hair', attr, self.mask, group=group)
            groups[attr] = self.store.approve('hair', 'contract', draft['contract_hash'],
                                             attribute_id=attr, group=group)
        with self.assertRaisesRegex(ValueError, 'group does not match'):
            self.store.reopen('hair', groups['hair_color']['contract_hash'], 'Revise pigment only',
                              attribute_id='hair_color', group='hair:hair_cut')
        reopened = self.store.reopen('hair', groups['hair_color']['contract_hash'], 'Revise pigment only',
                                     attribute_id='hair_color', group='hair:hair_color')
        self.assertEqual(reopened['group'], 'hair:hair_color')
        self.assertEqual(reopened['state'], 'draft')
        self.assertEqual(self.store.review('hair', group='hair:hair_cut'), groups['hair_cut'])
        self.store.set_mask('hair', 'hair_color', self.mask, group='hair:hair_color')
        with self.assertRaisesRegex(ValueError, 'Reopen'):
            self.store.set_mask('hair', 'hair_cut', self.mask, group='hair:hair_cut')

    def test_local_draft_never_publishes_without_gates(self):
        review = self.prepared()
        artifact = self.render()
        self.assertEqual(artifact['receipt']['status'], 'staged')
        self.assertFalse(artifact['accepted'])
        self.assertEqual(self.store.review('hair')['state'], 'draft')
        for stage in ('pilot', 'publish'):
            with self.assertRaises(ValueError):
                self.store.approve('hair', stage, review['contract_hash'], artifact_ids=[artifact['id']])

    def test_color_forks_original_base_and_exact_outside_mask_pixels(self):
        review = self.prepared()
        red = self.render()
        black = self.render(value='black', key='r2')
        self.assertEqual(red['receipt']['base_sha256'], review['baseline']['sha256'])
        self.assertEqual(black['receipt']['base_sha256'], review['baseline']['sha256'])
        self.assertEqual(red['receipt']['outside_mask_changed_pixels'], 0)
        self.assertGreater(red['receipt']['target_changed_pixels'], 0)
        with Image.open(self.store.asset(review['baseline']['asset_id'])) as base, \
             Image.open(self.store.asset(red['id'])) as edited, \
             Image.open(self.store.asset(review['masks']['hair_color']['asset_id'])) as mask:
            difference = ImageChops.difference(base.convert('RGB'), edited.convert('RGB'))
            # Nonzero antialiased mask samples are inside the approved footprint.
            outside = mask.convert('L').point(lambda x: 255 if x == 0 else 0)
            self.assertIsNone(ImageChops.multiply(difference, outside.convert('RGB')).getbbox())
        self.assertNotEqual(red['receipt']['output_sha256'], black['receipt']['output_sha256'])

    def test_request_idempotency_and_conflict_persist_across_restart(self):
        self.prepared()
        first = self.render()
        reopened = ComparisonStore(self.root)
        second = reopened.render('hair', 'hair_color', 'red', 'masked_recolor', {}, 'r1', self.lib)
        self.assertEqual(first, second)
        self.assertEqual(len(reopened.review('hair')['artifacts']), 1)
        with self.assertRaises(ValueError):
            self.render(value='black')

    def test_unapproved_or_missing_local_mask_never_calls_provider(self):
        calls = []
        def provider(*args):
            calls.append(args)
            raise AssertionError('Should not call')
        self.prepared()
        with self.assertRaises(ValueError):
            self.render('hair_cut', 'bob', 'reference_edit', provider=provider)
        self.assertEqual(calls, [])
        review = self.store.review('hair')
        self.store.approve('hair', 'contract', review['contract_hash'], provider_attempt_cap=1)
        with self.assertRaises(ValueError):
            self.render('hair_cut', 'bob', 'reference_edit', provider=provider)
        self.assertEqual(calls, [])

    def test_reference_edit_uses_owned_png_original_and_reserves_cap_once(self):
        review = self.prepared(attr='hair_cut', approve=True, cap=1)
        calls = []
        base = self.store.asset(review['baseline']['asset_id']).read_bytes()
        def provider(prompt, image_bytes, mime, aspect_ratio):
            calls.append((prompt, image_bytes, mime, aspect_ratio))
            image = Image.open(io.BytesIO(image_bytes)).convert('RGB')
            image.paste((230, 10, 20), (0, 0, 32, 40))
            return base64.b64encode(png(image)).decode(), 'image/png'
        artifact = self.render('hair_cut', 'bob', 'reference_edit', provider=provider)
        self.assertEqual(calls[0][1], base)
        self.assertEqual(calls[0][2], 'image/png')
        self.assertIn('bob', calls[0][0].lower())
        for word in ('cute', 'beautiful', 'gorgeous'):
            self.assertRegex(calls[0][0], rf'\b{word}\b')
        self.assertIn('do not reshape or beautify the approved face', calls[0][0])
        import hashlib
        self.assertEqual(artifact['receipt']['provider_prompt_sha256'], hashlib.sha256(calls[0][0].encode()).hexdigest())
        self.assertEqual(artifact['receipt']['outside_mask_changed_pixels'], 0)
        self.assertGreater(artifact['receipt']['provider_outside_mask_changed_pixels'], 0)
        self.assertEqual(self.store.review('hair')['budget'], {'cap': 1, 'used': 1})
        self.assertEqual(artifact, self.render('hair_cut', 'bob', 'reference_edit', provider=provider))
        self.assertEqual(len(calls), 1)
        with self.assertRaises(ValueError):
            self.render('hair_cut', 'bob', 'reference_edit', key='r2', provider=provider)

    def test_provider_failure_consumes_cap_and_records_sanitized_receipt(self):
        self.prepared(attr='hair_cut', approve=True, cap=1)
        def provider(*args):
            raise RuntimeError('token=private-secret /home/private image')
        result = self.render('hair_cut', 'bob', 'reference_edit', provider=provider)
        self.assertEqual(result['receipt']['status'], 'failed')
        self.assertIn('output_sha256', result['receipt'])
        self.assertIn('outside_delta', result['receipt'])
        self.assertIn('inside_change', result['receipt'])
        self.assertFalse(result['receipt']['simulated'])
        self.assertTrue(result['receipt']['limitations'])
        self.assertNotIn('private-secret', json.dumps(result))
        self.assertEqual(self.store.review('hair')['budget']['used'], 1)
        self.assertEqual(result, self.render('hair_cut', 'bob', 'reference_edit', provider=provider))
        self.assertEqual(self.store.review('hair')['state'], 'contract_approved')

    def test_invalid_resized_and_unchanged_provider_output_withheld(self):
        for case in ('resized', 'unchanged', 'invalid'):
            with self.subTest(case=case):
                tmp = tempfile.TemporaryDirectory()
                store = ComparisonStore(Path(tmp.name))
                store.list_categories(self.lib)
                source = Path(tmp.name) / 'base.png'
                Image.new('RGB', (32, 40), 'gray').save(source)
                review = store.set_base('hair', source, 'base')
                review = store.set_mask('hair', 'hair_cut', self.mask)
                store.approve('hair', 'contract', review['contract_hash'], provider_attempt_cap=1)
                def provider(prompt, image_bytes, mime, aspect):
                    if case == 'invalid':
                        return 'invalid', 'image/png'
                    if case == 'unchanged':
                        return base64.b64encode(image_bytes).decode(), 'image/png'
                    return base64.b64encode(png(Image.new('RGB', (10, 10), 'red'))).decode(), 'image/png'
                result = store.render('hair', 'hair_cut', 'bob', 'reference_edit', {}, 'one', self.lib, provider)
                self.assertEqual(result['receipt']['status'], 'failed')
                self.assertIsNone(result['url'])
                self.assertEqual(store.review('hair')['artifacts'], [])
                tmp.cleanup()

    def test_pilot_acceptance_then_publication_records_hashes_and_artifacts(self):
        review = self.prepared(approve=True)
        artifact = self.render()
        self.assertEqual(self.store.review('hair')['state'], 'pilot_done')
        review = self.store.approve('hair', 'pilot', review['contract_hash'], artifact_ids=[artifact['id']],
                                    approval_note='Inspected target, edges, identity and mask at 1x and 2x')
        self.assertEqual(review['state'], 'pilot_accepted')
        self.assertTrue(review['artifacts'][0]['accepted'])
        review = self.store.approve('hair', 'publish', review['contract_hash'], artifact_ids=[artifact['id']],
                                    approval_note='Publish reviewed pilot')
        self.assertEqual(review['state'], 'published')
        self.assertEqual(review['approvals'][-1]['artifact_hashes'][artifact['id']], artifact['receipt']['output_sha256'])

    def test_corruption_and_wrong_artifact_stop_publication(self):
        review = self.prepared(approve=True)
        artifact = self.render()
        for ids in ([], ['a' * 32]):
            with self.assertRaises(ValueError):
                self.store.approve('hair', 'pilot', review['contract_hash'], artifact_ids=ids)
        path = self.store.asset(artifact['id'])
        path.write_bytes(b'corrupt')
        self.assertIsNone(self.store.asset(artifact['id']))
        with self.assertRaises(ValueError):
            self.store.approve('hair', 'pilot', review['contract_hash'], artifact_ids=[artifact['id']])

    def test_swatch_generates_texture_png_without_provider_or_woman_reference(self):
        artifact = self.render('garment_color', 'red', 'fabric_swatch', category='wardrobe')
        self.assertEqual(artifact['receipt']['method'], 'fabric_swatch')
        self.assertIn('texture', artifact['receipt']['method_label'].lower())
        with Image.open(self.store.asset(artifact['id'])) as image:
            self.assertEqual(image.format, 'PNG')
            self.assertGreater(len(set(image.get_flattened_data())), 1)
        self.assertEqual(self.store.review('wardrobe')['budget']['used'], 0)

    def test_simulated_optical_global_effect_is_labeled_and_reproducible(self):
        self.store.set_base('photography', self.source, 'owned')
        self.store.set_mask('photography', 'grain', [[0, 0], [1, 0], [1, 1], [0, 1]])
        artifact = self.render('grain', 'fine', 'simulated_optics', params={'effect': 'grain', 'amount': 10},
                               category='photography')
        self.assertIn('simulated', artifact['receipt']['method_label'].lower())
        self.assertEqual(artifact['receipt']['outside_mask_changed_pixels'], 0)
        self.assertGreater(artifact['receipt']['target_changed_pixels'], 0)

    def test_method_validation_does_not_allow_control_or_method_substitution(self):
        self.prepared()
        for args in (('hair_color', 'red', 'reference_edit', 'hair'),
                     ('hair_color', 'unknown', 'masked_recolor', 'hair'),
                     ('age', 'age_24', 'fabric_swatch', 'age')):
            with self.subTest(args=args), self.assertRaises(ValueError):
                self.render(args[0], args[1], args[2], category=args[3])
        with self.assertRaises(ValueError):
            self.render(params={'image_path': '/etc/passwd'})

    def test_schema_contains_assets_and_request_reservations(self):
        self.prepared()
        artifact = self.render()
        with sqlite3.connect(self.root / 'comparisons.sqlite3') as db:
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertIn('comparison_assets', tables)
        self.assertIn('comparison_requests', tables)
        self.assertTrue((self.root / 'generated' / 'comparisons' / f"{artifact['id']}.png").is_file())


class SafetyTests(unittest.TestCase):
    store: ComparisonStore
    setUp = ComparisonTests.setUp
    tearDown = ComparisonTests.tearDown
    prepared = ComparisonTests.prepared
    render = ComparisonTests.render

    def test_all_declared_local_effects_generate_real_pngs_and_labels(self):
        settings = {
            'grain': {'seed': 42, 'amount': 12},
            'white_balance': {'temperature': .4, 'tint': .1},
            'gentlehighlight_rolloff': {'strength': .5, 'threshold': .3},
            'focal_fov': {'factor': 1.5},
            'focus_depth_blur': {'radius': 2, 'depth_assumption': 'masked background farther than subject'},
            'aperture_blur': {'radius': 2, 'depth_assumption': 'single flat depth plane, constant brightness'},
            'motion_blur': {'distance': 5, 'direction': 30, 'moving_region': 'masked cloth including swept footprint'},
        }
        for method, params in settings.items():
            with self.subTest(method=method):
                attr = {'id': method, 'preview_method': method,
                        'preview_scope': 'global' if method in list(settings)[:4] else 'localized',
                        'values': [{'id': 'demo'}]}
                self.lib['categories'][1]['attributes'] = [attr]
                self.store.list_categories(self.lib)
                self.store.set_base('photography', self.source, 'owned')
                if attr['preview_scope'] == 'localized':
                    self.store.set_mask('photography', method, self.mask)
                artifact = self.render(method, 'demo', method, method, params, category='photography')
                receipt = artifact['receipt']
                self.assertTrue(receipt['simulated'])
                self.assertGreater(receipt['inside_change']['changed_pixels'], 0)
                self.assertEqual(receipt['outside_delta'], 0)
                self.assertTrue(receipt['limitations'])
                self.assertTrue(receipt['method_label'])

    def test_rgba_alpha_edges_and_zero_outside_footprint(self):
        Image.new('RGBA', (32, 40), (100, 110, 120, 123)).save(self.source, 'PNG')
        review = self.prepared()
        artifact = self.render()
        base = Image.open(self.store.asset(review['baseline']['asset_id'])).convert('RGBA')
        output = Image.open(self.store.asset(artifact['id'])).convert('RGBA')
        mask = Image.open(self.store.asset(review['masks']['hair_color']['asset_id'])).convert('L')
        self.assertEqual(base.getchannel('A').tobytes(), output.getchannel('A').tobytes())
        self.assertTrue(any(0 < p < 255 for p in mask.get_flattened_data()))
        for before, after, alpha in zip(base.get_flattened_data(), output.get_flattened_data(), mask.get_flattened_data()):
            if not alpha:
                self.assertEqual(before, after)

    def test_mask_change_keeps_budget_consumption_and_archived_artifacts(self):
        review = self.prepared(attr='hair_cut', approve=True, cap=1)
        calls = []
        def provider(*args):
            calls.append(args)
            return base64.b64encode(png(Image.new('RGB', (32, 40), 'red'))).decode(), 'image/png'
        artifact = self.render('hair_cut', 'bob', 'reference_edit', provider=provider)
        previous = self.store.review('hair')
        original_bytes = self.store.asset(artifact['id']).read_bytes()
        polygon = [[.1, .1], [.5, .1], [.5, .7], [.1, .7]]
        with self.assertRaisesRegex(ValueError, 'Reopen'):
            self.store.set_mask('hair', 'hair_cut', polygon)
        self.assertEqual(self.store.review('hair'), previous)
        with self.assertRaisesRegex(ValueError, 'budget exhausted'):
            self.render('hair_cut', 'bob', 'reference_edit', key='exhausted', provider=provider)
        reopened = self.store.reopen('hair', previous['contract_hash'], 'Revise haircut mask after pilot inspection')
        self.assertEqual(reopened['budget'], {'cap': 0, 'used': 1})
        self.assertEqual(reopened['cycle'], {'id': 1, 'cap': 0, 'used': 1})
        self.assertEqual(reopened['attempts'], previous['attempts'])
        self.assertEqual(reopened['history'][-2]['event'], 'operator_reopen')
        self.assertEqual(reopened['history'][-2]['data']['previous']['artifacts'], previous['artifacts'])
        self.assertEqual(reopened['history'][-2]['data']['previous']['approvals'], previous['approvals'])
        changed = self.store.set_mask('hair', 'hair_cut', polygon)
        self.assertEqual(changed['state'], 'draft')
        self.assertEqual(changed['budget']['used'], 1)
        self.assertEqual(changed['artifacts'], [])
        self.assertTrue(self.store.asset(artifact['id']))
        self.assertEqual(self.store.asset(artifact['id']).read_bytes(), original_bytes)
        self.assertEqual(changed['approvals'], [])
        self.assertNotEqual(changed['contract_hash'], previous['contract_hash'])
        self.assertNotEqual(changed['masks']['hair_cut']['sha256'], previous['masks']['hair_cut']['sha256'])
        self.assertEqual(changed['history'][-2]['event'], 'mask_replaced_previous')
        self.assertEqual(changed['history'][-2]['data']['masks'], reopened['masks'])
        with self.assertRaisesRegex(ValueError, 'Operator contract'):
            self.render('hair_cut', 'bob', 'reference_edit', key='new', provider=provider)
        with self.assertRaisesRegex(ValueError, 'different parameters or contract'):
            self.render('hair_cut', 'bob', 'reference_edit', provider=provider)
        with self.assertRaisesRegex(ValueError, 'Stale or incorrect'):
            self.store.approve('hair', 'contract', review['contract_hash'])
        self.assertEqual(len(calls), 1)

        approved = self.store.approve('hair', 'contract', changed['contract_hash'], provider_attempt_cap=1,
                                      approval_note='Approve one attempt with the revised footprint')
        self.assertEqual(approved['budget'], {'cap': 1, 'used': 1})
        self.assertEqual(approved['cycle'], {'id': 2, 'cap': 1, 'used': 0})
        self.assertEqual(approved['approvals'][-1]['total_used'], 1)
        with self.assertRaisesRegex(ValueError, 'current original-base contract'):
            self.store.approve('hair', 'pilot', changed['contract_hash'], [artifact['id']])
        candidate = self.render('hair_cut', 'bob', 'reference_edit', key='new', provider=provider)
        self.assertEqual(candidate['receipt']['cycle_id'], 2)
        self.assertEqual(candidate['receipt']['total_used'], 2)
        self.assertEqual(candidate, self.render('hair_cut', 'bob', 'reference_edit', key='new', provider=provider))
        self.assertEqual(len(calls), 2)
        with self.assertRaisesRegex(ValueError, 'budget exhausted'):
            self.render('hair_cut', 'bob', 'reference_edit', key='second-exhausted', provider=provider)
        with self.assertRaisesRegex(ValueError, 'Accept the previous pilot'):
            self.store.approve('hair', 'expansion', approved['contract_hash'], provider_attempt_cap=1,
                               approval_note='Premature expansion')
        accepted = self.store.approve('hair', 'pilot', approved['contract_hash'], [candidate['id']])
        with self.assertRaisesRegex(ValueError, 'Contract already approved'):
            self.store.approve('hair', 'contract', accepted['contract_hash'], provider_attempt_cap=1)
        for digest, note, cap in ((accepted['contract_hash'], '', 1),
                                  ('0' * 64, 'Expand', 1), (accepted['contract_hash'], 'Expand', 4)):
            with self.subTest(digest=digest, note=note, cap=cap), self.assertRaises(ValueError):
                self.store.approve('hair', 'expansion', digest, provider_attempt_cap=cap, approval_note=note)
            self.assertEqual(self.store.review('hair'), accepted)

        # The cap bounds each explicit cycle; lifetime consumption may exceed three.
        for cycle_id in (3, 4):
            expanded = self.store.approve('hair', 'expansion', accepted['contract_hash'], provider_attempt_cap=1,
                                          approval_note=f'Operator approves one further attempt in cycle {cycle_id}')
            self.assertEqual(expanded['budget'], {'cap': 1, 'used': cycle_id - 1})
            self.assertEqual(expanded['cycle'], {'id': cycle_id, 'cap': 1, 'used': 0})
            self.assertEqual(expanded['contract_hash'], changed['contract_hash'])
            self.assertEqual(expanded['approvals'][-1]['total_used'], cycle_id - 1)
            self.assertEqual(candidate, self.render('hair_cut', 'bob', 'reference_edit', key='new', provider=provider))
            self.assertEqual(len(calls), cycle_id - 1)
            next_candidate = self.render('hair_cut', 'bob', 'reference_edit', key=f'cycle-{cycle_id}', provider=provider)
            self.assertEqual(next_candidate['receipt']['cycle_id'], cycle_id)
            self.assertEqual(next_candidate['receipt']['total_used'], cycle_id)
            with self.assertRaisesRegex(ValueError, 'budget exhausted'):
                self.render('hair_cut', 'bob', 'reference_edit', key=f'exhausted-{cycle_id}', provider=provider)
            accepted = self.store.approve('hair', 'pilot', expanded['contract_hash'], [next_candidate['id']])
        self.assertEqual(len(calls), 4)
        self.assertEqual(accepted['budget'], {'cap': 1, 'used': 4})
        self.assertEqual(accepted['cycle'], {'id': 4, 'cap': 1, 'used': 1})
        self.assertEqual(len(accepted['attempts']), 4)
        self.assertEqual(accepted['attempts'][0]['contract_hash'], previous['contract_hash'])
        self.assertEqual(ComparisonStore(self.root).review('hair'), accepted)
        self.assertEqual(self.store.asset(artifact['id']).read_bytes(), original_bytes)

    def test_new_unaccepted_render_cannot_be_published(self):
        review = self.prepared(approve=True)
        a = self.render()
        self.store.approve('hair', 'pilot', review['contract_hash'], [a['id']])
        b = self.render(value='black', key='black')
        with self.assertRaises(ValueError):
            self.store.approve('hair', 'publish', review['contract_hash'], [b['id']])
        published = self.store.approve('hair', 'publish', review['contract_hash'], [a['id']])
        self.assertEqual(published['published_artifact_ids'], [a['id']])

    def test_wrongbase_hash_posthoc_params_and_symlinks_fail_closed(self):
        review = self.prepared(attr='hair_cut', approve=True, cap=1)
        calls = []
        for params in ({'base_sha256': 'wrong'}, {'mask_sha256': 'wrong'}, {'image_path': str(self.source)}):
            with self.assertRaises(ValueError):
                self.render('hair_cut', 'bob', 'reference_edit', params=params, provider=lambda *args: calls.append(args))
        self.assertEqual(calls, [])
        self.assertEqual(self.store.review('hair'), review)
        link = self.root / 'generated' / 'link.png'
        link.symlink_to(self.source)
        with self.assertRaises(ValueError):
            self.store.set_base('hair', link, 'link')
        with self.assertRaisesRegex(ValueError, 'Reopen'):
            self.store.set_mask('hair', 'hair_color', self.mask)
        self.assertEqual(self.store.review('hair'), review)
        reopened = self.store.reopen('hair', review['contract_hash'], 'Add an independently reviewed pigment footprint')
        self.assertEqual(reopened['state'], 'draft')
        self.assertEqual(reopened['approvals'], [])
        self.assertEqual(reopened['budget'], {'cap': 0, 'used': 0})
        self.assertNotEqual(reopened['contract_hash'], review['contract_hash'])
        self.assertEqual(reopened['history'][-2]['event'], 'operator_reopen')
        self.assertEqual(reopened['history'][-2]['data']['previous']['masks'], review['masks'])
        self.store.set_mask('hair', 'hair_color', self.mask)
        a = self.render(key='local')
        before_chaining = self.store.review('hair')
        with self.assertRaisesRegex(ValueError, 'cannot be chained'):
            self.store.set_base('hair', self.store.asset(a['id']), a['id'])
        self.assertEqual(self.store.review('hair'), before_chaining)
        overlay = self.store.review('hair')['masks']['hair_cut']['overlay_asset_id']
        path = self.store.asset(overlay)
        path.unlink()
        path.symlink_to(self.source)
        self.assertIsNone(self.store.asset(overlay))
        with self.assertRaisesRegex(ValueError, 'overlay is missing or corrupted'):
            self.store.approve('hair', 'contract', self.store.review('hair')['contract_hash'], provider_attempt_cap=1)
        self.assertEqual(self.store.review('hair')['approvals'], [])
        self.assertEqual(self.store.review('hair')['budget']['used'], 0)
        self.assertEqual(calls, [])

    def test_concurrent_provider_budget_and_response_loss_retry(self):
        self.prepared(attr='hair_cut', approve=True, cap=1)
        calls = []
        entered, release = Event(), Event()
        def provider(*args):
            calls.append(args)
            entered.set()
            release.wait(5)
            return base64.b64encode(png(Image.new('RGB', (32, 40), 'red'))).decode(), 'image/png'
        with ThreadPoolExecutor(max_workers=2) as pool:
            pending = pool.submit(self.render, 'hair_cut', 'bob', 'reference_edit', 'one', None, provider)
            self.assertTrue(entered.wait(5))
            with self.assertRaises(ValueError):
                self.render('hair_cut', 'bob', 'reference_edit', 'two', provider=provider)
            with self.assertRaises(ValueError):
                self.render('hair_cut', 'bob', 'reference_edit', 'one', provider=provider)
            release.set()
            result = pending.result(5)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result, self.render('hair_cut', 'bob', 'reference_edit', 'one', provider=provider))
        self.assertEqual(self.store.review('hair')['budget']['used'], 1)

    def test_changed_mask_during_provider_withholds_result(self):
        self.prepared(attr='hair_cut', approve=True, cap=1)
        def provider(*args):
            self.store.set_mask('hair', 'hair_cut', [[.1, .1], [.5, .1], [.5, .7], [.1, .7]])
            return base64.b64encode(png(Image.new('RGB', (32, 40), 'red'))).decode(), 'image/png'
        result = self.render('hair_cut', 'bob', 'reference_edit', provider=provider)
        self.assertEqual(result['receipt']['status'], 'failed')
        self.assertIsNone(result['url'])
        review = self.store.review('hair')
        self.assertEqual(review['artifacts'], [])
        self.assertEqual(review['budget']['used'], 1)

    def test_seed_determinism_and_empty_target_rejection(self):
        self.store.set_base('photography', self.source, 'owned')
        with self.assertRaises(ValueError):
            self.render('grain', 'fine', 'simulated_optics', params={'effect': 'grain', 'amount': 0}, category='photography')
        a = self.render('grain', 'fine', 'simulated_optics', 'a', {'effect': 'grain', 'amount': 10, 'seed': 9}, category='photography')
        b = self.render('grain', 'fine', 'simulated_optics', 'b', {'effect': 'grain', 'amount': 10, 'seed': 9}, category='photography')
        self.assertEqual(a['receipt']['output_sha256'], b['receipt']['output_sha256'])

    def test_provider_alpha_drift_and_valueerror_secret_sanitized(self):
        Image.new('RGBA', (32, 40), (100, 110, 120, 123)).save(self.source, 'PNG')
        self.prepared(attr='hair_cut', approve=True, cap=2)
        def alpha(*args):
            return base64.b64encode(png(Image.new('RGBA', (32, 40), (250, 20, 20, 0)))).decode(), 'image/png'
        result = self.render('hair_cut', 'bob', 'reference_edit', 'alpha', provider=alpha)
        self.assertEqual(result['receipt']['status'], 'failed')
        def secret(*args):
            raise ValueError('private-secret-token')
        result = self.render('hair_cut', 'bob', 'reference_edit', 'secret', provider=secret)
        self.assertNotIn('private-secret-token', json.dumps(result))

    def test_unsupported_params_and_local_motion_claims_rejected(self):
        self.prepared()
        with self.assertRaises(ValueError):
            self.render(params={'pretend_slider': 50})
        with self.assertRaises(ValueError):
            self.render(params={'crop': [0, 0, .5, .5]})
        self.lib['categories'][1]['attributes'][0].update(id='motion', preview_scope='global')
        self.store.list_categories(self.lib)
        self.store.set_base('photography', self.source, 'owned')
        with self.assertRaises(ValueError):
            self.render('motion', 'fine', 'simulated_optics', params={'effect': 'motion_blur', 'moving_region': 'all'}, category='photography')

    def test_reencoded_output_cannot_be_substituted_for_original(self):
        self.prepared()
        artifact = self.render()
        copied = self.root / 'generated' / 'copied-output.png'
        with Image.open(self.store.asset(artifact['id'])) as image:
            image.save(copied, 'PNG', compress_level=0)
        self.assertNotEqual(copied.read_bytes(), self.store.asset(artifact['id']).read_bytes())
        with self.assertRaises(ValueError):
            self.store.set_base('hair', copied, 'pretend-original')

    def test_decoding_bounded_before_loading_and_traversal(self):
        with patch('comparisons.MAX_PIXELS', 100):
            with self.assertRaises(ValueError):
                self.store.set_base('hair', self.source, 'owned')
        for image_id in ('../owned.png', '../' + 'a' * 32, 'a' * 32 + '.jpg', None):
            self.assertIsNone(self.store.asset(image_id))

    def test_receipt_records_default_optical_parameters_and_disallows_whole_hair(self):
        self.store.set_base('photography', self.source, 'owned')
        artifact = self.render('grain', 'fine', 'simulated_optics', params={'effect': 'grain'}, category='photography')
        self.assertEqual(artifact['receipt']['params']['seed'], 0)
        self.assertEqual(artifact['receipt']['params']['amount'], 10)
        self.lib['categories'][0]['attributes'][0]['preview_scope'] = 'global'
        self.store.list_categories(self.lib)
        self.store.set_base('hair', self.source, 'owned')
        with self.assertRaises(ValueError):
            self.render()


    def test_empty_polygon_removes_saved_mask_and_invalidates_approval(self):
        self.prepared(approve=True, cap=1)
        previous = self.store.review('hair')
        saved_mask = previous['masks']['hair_color']
        with self.assertRaisesRegex(ValueError, 'Reopen'):
            self.store.set_mask('hair', 'hair_color', [])
        self.assertEqual(self.store.review('hair'), previous)
        reopened = self.store.reopen('hair', previous['contract_hash'], 'Explicitly remove the reviewed footprint')
        self.assertEqual(reopened['state'], 'draft')
        self.assertEqual(reopened['approvals'], [])
        self.assertEqual(reopened['masks'], previous['masks'])
        self.assertNotEqual(reopened['contract_hash'], previous['contract_hash'])
        self.assertEqual(reopened['history'][-2]['event'], 'operator_reopen')
        self.assertEqual(reopened['history'][-2]['data']['previous']['approvals'], previous['approvals'])
        removed = self.store.set_mask('hair', 'hair_color', [])
        self.assertNotIn('hair_color', removed['masks'])
        self.assertEqual(removed['state'], 'draft')
        self.assertNotEqual(removed['contract_hash'], previous['contract_hash'])
        self.assertNotEqual(removed['contract_hash'], reopened['contract_hash'])
        self.assertEqual(removed['budget']['used'], previous['budget']['used'])
        self.assertEqual(removed['budget']['cap'], 0)
        self.assertEqual(removed['approvals'], [])
        self.assertEqual(removed['history'][-2]['event'], 'mask_removed_previous')
        self.assertEqual(removed['history'][-2]['data']['masks']['hair_color'], saved_mask)
        self.assertIsNotNone(self.store.asset(saved_mask['asset_id']))
        self.assertIsNotNone(self.store.asset(saved_mask['overlay_asset_id']))
        with self.assertRaisesRegex(ValueError, 'Stale or incorrect'):
            self.store.approve('hair', 'contract', previous['contract_hash'], provider_attempt_cap=1)
        with self.assertRaisesRegex(ValueError, 'at least one target mask'):
            self.store.approve('hair', 'contract', removed['contract_hash'], provider_attempt_cap=1)
        with self.assertRaisesRegex(ValueError, 'no independently drawn mask'):
            self.render()
        with self.assertRaisesRegex(ValueError, 'Unknown comparison attribute'):
            self.store.set_mask('hair', 'unknown_attribute', [])
        self.assertEqual(self.store.review('hair', attribute_id='hair_color'), removed)


if __name__ == '__main__':
    unittest.main()
