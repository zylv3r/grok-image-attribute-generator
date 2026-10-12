"""Resume verification: real Application/ComparisonStore/HTTP, MOCK providers only.

All databases, references, approvals and tampering are isolated TemporaryDirectory
fixtures. The checked-out catalog is read-only. No runtime DB/config/credential
reads, real vendor requests, or approvals of production masks occur here.
"""
import base64
import copy
import hashlib
import http.client
import io
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from urllib.parse import urlencode

from PIL import Image

import catalog_v2
import server
from gallery import save_image


def png(image):
    stream = io.BytesIO()
    image.save(stream, 'PNG')
    return stream.getvalue()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class HTTPByteTransport:
    """Raw HTTP bytes through the real parser; sandbox forbids socket creation."""
    def __init__(self, raw):
        self.incoming = io.BytesIO(raw)
        self.outgoing = io.BytesIO()

    def makefile(self, mode, *args):
        return self.incoming

    def sendall(self, raw):
        self.outgoing.write(raw)

    def settimeout(self, timeout):
        pass


class ResumeBackendIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog_bundle = catalog_v2.load_bundle(Path(__file__).resolve().parent)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='resume-backend-MOCK-')
        self.root = Path(self.tmp.name)
        self.bundle = copy.deepcopy(self.catalog_bundle)
        self.generation = Mock(side_effect=AssertionError('MOCK: unexpected generation'))
        self.expected_generations = 0
        self.edits = Mock(side_effect=self.mock_edit)
        # Fail closed even if an application regression drops the supplied mocks.
        self.native_generation = patch.object(server, 'generate_native_image', side_effect=AssertionError('Real provider forbidden'))
        self.native_edit = patch.object(server, 'edit_native_image', side_effect=AssertionError('Real provider forbidden'))
        self.native_generation.start()
        self.native_edit.start()
        self.addCleanup(self.native_generation.stop)
        self.addCleanup(self.native_edit.stop)
        self.addCleanup(self.tmp.cleanup)
        self.app = None
        self.httpd = None
        self.addCleanup(self.stop)
        self.start()
        image = Image.new('RGB', (64, 80))
        image.putdata([(50 + x * 2, 40 + y * 2, 80) for y in range(80) for x in range(64)])
        record = save_image(base64.b64encode(png(image)).decode(), self.app.store.output_dir, '4:5')
        self.owned = self.app.store.add_image(record, 'MOCK isolated adult-woman declaration fixture', {})
        self.source = self.app.store.owned_image(self.owned['id'])
        self.source_bytes = self.source.read_bytes()
        self.polygon = [[.1, .1], [.5, .1], [.5, .7], [.1, .7]]

    def mock_edit(self, prompt, raw, mime, aspect):
        """MOCK provider intentionally drifts everywhere; engine must composite."""
        with Image.open(io.BytesIO(raw)) as reference:
            image = Image.new('RGBA', reference.size, (230, 20, 30, 255))
            image.putalpha(reference.convert('RGBA').getchannel('A'))
        return base64.b64encode(png(image)).decode(), 'image/png'

    def start(self):
        self.app = server.Application(self.root, catalog=server.Catalog(self.bundle['library'], self.bundle),
                                      provider=self.generation, edit_provider=self.edits)
        self.httpd = SimpleNamespace(app=self.app, server_port=8123)
        self.origin = 'http://127.0.0.1:' + str(self.httpd.server_port)

    def stop(self):
        if self.httpd:
            self.httpd = None
        if self.app:
            self.app.close()
            self.app = None

    def restart(self):
        self.stop()
        self.start()

    def tearDown(self):
        try:
            self.stop()
            self.assertEqual(self.generation.call_count, self.expected_generations)
        finally:
            self.tmp.cleanup()

    def request(self, method, path, body=None, *, origin=True, status=200):
        headers = {}
        raw = b''
        if body is not None:
            raw = json.dumps(body).encode()
            headers['Content-Type'] = 'application/json'
            headers['Content-Length'] = str(len(raw))
        if origin:
            headers['Origin'] = self.origin
        headers['Host'] = '127.0.0.1:' + str(self.httpd.server_port)
        wire = f'{method} {path} HTTP/1.1\r\n' + ''.join(f'{key}: {value}\r\n' for key, value in headers.items())
        transport = HTTPByteTransport(wire.encode('ascii') + b'\r\n' + raw)
        server.AppHandler(transport, ('127.0.0.1', 12345), self.httpd)
        response = http.client.HTTPResponse(HTTPByteTransport(transport.outgoing.getvalue()), method=method)
        try:
            response.begin()
            data = response.read()
            self.assertEqual(response.status, status, (path, data[:500]))
            if method != 'HEAD' and response.getheader('Content-Type', '').startswith('application/json'):
                return json.loads(data)
            return data
        finally:
            response.close()

    def post(self, category, action, payload, **kwargs):
        return self.request('POST', '/api/comparisons/' + category + '/' + action, payload, **kwargs)

    def review(self, category='hair', attribute='hair_cut'):
        return self.request('GET', '/api/comparisons/' + category + '?' + urlencode({'attribute_id': attribute}))

    def base(self, category='hair', attribute='hair_cut', **extra):
        review = self.review(category, attribute)
        # Isolated simulated-human fixture attestation, never operator approval.
        body = {'image_id': self.owned['id'], 'attribute_id': attribute, **extra}
        if review['baseline_requirements']:
            body['baseline_confirmations'] = list(review['baseline_requirements'])
        return self.post(category, 'base', body)

    def prepare(self, category='hair', attribute='hair_cut', cap=1):
        self.base(category, attribute)
        review = self.post(category, 'mask', {'attribute_id': attribute, 'polygon': self.polygon})
        return self.approve(review, attribute, 'contract', provider_attempt_cap=cap)

    def approve(self, review, attribute, stage, **extra):
        return self.post(review['category_id'], 'approve', {'attribute_id': attribute, 'stage': stage,
                         'expected_contract_hash': review['contract_hash'],
                         'approval_note': 'MOCK isolated simulated-human fixture review only', **extra})

    def render(self, key, category='hair', attribute='hair_cut', value='blunt_bob', **kwargs):
        method = self.app.catalog.attributes[attribute]['preview_method']
        params = kwargs.pop('params', {})
        return self.post(category, 'preview', {'attribute_id': attribute, 'value_id': value,
                         'method': method, 'request_key': key, 'params': params}, **kwargs)

    def target(self, attribute, value):
        library = self.request('GET', '/api/library')
        return next(v for c in library['categories'] for a in c['attributes'] if a['id'] == attribute
                    for v in a['values'] if v['id'] == value)

    def publish_color(self):
        review = self.prepare(attribute='hair_color', cap=0)
        artifact = self.render('canonical', attribute='hair_color', value='platinum')
        self.approve(review, 'hair_color', 'pilot', artifact_ids=[artifact['id']])
        review = self.approve(review, 'hair_color', 'publish', artifact_ids=[artifact['id']])
        return review, artifact

    def test_group_bases_crops_and_shared_photography_fork_the_original(self):
        color = self.prepare(attribute='hair_color', cap=0)
        artifact = self.render('color', attribute='hair_color', value='platinum')
        cut = self.base(attribute='hair_cut', crop=[0, 0, .5, .5])
        self.assertEqual((cut['baseline']['width'], cut['baseline']['height']), (32, 40))
        self.assertEqual(cut['masks'], {})
        self.assertEqual(self.review(attribute='hair_color')['contract_hash'], color['contract_hash'])
        self.assertEqual(self.review(attribute='hair_color')['artifacts'][0]['id'], artifact['id'])
        scene = self.base('photography', 'grain')
        self.assertEqual(scene['group'], 'photography:same_scene')
        grain = self.render('grain', 'photography', 'grain', 'fine_grain')
        warm = self.render('warm', 'photography', 'white_balance', 'cloudy')
        self.assertEqual(grain['receipt']['contract_hash'], scene['contract_hash'])
        self.assertEqual(warm['receipt']['contract_hash'], scene['contract_hash'])
        self.assertEqual(grain['receipt']['base_sha256'], warm['receipt']['base_sha256'])
        self.assertEqual(self.review('photography', 'white_balance')['baseline'], scene['baseline'])
        self.assertEqual(len(self.review('photography', 'grain')['artifacts']), 2)
        self.request('GET', '/api/comparisons/hair?attribute_id=hair_color&group=hair:hair_cut', status=400)
        self.assertEqual(self.source.read_bytes(), self.source_bytes)
        self.edits.assert_not_called()

    def test_hash_note_bound_reopen_draft_guards_and_archived_publication(self):
        review, artifact = self.publish_color()
        for action, payload in (
            ('base', {'attribute_id': 'hair_color', 'image_id': self.owned['id'],
                      'baseline_confirmations': list(review['baseline_requirements'])}),
            ('mask', {'attribute_id': 'hair_color', 'polygon': []}),
        ):
            self.assertIn('Reopen', self.post('hair', action, payload, status=400)['error'])
        self.render('post-publish', attribute='hair_color', value='platinum', status=400)
        body = {'attribute_id': 'hair_color', 'expected_contract_hash': review['contract_hash'], 'approval_note': 'MOCK isolated revision'}
        self.post('hair', 'reopen', body, origin=False, status=403)
        self.post('hair', 'reopen', {**body, 'expected_contract_hash': '0' * 64}, status=400)
        for note in ('', '   ', None):
            self.post('hair', 'reopen', {**body, 'approval_note': note}, status=400)
        reopened = self.post('hair', 'reopen', body)
        self.assertEqual(reopened['state'], 'draft')
        self.assertNotEqual(reopened['contract_hash'], review['contract_hash'])
        archived = next(h['data'] for h in reopened['history'] if h['event'] == 'operator_reopen')
        self.assertEqual(archived['previous']['published_artifact_ids'], [artifact['id']])
        self.assertEqual(archived['note'], body['approval_note'])
        self.assertEqual(self.request('GET', artifact['url']), self.app.comparisons.asset(artifact['id']).read_bytes())
        self.render('canonical', attribute='hair_color', value='platinum', status=400)
        changed = self.post('hair', 'mask', {'attribute_id': 'hair_color', 'polygon': []})
        self.assertEqual(changed['masks'], {})
        self.assertEqual(changed['published_artifact_ids'], [])
        self.assertEqual(changed['budget']['used'], review['budget']['used'])
        self.edits.assert_not_called()

    def test_explicit_cycles_cap_three_total_failure_and_idempotency_survive_restart(self):
        review = self.prepare(cap=1)
        for cap in (-1, 4, True, 1.5):
            self.post(
                'hair', 'approve', {'attribute_id': 'hair_cut', 'stage': 'expansion', 'expected_contract_hash': review['contract_hash'],
                                    'provider_attempt_cap': cap, 'approval_note': 'MOCK'}, status=400)
        first = self.render('first')
        self.assertFalse(first['accepted'])
        self.assertEqual(self.target('hair_cut', 'blunt_bob')['thumbnail_source'], 'pending')
        self.render('exhausted', status=400)
        expansion = {'attribute_id': 'hair_cut', 'stage': 'expansion', 'expected_contract_hash': review['contract_hash'],
                     'provider_attempt_cap': 2, 'approval_note': 'MOCK explicit next cycle'}
        self.post('hair', 'approve', expansion, status=400)
        self.approve(review, 'hair_cut', 'pilot', artifact_ids=[first['id']])
        self.post('hair', 'approve', {**expansion, 'approval_note': ''}, status=400)
        cycle = self.post('hair', 'approve', expansion)
        self.assertEqual(cycle['cycle'], {'id': 2, 'cap': 2, 'used': 0})
        self.assertEqual(self.render('first'), first)
        self.edits.side_effect = RuntimeError('MOCK-private-error-withheld')
        failed = self.render('failed')
        self.assertEqual(failed['receipt']['status'], 'failed')
        self.assertIsNone(failed['id'])
        self.assertNotIn('MOCK-private-error-withheld', json.dumps(failed))
        self.edits.side_effect = self.mock_edit
        second = self.render('second')
        self.render('exhausted-two', status=400)
        self.approve(cycle, 'hair_cut', 'pilot', artifact_ids=[second['id']])
        cycle = self.post('hair', 'approve', {**expansion, 'provider_attempt_cap': 3})
        third = self.render('third')
        fourth = self.render('fourth')
        fifth = self.render('fifth')
        self.render('exhausted-three', status=400)
        self.assertEqual(cycle['cycle'], {'id': 3, 'cap': 3, 'used': 0})
        before = self.review()
        self.assertEqual(before['budget']['used'], 6)
        self.assertEqual(before['cycle'], {'id': 3, 'cap': 3, 'used': 3})
        self.assertEqual(len(before['attempts']), 6)
        self.restart()
        self.assertEqual(self.review(), before)
        for key, expected in (('first', first), ('failed', failed), ('second', second), ('third', third), ('fourth', fourth), ('fifth', fifth)):
            self.assertEqual(self.render(key), expected)
        self.render('first', value='long_bob', status=400)
        self.assertEqual(self.edits.call_count, 6)
        for call in self.edits.call_args_list:
            self.assertEqual(call.args[1], self.app.comparisons.asset(before['baseline']['asset_id']).read_bytes())

    def test_native_preflight_and_provider_pixels_obey_original_and_footprint_locks(self):
        review = self.prepare(cap=1)
        for params in ({'base_sha256': '0' * 64}, {'mask_sha256': '0' * 64},
                       {'nested': {'image_url': 'https://MOCK.invalid/source'}}, {'resize': [16, 16]}):
            self.render('preflight', params=params, status=400)
        self.post('hair', 'mask', {'attribute_id': 'hair_cut', 'polygon': []}, status=400)
        self.post('hair', 'base', {'attribute_id': 'hair_cut', 'image_id': self.owned['id']}, status=400)
        self.assertEqual(self.review()['attempts'], [])
        self.assertEqual(self.review()['budget']['used'], 0)
        self.edits.assert_not_called()
        artifact = self.render('valid-native')
        receipt = artifact['receipt']
        self.assertEqual(receipt['status'], 'staged')
        self.assertTrue(receipt['provider_attempt_reserved'])
        self.assertEqual(receipt['base_sha256'], review['baseline']['sha256'])
        self.assertEqual(receipt['mask_overlay_sha256'], review['masks']['hair_cut']['overlay_sha256'])
        self.assertEqual(receipt['outside_delta'], 0)
        self.assertGreater(receipt['provider_outside_changed_pixels'], 0)
        self.assertGreater(receipt['inside_change']['changed_pixels'], 0)
        self.assertEqual(receipt['locked_params']['dimensions'], [64, 80])
        base_raw = self.request('GET', review['baseline']['url'])
        self.assertEqual(self.edits.call_args.args[1:], (base_raw, 'image/png', '4:5'))
        with Image.open(io.BytesIO(base_raw)) as base, Image.open(io.BytesIO(self.request('GET', artifact['url']))) as output, Image.open(self.app.comparisons.asset(review['masks']['hair_cut']['asset_id'])) as mask:
            original, result, footprint = base.convert('RGBA'), output.convert('RGBA'), mask.convert('L')
            self.assertEqual(original.size, result.size)
            self.assertEqual(original.getchannel('A').tobytes(), result.getchannel('A').tobytes())
            self.assertEqual(sum(a != b for a, b, m in zip(original.get_flattened_data(), result.get_flattened_data(), footprint.get_flattened_data()) if m == 0), 0)
        self.edits.assert_called_once()

    def test_concurrent_http_reservation_is_consumed_once_and_replays_failure(self):
        self.prepare(cap=1)
        entered, release = threading.Event(), threading.Event()
        def fail(*args):
            entered.set()
            if not release.wait(8):
                raise AssertionError('MOCK release timeout')
            raise RuntimeError('MOCK ambiguous billed failure')
        self.edits.side_effect = fail
        with ThreadPoolExecutor(max_workers=1) as pool:
            task = pool.submit(self.render, 'inflight')
            try:
                self.assertTrue(entered.wait(5))
                self.assertEqual(self.review()['attempts'][0]['status'], 'reserved')
                self.render('inflight', status=400)
                self.render('other', status=400)
            finally:
                release.set()
            failure = task.result(10)
        self.assertEqual(failure['receipt']['status'], 'failed')
        self.restart()
        self.assertEqual(self.render('inflight'), failure)
        self.render('other', status=400)
        self.assertEqual(self.review()['budget']['used'], 1)
        self.edits.assert_called_once()

    def test_interrupted_reservation_restarts_fail_closed_and_retains_tombstone(self):
        review = self.prepare(cap=1)
        self.edits.side_effect = SystemExit('MOCK process interruption')
        payload = {'attribute_id': 'hair_cut', 'value_id': 'blunt_bob', 'method': 'reference_edit', 'request_key': 'interrupted'}
        with self.assertRaises(SystemExit):
            self.app.comparison_post('hair', 'preview', payload)
        self.restart()
        current = self.review()
        self.assertEqual(current['budget']['used'], 1)
        self.assertEqual(current['cycle']['used'], 1)
        self.assertEqual(current['attempts'][0]['status'], 'reserved')
        self.render('interrupted', status=400)
        self.render('new', status=400)
        reopened = self.post('hair', 'reopen', {'attribute_id': 'hair_cut', 'expected_contract_hash': review['contract_hash'],
                                             'approval_note': 'MOCK revise after interrupted worker'})
        self.assertEqual(reopened['budget']['used'], 1)
        self.assertEqual(reopened['attempts'][0]['status'], 'reserved')
        self.render('interrupted', status=400)
        self.edits.assert_called_once()

    def test_custom_target_cannot_be_published_as_canonical_catalog_color(self):
        review = self.prepare(attribute='hair_color', cap=0)
        custom = self.render('custom', attribute='hair_color', value='platinum', params={'hex': '#ff0000'})
        self.assertEqual(custom['receipt']['catalog_params']['colour']['hex'], '#e8e1ce')
        self.assertEqual(custom['receipt']['effective_params']['colour']['hex'], '#ff0000')
        self.assertTrue(custom['custom'])
        self.approve(review, 'hair_color', 'pilot', artifact_ids=[custom['id']])
        result = self.post('hair', 'approve', {'attribute_id': 'hair_color', 'stage': 'publish',
                           'expected_contract_hash': review['contract_hash'], 'artifact_ids': [custom['id']]}, status=400)
        self.assertIn('Custom', result['error'])
        self.assertEqual(self.target('hair_color', 'platinum')['thumbnail_source'], 'pending')
        self.assertEqual(self.review(attribute='hair_color')['published_artifact_ids'], [])
        self.edits.assert_not_called()

    def test_no_person_geometry_denied_before_any_native_reservation(self):
        # Inject an actual synthetic swatch reference into an isolated native
        # record before mask/contract review. Real catalog group contracts stay
        # intact; this deliberately invalid subject must reach the person guard.
        self.render('swatch', 'wardrobe', 'fabric_color', 'pale_pink')
        swatch = self.review('wardrobe', 'fabric_color')
        native = self.review('wardrobe', 'drape_effect')
        self.assertEqual(native['baseline_requirements'], [])
        with self.app.comparisons._transaction() as db:
            record = self.app.comparisons._get(db, 'wardrobe::' + native['group'])
            record['baseline'] = copy.deepcopy(swatch['baseline'])
            self.app.comparisons._save(db, record)
        review = self.post('wardrobe', 'mask', {'attribute_id': 'drape_effect', 'polygon': self.polygon})
        review = self.approve(review, 'drape_effect', 'contract', provider_attempt_cap=1)
        before = self.review('wardrobe', 'drape_effect')
        denied = self.render('native-no-person', 'wardrobe', 'drape_effect', 'on', status=400)
        self.assertIn('no-person', denied['error'])
        after = self.review('wardrobe', 'drape_effect')
        self.assertEqual(before, after)
        self.assertEqual(after['baseline']['subject_metadata']['presentation'], 'no_person')
        self.assertEqual(after['budget']['used'], 0)
        self.assertEqual(after['cycle']['used'], 0)
        self.assertFalse(any(a['receipt']['provider_attempt_reserved'] for a in after['attempts']))
        self.edits.assert_not_called()

    def test_full_publication_provenance_pixels_http_assets_and_restart_preservation(self):
        review, artifact = self.publish_color()
        receipt = artifact['receipt']
        mask = review['masks']['hair_color']
        entries = ((review['baseline']['asset_id'], review['baseline']['sha256']),
                   (mask['asset_id'], mask['sha256']), (mask['overlay_asset_id'], mask['overlay_sha256']),
                   (artifact['id'], receipt['output_sha256']))
        for ident, digest in entries:
            raw = self.request('GET', '/api/comparisons/assets/' + ident + '.png')
            self.assertEqual(sha(raw), digest)
            self.assertEqual(self.request('HEAD', '/api/comparisons/assets/' + ident + '.png'), b'')
            with Image.open(io.BytesIO(raw)) as image:
                self.assertEqual(image.format, 'PNG')
                self.assertEqual(image.size, (64, 80))
        self.assertEqual(receipt['base_sha256'], review['baseline']['sha256'])
        self.assertEqual(receipt['mask_sha256'], mask['sha256'])
        self.assertEqual(receipt['mask_overlay_sha256'], mask['overlay_sha256'])
        encoded_receipt = json.dumps(receipt, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
        self.assertEqual(artifact['receipt_sha256'], sha(encoded_receipt))
        images = [Image.open(self.app.comparisons.asset(ident)).convert(mode)
                  for ident, mode in ((entries[0][0], 'RGBA'), (entries[1][0], 'L'), (entries[3][0], 'RGBA'))]
        before, footprint, after = [list(image.get_flattened_data()) for image in images]
        self.assertTrue(any(m == 0 for m in footprint))
        self.assertTrue(any(0 < m < 255 for m in footprint))
        self.assertEqual(sum(b != a for b, m, a in zip(before, footprint, after) if m == 0), 0)
        self.assertEqual(sum(b != a for b, m, a in zip(before, footprint, after) if m > 0), receipt['inside_change']['changed_pixels'])
        self.assertGreater(receipt['inside_change']['changed_pixels'], 0)
        self.assertEqual(receipt['outside_delta'], 0)
        approval = review['approvals'][-1]
        self.assertEqual(approval['baseline_sha256'], receipt['base_sha256'])
        self.assertEqual(approval['mask_hashes']['hair_color'], receipt['mask_sha256'])
        self.assertEqual(approval['overlay_hashes']['hair_color'], receipt['mask_overlay_sha256'])
        self.assertEqual(approval['artifact_hashes'][artifact['id']], receipt['output_sha256'])
        self.restart()
        self.assertEqual(self.review(attribute='hair_color'), review)
        self.assertEqual(self.target('hair_color', 'platinum')['thumbnail_url'], artifact['url'])
        self.assertEqual(self.review(attribute='hair_color'), review)
        self.assertEqual(self.source.read_bytes(), self.source_bytes)
        self.edits.assert_not_called()

    def test_asset_and_receipt_tampering_withhold_publication_after_restart(self):
        review, artifact = self.publish_color()
        mask = review['masks']['hair_color']
        for ident in (review['baseline']['asset_id'], mask['asset_id'], mask['overlay_asset_id'], artifact['id']):
            with self.subTest(asset=ident):
                path = self.app.comparisons.asset(ident)
                raw = path.read_bytes()
                try:
                    path.write_bytes(b'MOCK tampered PNG')
                    self.request('GET', '/api/comparisons/assets/' + ident + '.png', status=404)
                    self.request('HEAD', '/api/comparisons/assets/' + ident + '.png', status=404)
                    self.restart()
                    value = self.target('hair_color', 'platinum')
                    self.assertEqual(value['thumbnail_source'], 'withheld_provenance')
                    self.assertEqual(value['thumbnail_url'], '')
                    self.assertNotIn('example_url', value)
                finally:
                    path.write_bytes(raw)
                self.assertEqual(self.target('hair_color', 'platinum')['thumbnail_source'], 'approved_comparison')
        key = 'hair::' + review['group']
        with self.app.comparisons._transaction() as db:
            original = self.app.comparisons._get(db, key)
        for field in ('base_sha256', 'mask_sha256', 'mask_overlay_sha256', 'output_sha256', 'outside_delta', 'effective_params'):
            with self.subTest(receipt=field):
                corrupted = copy.deepcopy(original)
                corrupted['artifacts'][0]['receipt'][field] = 1 if field == 'outside_delta' else ({'colour': {'hex': '#ff0000'}} if field == 'effective_params' else '0' * 64)
                with self.app.comparisons._transaction() as db:
                    self.app.comparisons._save(db, corrupted)
                try:
                    self.restart()
                    self.assertEqual(self.target('hair_color', 'platinum')['thumbnail_source'], 'withheld_provenance')
                finally:
                    with self.app.comparisons._transaction() as db:
                        self.app.comparisons._save(db, original)
        with self.app.comparisons._transaction() as db:
            row = db.execute('SELECT receipt FROM comparison_requests WHERE category_id=? AND request_key=?', ('hair', 'canonical')).fetchone()
            original_attempt = row['receipt']
            changed = json.loads(original_attempt)
            changed['output_sha256'] = '0' * 64
            db.execute('UPDATE comparison_requests SET receipt=? WHERE category_id=? AND request_key=?', (json.dumps(changed), 'hair', 'canonical'))
        try:
            self.restart()
            self.assertEqual(self.target('hair_color', 'platinum')['thumbnail_source'], 'withheld_provenance')
        finally:
            with self.app.comparisons._transaction() as db:
                db.execute('UPDATE comparison_requests SET receipt=? WHERE category_id=? AND request_key=?', (original_attempt, 'hair', 'canonical'))
        self.assertEqual(self.target('hair_color', 'platinum')['thumbnail_source'], 'approved_comparison')
        self.edits.assert_not_called()

    def test_requested_snapshot_precedes_defaults_and_presets_preserve_comparison_only_anchor(self):
        review = self.prepare(attribute='hair_color', cap=0)
        anchor = {'category_id': 'hair', 'group': review['group'], 'baseline_asset_id': review['baseline']['asset_id'],
                  'contract_hash': review['contract_hash'], 'locked_fields': review['locked_fields']}
        draft = {'selections': {'hair_color': ['platinum']}, 'whitelist': {}, 'mode': 'single', 'n': 1,
                 'aspect_ratio': '9:16', 'extra_prompt': '', 'comparison': anchor}
        saved = self.request('POST', '/api/presets', {'name': 'MOCK comparison context', 'draft': draft, 'request_key': 'preset-anchor'}, status=201)
        self.assertEqual(saved['draft'], draft)
        resolved = self.request('POST', '/api/catalog/resolve', {'draft': draft})
        self.assertEqual(resolved['raw_draft'], draft)
        self.assertEqual(resolved['draft']['comparison'], anchor)
        payload = {k: v for k, v in draft.items() if k != 'comparison'}
        plan = self.request('POST', '/api/preview', payload)['plans'][0]
        requested = plan['requested_selection_snapshot']
        self.assertEqual(requested['requested_maps'], {'selections': draft['selections'], 'whitelist': {}})
        self.assertNotIn('gender', requested['selections'])
        self.assertNotIn('age', requested['selections'])
        self.assertEqual(set(requested['defaulted']), {'age', 'gender'})
        self.assertEqual(plan['selections']['gender'], ['woman'])
        self.assertEqual(plan['selections']['age'], ['age_24'])
        self.assertNotIn('comparison', plan)
        self.assertNotIn(anchor['contract_hash'], plan['prompt'])
        self.assertNotIn(anchor['baseline_asset_id'], plan['prompt'])
        self.request('POST', '/api/preview', draft, status=400)
        explicit = self.request('POST', '/api/preview', {**payload, 'selections': {'gender': ['man'], 'age': ['age_85']}})['plans'][0]
        self.assertEqual(explicit['requested_selection_snapshot']['defaulted'], [])
        self.assertEqual(explicit['selections'], {'age': ['age_85'], 'gender': ['man']})
        # Real async JobManager + Gallery persist the requested/resolved split;
        # image generation here is a labeled MOCK, never a vendor request.
        self.expected_generations = 1
        self.generation.side_effect = None
        self.generation.return_value = (base64.b64encode(png(Image.new('RGB', (90, 160), 'gray'))).decode(), 'image/png')
        submitted = self.request('POST', '/api/jobs', {**payload, 'seed': 123}, status=202)
        deadline = time.monotonic() + 5
        job = self.request('GET', '/api/jobs/' + submitted['id'])
        while job['status'] in ('queued', 'running') and time.monotonic() < deadline:
            time.sleep(.01)
            job = self.request('GET', '/api/jobs/' + submitted['id'])
        self.assertEqual(job['status'], 'completed', job)
        self.assertEqual(len(job['results']), 1)
        image = self.request('GET', '/api/images/' + job['results'][0]['id'])
        self.assertEqual(image['requested_selection_snapshot'], requested)
        self.assertEqual(image['resolved_selection_snapshot']['gender']['values'][0]['id'], 'woman')
        self.assertEqual(image['resolved_selection_snapshot']['age']['values'][0]['id'], 'age_24')
        self.assertNotIn('comparison', image)
        self.assertNotIn(anchor['baseline_asset_id'], self.generation.call_args.args[0])
        self.restart()
        self.assertEqual(self.request('GET', '/api/presets')['presets'], [saved])
        self.assertEqual(self.review(attribute='hair_color')['baseline']['asset_id'], anchor['baseline_asset_id'])
        self.edits.assert_not_called()


if __name__ == '__main__':
    unittest.main()
