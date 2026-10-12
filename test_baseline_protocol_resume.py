"""Strict real-catalog baseline attestations through the socket-free HTTP API.

Every attestation and deliberate invalid record is an isolated simulated-human
fixture. None is an actual operator approval or evidence about image contents.
"""
import copy
import unittest
from urllib.parse import urlencode

import test_resume_backend as fixtures


class BaselineProtocolResumeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.ResumeBackendIntegrationTests.setUpClass()

    def setUp(self):
        self.f = fixtures.ResumeBackendIntegrationTests('runTest')
        self.addCleanup(self.f.doCleanups)
        self.f.setUp()
        self.addCleanup(self.f.tearDown)

    def assert_unspent(self, category, attribute):
        review = self.f.review(category, attribute)
        self.assertEqual(review['budget']['used'], 0)
        self.assertEqual(review['cycle']['used'], 0)
        self.assertEqual(review['attempts'], [])
        with self.f.app.comparisons._transaction(read_only=True) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM comparison_requests').fetchone()[0], 0)
        self.f.edits.assert_not_called()
        self.f.generation.assert_not_called()

    def test_missing_wrong_extra_confirmations_reject_attribute_and_group_before_reservation(self):
        f = self.f
        for category, attribute in [('hair', 'hair_cut'), ('hair', 'hair_color'),
                                    ('eyes', 'eye_color'), ('photography', 'grain')]:
            review = f.review(category, attribute)
            requirements = review['baseline_requirements']
            self.assertTrue(requirements)
            for targeting in ({'attribute_id': attribute}, {'group': review['group']},
                              {'attribute_id': attribute, 'group': review['group']}):
                invalid = ({}, {'baseline_confirmations': None}, {'baseline_confirmations': []},
                           {'baseline_confirmations': ['MOCK wrong attestation']},
                           {'baseline_confirmations': requirements + ['MOCK extra attestation']},
                           {'baseline_confirmations': requirements[:-1]},
                           {'baseline_confirmations': requirements + [requirements[0]]})
                for confirmations in invalid:
                    with self.subTest(attribute=attribute, targeting=targeting, confirmations=confirmations):
                        f.post(category, 'base', {'image_id': f.owned['id'], **targeting, **confirmations}, status=400)
                        self.assertEqual(f.review(category, attribute), review)
                        f.post(category, 'approve', {**targeting, 'stage': 'contract',
                            'expected_contract_hash': review['contract_hash'], 'provider_attempt_cap': 3,
                            'approval_note': 'MOCK fixture must not bypass absent baseline'}, status=400)
                        value = f.app.catalog.attributes[attribute]['values'][-1]['id']
                        f.render('denied-' + attribute, category, attribute, value, status=400)
                        self.assert_unspent(category, attribute)

    def test_explicit_group_accepts_only_review_requirements_and_persists_attestation(self):
        f = self.f
        review = f.review()
        requirements = list(review['baseline_requirements'])
        base = f.post('hair', 'base', {'group': review['group'], 'image_id': f.owned['id'],
                                     'baseline_confirmations': requirements})
        self.assertEqual(base['group'], review['group'])
        self.assertEqual(base['baseline']['baseline_confirmations'], requirements)
        self.assertEqual(base['baseline']['confirmation_basis'], 'operator_attestation_not_machine_proof')
        self.assertTrue(base['baseline_integrity'])
        self.assertIsNone(f.review(attribute='hair_color')['baseline'])
        f.restart()
        self.assertEqual(f.review(), base)
        self.assert_unspent('hair', 'hair_cut')

    def test_category_base_requires_full_union_not_one_groups_attestation(self):
        f = self.f
        category = f.request('GET', '/api/comparisons/hair')
        required = category['baseline_requirements']
        declared = list(dict.fromkeys(r for g in category['groups'].values() for r in g['baseline_requirements']))
        self.assertEqual(required, declared)
        cut = f.review()
        self.assertTrue(set(cut['baseline_requirements']) < set(required))
        for confirmations in ({}, {'baseline_confirmations': cut['baseline_requirements']},
                              {'baseline_confirmations': required + ['MOCK extra attestation']}):
            with self.subTest(confirmations=confirmations):
                f.post('hair', 'base', {'image_id': f.owned['id'], **confirmations}, status=400)
                self.assertEqual(f.request('GET', '/api/comparisons/hair'), category)
                self.assert_unspent('hair', 'hair_cut')
        # Compatibility baselines remain available only after the entire union
        # is explicitly attested in this isolated simulated-human fixture.
        base = f.post('hair', 'base', {'image_id': f.owned['id'], 'baseline_confirmations': list(required)})
        self.assertTrue(base['compatibility_view'])
        self.assertEqual(base['baseline']['baseline_confirmations'], required)
        fallback = f.review()
        self.assertIsNone(fallback['group'])
        self.assertEqual(fallback['baseline_requirements'], required)
        explicit = f.request('GET', '/api/comparisons/hair?' + urlencode({'group': cut['group']}))
        self.assertIsNone(explicit['baseline'])
        self.assert_unspent('hair', 'hair_cut')

    def test_category_fallback_cannot_approve_or_render_without_declared_attestation_after_restart(self):
        f = self.f
        category = f.request('GET', '/api/comparisons/hair')
        requirements = category['baseline_requirements']
        cut = f.review()
        missing = cut['baseline_requirements'][0]
        f.post('hair', 'base', {'image_id': f.owned['id'], 'baseline_confirmations': list(requirements)})
        # Deliberately damage only the private compatibility record. Drawing a
        # real mask recomputes its contract, isolating attestation enforcement
        # from a stale-hash denial. No guard or approval is mocked.
        with f.app.comparisons._transaction() as db:
            record = copy.deepcopy(f.app.comparisons._get(db, 'hair'))
            record['baseline']['baseline_confirmations'].remove(missing)
            f.app.comparisons._save(db, record)
        review = f.post('hair', 'mask', {'attribute_id': 'hair_cut', 'polygon': f.polygon})
        self.assertIsNone(review['group'])
        self.assertFalse(review['baseline_integrity'])
        self.assertIn(missing, review['baseline_requirements'])
        for restarted in (False, True):
            with self.subTest(restarted=restarted):
                if restarted:
                    f.restart()
                review = f.review()
                error = f.post('hair', 'approve', {'attribute_id': 'hair_cut', 'stage': 'contract',
                    'expected_contract_hash': review['contract_hash'], 'provider_attempt_cap': 3,
                    'approval_note': 'MOCK category fallback cannot waive human gate'}, status=400)
                self.assertIn('Exact operator baseline confirmations', error['error'])
                error = f.render('unattested-fallback', status=400)
                self.assertIn('Exact operator baseline confirmations', error['error'])
                self.assertEqual(f.review(), review)
                self.assert_unspent('hair', 'hair_cut')


if __name__ == '__main__':
    unittest.main()
