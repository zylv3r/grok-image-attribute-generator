"""Isolated integrity regressions; all providers mocked, no sockets or live data."""
import copy
import io
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from PIL import Image
import comparisons
import server
import test_server_v2
import test_workflow_security_v2


def png(color, size=(32, 40)):
    stream = io.BytesIO()
    Image.new('RGBA', size, color).save(stream, 'PNG')
    return stream.getvalue()


def replace(path, raw):
    staged = path.with_suffix('.replacement')
    staged.write_bytes(raw)
    os.replace(staged, path)


class SnapshotIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.f = test_workflow_security_v2.WorkflowSecurityTests()
        self.f.setUp()
        self.addCleanup(self.f.tearDown)

    def test_native_replacement_at_actual_read_consumes_nothing(self):
        f = self.f
        r = f.prepare('hair_cut', 1)
        path = f.store.asset(r['baseline']['asset_id'])
        reader = comparisons._read_file
        def tamper(target):
            if Path(target) == path:
                replace(path, png('blue'))
            return reader(target)
        with patch.object(comparisons, '_read_file', side_effect=tamper):
            with self.assertRaises(ValueError):
                f.render('hair_cut', 'preflight-tamper')
        f.provider.assert_not_called()
        current = f.store.review('hair')
        self.assertEqual(current['budget']['used'], 0)
        self.assertEqual(current['attempts'], [])

    def test_native_mutation_after_snapshot_never_charges_wrong_bytes(self):
        f = self.f
        r = f.prepare('hair_cut', 1)
        path = f.store.asset(r['baseline']['asset_id'])
        original = path.read_bytes()
        reader = comparisons._read_file
        replaced = False
        def tamper_after_read(target):
            nonlocal replaced
            raw = reader(target)
            if Path(target) == path and not replaced:
                replaced = True
                replace(path, png('blue'))
            return raw
        with patch.object(comparisons, '_read_file', side_effect=tamper_after_read):
            try:
                f.render('hair_cut', 'pinned-snapshot')
            except ValueError:
                pass  # Refusal before reservation is also safe.
        self.assertTrue(replaced)
        if f.provider.called:
            self.assertEqual(f.provider.call_args.args[1], original)
        else:
            self.assertEqual(f.store.review('hair')['budget']['used'], 0)

    def test_mutation_after_complete_preflight_uses_pinned_original(self):
        f = self.f
        r = f.prepare('hair_cut', 1)
        path = f.store.asset(r['baseline']['asset_id'])
        original = path.read_bytes()
        preflight = f.store._integrity
        def tamper_after_preflight(db, record):
            snapshots = preflight(db, record)
            replace(path, png('blue'))
            return snapshots
        with patch.object(f.store, '_integrity', side_effect=tamper_after_preflight):
            a = f.render('hair_cut', 'post-snapshot')
        f.provider.assert_called_once()
        self.assertEqual(f.provider.call_args.args[1], original)
        self.assertEqual(a['receipt']['status'], 'staged')
        self.assertEqual(a['receipt']['base_sha256'], comparisons._hash(original))
        self.assertEqual(f.store.review('hair')['budget']['used'], 1)
        self.assertFalse(f.store.review('hair')['baseline_integrity'])

    def test_safe_read_bytes_checks_same_snapshot_sha_dimensions_and_symlinks(self):
        f = self.f
        r = f.prepare()
        ident = r['baseline']['asset_id']
        path = f.store.asset(ident)
        original = path.read_bytes()
        self.assertEqual(f.store.read_bytes(ident + '.png'), original)
        reader = comparisons._read_file
        def symlink_at_read(target):
            if Path(target) == path:
                path.unlink()
                path.symlink_to(f.source)
            return reader(target)
        with patch.object(comparisons, '_read_file', side_effect=symlink_at_read):
            self.assertIsNone(f.store.read_bytes(ident))
        path.unlink()
        path.write_bytes(original)
        with f.store._transaction() as db:
            db.execute('UPDATE comparison_assets SET width=width+1 WHERE id=?', (ident,))
        self.assertIsNone(f.store.read_bytes(ident))

    def test_every_approval_stage_binds_base_masks_overlay_hash_and_cycle(self):
        f = self.f
        r = f.prepare()
        a = f.render()
        r = f.accept(r, a)
        f.store.approve('hair', 'publish', r['contract_hash'], [a['id']])
        with f.store._transaction() as db:
            original = copy.deepcopy(f.store._get(db, 'hair'))
        self.assertTrue(f.store.publication_valid('hair', a['id']))
        for stage in ('contract', 'pilot', 'publish'):
            for field in ('baseline_sha256', 'mask_hashes', 'overlay_hashes', 'contract_hash', 'cycle_id'):
                with self.subTest(stage=stage, field=field):
                    changed = copy.deepcopy(original)
                    approval = next(v for v in changed['approvals'] if v['stage'] == stage)
                    approval[field] = ({'hair_color': '0' * 64} if field.endswith('hashes') else
                                       999 if field == 'cycle_id' else '0' * 64)
                    with f.store._transaction() as db:
                        f.store._save(db, changed)
                    self.assertFalse(f.store.publication_valid('hair', a['id']))
        with f.store._transaction() as db:
            f.store._save(db, original)
        self.assertTrue(f.store.publication_valid('hair', a['id']))

    def test_corrupt_contract_approval_blocks_native_before_reservation(self):
        f = self.f
        f.prepare('hair_cut', 1)
        with f.store._transaction() as db:
            record = f.store._get(db, 'hair')
            record['approvals'][0]['overlay_hashes']['hair_cut'] = '0' * 64
            f.store._save(db, record)
        with self.assertRaises(ValueError):
            f.render('hair_cut', 'corrupt-contract')
        f.provider.assert_not_called()
        self.assertEqual(f.store.review('hair')['budget']['used'], 0)

    def test_corrupt_expansion_approval_blocks_native_before_reservation(self):
        f = self.f
        r = f.prepare('hair_cut', 1)
        a = f.render('hair_cut')
        r = f.accept(r, a)
        f.store.approve('hair', 'expansion', r['contract_hash'], provider_attempt_cap=1,
                        approval_note='One further reviewed candidate')
        with f.store._transaction() as db:
            record = f.store._get(db, 'hair')
            record['approvals'][-1]['overlay_hashes']['hair_cut'] = '0' * 64
            f.store._save(db, record)
        with self.assertRaises(ValueError):
            f.render('hair_cut', 'bad-expansion')
        self.assertEqual(f.provider.call_count, 1)
        self.assertEqual(f.store.review('hair')['budget']['used'], 1)


class HTTPIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.f = test_server_v2.ComparisonHTTPTests()
        self.f.setUp()
        self.addCleanup(self.f.tearDown)

    def test_atomic_replacement_at_http_open_is_not_served(self):
        f = self.f
        r = f.base()
        path = f.app.comparisons.asset(r['baseline']['asset_id'])
        original = path.read_bytes()
        reader = f.app._preview_file
        def tamper(path, limit):
            replace(path, png('red', (90, 160)))
            return reader(path, limit)
        for method in ('GET', 'HEAD'):
            path.write_bytes(original)
            with self.subTest(method=method), patch.object(f.app, '_preview_file', side_effect=tamper):
                self.assertEqual(f.request(method, r['baseline']['url'])[0], 404)

    def test_base_http_requires_exact_explicit_confirmation_list(self):
        f = self.f
        requirement = 'Operator reviewed close eye view'
        attr = f.app.catalog.library['categories'][0]['attributes'][0]
        attr['preview_contract'] = {'baseline_requirements': [requirement]}
        f.app.comparisons.list_categories(f.app.catalog.library)
        body = {'image_id': f.image['id'], 'attribute_id': attr['id']}
        for confirmations in (None, 'yes', {}, [], [requirement, requirement], ['other']):
            with self.subTest(confirmations=confirmations):
                self.assertEqual(f.post('base', {**body, 'baseline_confirmations': confirmations})[0], 400)
        self.assertEqual(f.post('base', body)[0], 400)
        status, r, _ = f.post('base', {**body, 'baseline_confirmations': [requirement]})
        self.assertEqual(status, 200, r)
        self.assertEqual(r['baseline_requirements'], [requirement])
        self.assertEqual(r['baseline']['baseline_confirmations'], [requirement])
        f.edits.assert_not_called()

    def test_corrupt_contract_approval_withholds_library_ready(self):
        f = self.f
        f.base()
        r = f.mask()
        self.assertEqual(f.post('approve', {'stage': 'contract', 'expected_contract_hash': r['contract_hash']})[0], 200)
        status, a, _ = f.post('preview', {'attribute_id': 'color', 'value_id': 'blue',
                             'method': 'masked_recolor', 'request_key': 'approval-proof'})
        self.assertEqual(status, 200)
        for stage in ('pilot', 'publish'):
            status, r, _ = f.post('approve', {'stage': stage, 'expected_contract_hash': r['contract_hash'], 'artifact_ids': [a['id']]})
            self.assertEqual(status, 200)
        with f.app.comparisons._transaction() as db:
            record = f.app.comparisons._get(db, 'test')
            record['approvals'][0]['baseline_sha256'] = '0' * 64
            f.app.comparisons._save(db, record)
        status, lib, _ = f.request('GET', '/api/library')
        self.assertEqual(status, 200)
        value = next(v for c in lib['categories'] for attr in c['attributes'] if attr['id'] == 'color'
                     for v in attr['values'] if v['id'] == 'blue')
        self.assertEqual(value['thumbnail_status'], 'review_required')
        f.edits.assert_not_called()


class GroupContractTests(unittest.TestCase):
    def setUp(self):
        self.f = test_workflow_security_v2.WorkflowSecurityTests()
        self.f.setUp()
        self.addCleanup(self.f.tearDown)
        self.contract = {'locked_fields': ['identity', 'camera', 'crop'],
                         'allowed_changes': ['pose and gaze consequences'],
                         'baseline_requirements': ['Operator reviewed neutral medium-brown hair geometry']}
        self.attr = self.f.lib['categories'][0]['attributes'][1]
        self.assertEqual(self.attr['id'], 'hair_cut')
        self.attr['preview_contract'] = copy.deepcopy(self.contract)
        self.f.store.list_categories(self.f.lib)

    def test_group_derives_contract_and_exposes_required_attestations(self):
        r = self.f.store.review('hair', attribute_id='hair_cut')
        self.assertEqual(r['locked_fields'], self.contract['locked_fields'])
        self.assertEqual(r['allowed_changes'], self.contract['allowed_changes'])
        self.assertEqual(r['baseline_requirements'], self.contract['baseline_requirements'])

    def test_baseline_requires_exact_operator_confirmations(self):
        f = self.f
        for confirmations in (None, [], ['wrong'], self.contract['baseline_requirements'] * 2):
            with self.subTest(confirmations=confirmations), self.assertRaises(ValueError):
                f.store.set_base('hair', f.source, 'owned', attribute_id='hair_cut', baseline_confirmations=confirmations)
        r = f.store.set_base('hair', f.source, 'owned', attribute_id='hair_cut',
                             baseline_confirmations=self.contract['baseline_requirements'])
        self.assertEqual(r['baseline']['baseline_confirmations'], self.contract['baseline_requirements'])
        self.assertEqual(r['baseline']['confirmation_basis'], 'operator_attestation_not_machine_proof')

    def test_reference_prompt_receipt_bind_actual_locks_allowances_and_recipe(self):
        f = self.f
        self.attr['values'][0]['recipe'] = {'selections': {'pose': ['turn']}}
        f.store.list_categories(f.lib)
        f.store.set_base('hair', f.source, 'owned', attribute_id='hair_cut',
                         baseline_confirmations=self.contract['baseline_requirements'])
        r = f.store.set_mask('hair', 'hair_cut', f.poly)
        r = f.store.approve('hair', 'contract', r['contract_hash'], provider_attempt_cap=1, attribute_id='hair_cut')
        a = f.render('hair_cut', 'contract-prompt')
        self.assertEqual(a['receipt']['status'], 'staged')
        self.assertEqual(a['receipt']['target_contract'], self.contract)
        self.assertEqual(a['receipt']['recipe_components'], {'pose': ['turn']})
        prompt = f.provider.call_args.args[0]
        self.assertIn(comparisons._json(self.contract['locked_fields']), prompt)
        self.assertIn(comparisons._json(self.contract['allowed_changes']), prompt)
        self.assertNotIn('wardrobe, pose, gaze', prompt)
        self.assertIn('turn', prompt)

    def test_baseline_confirmation_tamper_blocks_approval_and_native(self):
        f = self.f
        f.store.set_base('hair', f.source, 'owned', attribute_id='hair_cut',
                         baseline_confirmations=self.contract['baseline_requirements'])
        r = f.store.set_mask('hair', 'hair_cut', f.poly)
        r = f.store.approve('hair', 'contract', r['contract_hash'], provider_attempt_cap=1, attribute_id='hair_cut')
        with f.store._transaction() as db:
            record = f.store._get(db, 'hair::hair:hair_cut')
            record['baseline']['baseline_confirmations'] = []
            record['contract_hash'] = f.store._contract(record)  # Even a rehashed corrupt attestation fails.
            f.store._save(db, record)
        with self.assertRaises(ValueError):
            f.store.approve('hair', 'contract', record['contract_hash'], attribute_id='hair_cut')
        with self.assertRaises(ValueError):
            f.render('hair_cut', 'invalid-attestation')
        f.provider.assert_not_called()
        self.assertEqual(f.store.review('hair', attribute_id='hair_cut')['budget']['used'], 0)

    def test_incompatible_shared_native_contract_rejected(self):
        f = self.f
        other = copy.deepcopy(self.attr)
        other['id'] = 'incompatible'
        other['preview_contract']['locked_fields'] = ['identity', 'pose']
        f.lib['categories'][0]['attributes'].append(other)
        with self.assertRaisesRegex(ValueError, '[Ii]ncompatible|shared'):
            f.store.list_categories(f.lib)

    def test_incompatible_locks_across_shared_methods_rejected(self):
        f = self.f
        other = f.lib['categories'][0]['attributes'][0]
        other['comparison_group'] = self.attr['comparison_group']
        other['preview_contract'] = {'locked_fields': ['identity', 'pose'],
                                     'allowed_changes': ['hair pigment']}
        with self.assertRaisesRegex(ValueError, '[Ii]ncompatible|shared'):
            f.store.list_categories(f.lib)

    def test_baseline_requirements_bind_definition_hash(self):
        f = self.f
        before = f.store.review('hair', attribute_id='hair_cut')
        self.attr['preview_contract']['baseline_requirements'].append('Operator reviewed close eye view')
        f.store.list_categories(f.lib)
        after = f.store.review('hair', attribute_id='hair_cut')
        self.assertNotEqual(before['contract_hash'], after['contract_hash'])
        self.assertEqual(after['baseline_requirements'], self.attr['preview_contract']['baseline_requirements'])


if __name__ == '__main__':
    unittest.main()
