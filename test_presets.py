"""Preset persistence and real HTTP parser regressions; no listening sockets/providers."""
import http.client
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import server
from test_server import LIBRARY, MemorySocket

RAW = {'selections': {'retired': ['old'], 'color': ['red']}, 'whitelist': {'color': []},
       'attributeModes': {'color': 'whitelist'}, 'mode': 'variations', 'n': 24,
       'aspect_ratio': '9:16', 'seed': 9, 'extra_prompt': 'unfinished',
       'future': {'nested': [False, None, {'value': 'keep'}]}}


class PresetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = server.Application(Path(self.tmp.name), catalog=server.Catalog(LIBRARY), provider=lambda *_: self.fail('provider called'))

    def tearDown(self):
        self.app.close()
        self.tmp.cleanup()

    def request(self, method, path='/api/presets', payload=None, headers=None, raw=None, client='127.0.0.1'):
        body = raw if raw is not None else json.dumps(payload or {}).encode()
        defaults = [('Host', 'localhost:8123'), ('Content-Type', 'application/json'), ('Content-Length', str(len(body))), ('Origin', 'http://localhost:8123')]
        if headers is not None:
            defaults = headers
        wire = f'{method} {path} HTTP/1.1\r\n' + ''.join(f'{k}: {v}\r\n' for k, v in defaults)
        transport = MemorySocket(wire.encode() + b'\r\n' + body)
        server.AppHandler(transport, (client, 12345), SimpleNamespace(app=self.app, server_port=8123))
        response = http.client.HTTPResponse(MemorySocket(transport.outgoing.getvalue()), method=method)
        response.begin()
        return response.status, json.loads(response.read())

    def create(self, key='save-1', draft=RAW):
        return self.request('POST', payload={'name': 'Unfinished', 'draft': draft, 'request_key': key})

    def test_raw_save_retry_restart_conflict_and_delete_tombstone(self):
        status, preset = self.create()
        self.assertEqual(status, 201)
        self.assertEqual(preset['draft'], RAW)
        self.assertEqual(preset['schema_version'], 1)
        self.assertEqual(preset['catalog_hash'], self.app.catalog.library_hash)
        self.assertEqual(self.create(), (200, preset))  # committed response lost
        self.app.close()
        self.app = server.Application(Path(self.tmp.name), catalog=server.Catalog(LIBRARY))
        self.assertEqual(self.create(), (200, preset))
        self.assertEqual(self.create(draft={})[0], 409)
        self.assertEqual(self.request('GET')[1]['presets'], [preset])
        self.assertEqual(self.request('DELETE', '/api/presets/' + preset['id'])[0], 200)
        self.assertEqual(self.create()[0], 410)
        self.assertEqual(self.request('GET')[1]['presets'], [])

    def test_canonical_import_preserves_raw_and_conflict_copies_across_restarts(self):
        legacy = {'id': 'legacy', 'name': 'Old', 'draft': RAW, 'unknown_record_field': ['preserved']}
        envelope = {'presets': [legacy, {'broken': 'recoverable'}], 'raw_text': json.dumps([legacy, {'broken': 'recoverable'}])}
        status, result = self.request('POST', '/api/presets/import', envelope)
        self.assertEqual(status, 200)
        self.assertEqual(result['presets'][0]['draft'], RAW)
        self.assertTrue(result['warnings'])
        first = result['presets'][0]
        reordered = json.loads(json.dumps(envelope, sort_keys=True))
        self.assertEqual(self.request('POST', '/api/presets/import', reordered)[1]['presets'], [first])
        changed = dict(legacy, draft=dict(RAW, seed=10))
        self.request('POST', '/api/presets/import', {'presets': [changed]})
        self.assertEqual(len(self.request('GET')[1]['presets']), 2)
        self.assertEqual(self.app.presets.archives()[0]['envelope'], envelope)
        self.request('DELETE', '/api/presets/' + first['id'])
        self.app.close()
        self.app = server.Application(Path(self.tmp.name), catalog=server.Catalog(LIBRARY))
        self.request('POST', '/api/presets/import', envelope)
        self.assertEqual(len(self.request('GET')[1]['presets']), 1)
        self.assertEqual(self.app.presets.archives()[0]['envelope'], envelope)

    def test_concurrent_retry_and_import_converge(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            responses = list(pool.map(lambda _: self.create(), range(8)))
        self.assertEqual({r[0] for r in responses}, {200, 201})
        self.assertEqual(len({r[1]['id'] for r in responses}), 1)
        legacy = {'presets': [{'id': 'x', 'name': 'X', 'draft': RAW}]}
        with ThreadPoolExecutor(max_workers=4) as pool:
            responses = list(pool.map(lambda _: self.request('POST', '/api/presets/import', legacy), range(8)))
        self.assertTrue(all(r[0] == 200 for r in responses))
        self.assertEqual(len(self.request('GET')[1]['presets']), 2)

    def test_required_exact_origin_host_client_and_duplicate_headers(self):
        body = json.dumps({'name': 'X', 'draft': RAW, 'request_key': 'x'}).encode()
        base = [('Host', 'localhost:8123'), ('Content-Type', 'application/json'), ('Content-Length', str(len(body)))]
        for origin in [[], [('Origin', 'null')], [('Origin', 'http://evil.test')], [('Origin', 'http://localhost:8123'), ('Origin', 'http://localhost:8123')]]:
            for method, path in [('POST', '/api/presets'), ('POST', '/api/presets/import'), ('DELETE', '/api/presets/' + 'a'*32)]:
                self.assertEqual(self.request(method, path, headers=base + origin, raw=body)[0], 403)
        self.assertEqual(self.request('POST', headers=base + [('Origin', 'http://localhost:8123'), ('Host', 'localhost:8123')], raw=body)[0], 403)
        self.assertEqual(self.request('POST', client='192.0.2.1')[0], 403)
        forwarded = base + [('Origin', 'http://evil.test'), ('X-Forwarded-Host', 'localhost:8123')]
        self.assertEqual(self.request('POST', headers=forwarded, raw=body)[0], 403)

    def test_json_bounds_unsafe_structure_and_duplicate_keys_headers(self):
        for draft in [[], {'__proto__': {}}, {'future': {'constructor': {}}}, {'future': 'x'*70000}, {'selections': {'color': [False]}}, {'seed': float('nan')}]:
            self.assertEqual(self.create(draft=draft)[0], 400)
        self.assertEqual(self.request('POST', raw=b'{"name":"x","name":"y"}')[0], 400)
        body = b'{}'
        for extra in [('Content-Type', 'text/plain'), ('Content-Length', '2'), ('Transfer-Encoding', 'chunked')]:
            headers = [('Host', 'localhost:8123'), ('Origin', 'http://localhost:8123'), ('Content-Type', 'application/json'), ('Content-Length', '2'), extra]
            self.assertEqual(self.request('POST', headers=headers, raw=body)[0], 400)
        self.assertEqual(self.request('POST', '/api/presets/import', {'raw_text': '{broken', 'presets': []})[0], 200)
        self.assertEqual(self.app.presets.archives()[0]['envelope']['raw_text'], '{broken')
        self.assertTrue(self.request('POST', '/api/presets/import', {'raw_text': '', 'presets': []})[1]['warnings'])


if __name__ == '__main__':
    unittest.main()
