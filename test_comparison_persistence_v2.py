"""Targeted publication survives a real Application restart in a private fixture."""
import base64
import hashlib
import io
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import Mock

from PIL import Image

import server
from gallery import save_image


class ComparisonPersistenceTests(unittest.TestCase):
    def test_approved_published_category_survives_application_restart_and_library_reads(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(server.ROOT / 'catalog', root / 'catalog')
            shutil.copyfile(server.ROOT / 'library.json', root / 'library.json')
            provider = Mock(side_effect=AssertionError('No provider call allowed'))
            app = server.Application(root, provider=provider, edit_provider=provider)
            self.assertIsNotNone(app.comparisons)
            target = {'attribute_id': 'hair_color'}
            try:
                image = Image.new('RGB', (64, 80))
                image.putdata([(50 + x * 2, 40 + y * 2, 80) for y in range(80) for x in range(64)])
                stream = io.BytesIO()
                image.save(stream, 'PNG')
                record = save_image(base64.b64encode(stream.getvalue()).decode(), app.store.output_dir, '4:5')
                owned = app.store.add_image(record, 'Isolated restart fixture', {})
                source = app.store.owned_image(owned['id'])
                source_bytes = source.read_bytes()
                review = app.comparisons.review('hair', **target)
                # Simulated-human fixture attestation; never actual operator approval.
                app.comparison_post('hair', 'base', {**target, 'image_id': owned['id'],
                    'baseline_confirmations': list(review['baseline_requirements'])})
                review = app.comparison_post('hair', 'mask', {**target,
                    'polygon': [[.1, .1], [.5, .1], [.5, .5], [.1, .5]]})
                review = app.comparison_post('hair', 'approve', {**target, 'stage': 'contract',
                    'expected_contract_hash': review['contract_hash'], 'provider_attempt_cap': 0,
                    'approval_note': 'QA isolated simulated-human contract review'})
                artifact = app.comparison_post('hair', 'preview', {**target, 'value_id': 'copper_red',
                    'method': 'masked_recolor', 'params': {}, 'request_key': 'qa-restart'})
                for stage in ('pilot', 'publish'):
                    review = app.comparison_post('hair', 'approve', {**target, 'stage': stage,
                        'expected_contract_hash': review['contract_hash'], 'artifact_ids': [artifact['id']],
                        'approval_note': 'QA isolated simulated-human artifact review'})
                before = app.comparisons.review('hair', **target)
                self.assertEqual(before['state'], 'published')
                self.assertEqual(before['group'], 'hair:hair_color')
                self.assertEqual(before['baseline']['baseline_confirmations'], before['baseline_requirements'])
                self.assertEqual([a['stage'] for a in before['approvals']], ['contract', 'pilot', 'publish'])
                mask = before['masks']['hair_color']
                snapshots = {ident: app.comparisons.asset(ident).read_bytes() for ident in (
                    before['baseline']['asset_id'], mask['asset_id'], mask['overlay_asset_id'], artifact['id'])}
                approval = before['approvals'][-1]
                self.assertEqual(approval['baseline_sha256'], before['baseline']['sha256'])
                self.assertEqual(approval['mask_hashes']['hair_color'], mask['sha256'])
                self.assertEqual(approval['overlay_hashes']['hair_color'], mask['overlay_sha256'])
                self.assertEqual(approval['artifact_hashes'][artifact['id']], hashlib.sha256(snapshots[artifact['id']]).hexdigest())
            finally:
                app.close()
            reopened = server.Application(root, provider=provider, edit_provider=provider)
            try:
                self.assertEqual(reopened.comparisons.review('hair', **target), before,
                                 'Restart must preserve the entire targeted published review')
                library, _, _ = reopened.thumbnail_library()
                value = next(v for c in library['categories'] for a in c['attributes']
                             if a['id'] == 'hair_color' for v in a['values'] if v['id'] == 'copper_red')
                self.assertEqual(value['thumbnail_source'], 'approved_comparison')
                self.assertEqual(value['thumbnail_url'], artifact['url'])
                self.assertEqual(reopened.comparisons.review('hair', **target), before)
                category = reopened.comparisons.review('hair')
                self.assertEqual(category['groups']['hair:hair_color'], before)
                self.assertFalse(category['compatibility_view'])
                self.assertIsNone(category['baseline'])
                other = reopened.comparisons.review('hair', attribute_id='hair_cut')
                self.assertEqual(other['state'], 'draft')
                self.assertIsNone(other['baseline'])
                for ident, raw in snapshots.items():
                    self.assertEqual(reopened.comparisons.asset(ident).read_bytes(), raw)
                self.assertEqual(source.read_bytes(), source_bytes)
                provider.assert_not_called()
            finally:
                reopened.close()


if __name__ == '__main__':
    unittest.main()
