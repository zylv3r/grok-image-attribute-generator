"""Operator launchers: isolated fixtures, no providers or live service changes."""
import contextlib
import http.client
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent

def load_tunnel():
    spec = importlib.util.spec_from_file_location('operator_tunnel', ROOT / 'scripts/tunnel.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MemorySocket:
    """Exercise the real HTTP parser and handler without network sockets."""
    def __init__(self, data):
        self.incoming, self.outgoing = io.BytesIO(data), io.BytesIO()
        self.timeouts = []

    def makefile(self, *args):
        return self.incoming

    def sendall(self, data):
        self.outgoing.write(data)

    def settimeout(self, timeout):
        self.timeouts.append(timeout)


class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.tunnel = load_tunnel()
        self.state = {'origin': 'https://example.trycloudflare.com',
                      'token': 'private-test-token', 'expires_at': time.time() + 60}
        self.httpd = SimpleNamespace(state=self.state, app_port=8130)
        self.upstream = Mock()
        self.response = Mock(status=200)
        self.response.read.return_value = b'{"fake_upstream":true}'
        self.response.getheader.side_effect = lambda key, default=None: {
            'Content-Type': 'application/json', 'Content-Length': '22',
            'Content-Security-Policy': "default-src 'self'",
            'Content-Disposition': 'inline'}.get(key, default)
        self.upstream.getresponse.return_value = self.response
        self.factory = patch.object(self.tunnel.http.client, 'HTTPConnection', return_value=self.upstream).start()
        self.addCleanup(patch.stopall)

    def request(self, method='GET', path='/', headers=None, body=b'', authenticated=True):
        headers = list(headers if headers is not None else [('Host', 'example.trycloudflare.com')])
        if authenticated:
            headers.append(('Cookie', '__Host-atelier_access=' + self.state['token']))
        wire = f'{method} {path} HTTP/1.1\r\n'.encode()
        wire += ''.join(f'{key}: {value}\r\n' for key, value in headers).encode()
        transport = MemorySocket(wire + b'\r\n' + body)
        with contextlib.redirect_stderr(io.StringIO()) as logs:
            self.tunnel.ProxyHandler(transport, ('127.0.0.1', 1234), self.httpd)
        self.assertNotIn('private-test-token', logs.getvalue())
        self.assertNotIn('/access/', logs.getvalue())
        response = http.client.HTTPResponse(MemorySocket(transport.outgoing.getvalue()), method=method)
        response.begin()
        return response.status, dict(response.getheaders()), response.read(), transport

    def test_upstream_timeout_allows_synchronous_image_edits(self):
        self.assertEqual(self.request()[0], 200)
        self.assertGreaterEqual(self.factory.call_args.kwargs['timeout'], 180,
                                'The tunnel must not cut off valid native edits after ten seconds')

    def test_before_origin_and_after_expiry_fail_closed(self):
        self.state['origin'] = None
        self.assertEqual(self.request(authenticated=False)[0], 503)
        self.state['origin'] = 'https://example.trycloudflare.com'
        self.state['expires_at'] = time.time() - 1
        for path in ('/', '/access/private-test-token'):
            self.assertEqual(self.request(path=path)[0], 403)
        self.upstream.request.assert_not_called()

    def test_exact_single_host_required_before_auth_or_bootstrap(self):
        for headers in ([], [('Host', 'evil.test')], [('Host', '127.0.0.1:8130')],
                        [('Host', 'example.trycloudflare.com.evil.test')],
                        [('Host', 'example.trycloudflare.com'), ('Host', 'example.trycloudflare.com')]):
            self.assertEqual(self.request(headers=headers, path='/access/private-test-token')[0], 403)
        self.upstream.request.assert_not_called()

    def test_anonymous_or_bad_cookie_never_reaches_gallery_or_jobs(self):
        for path in ('/', '/api/gallery', '/api/jobs'):
            self.assertEqual(self.request(path=path, authenticated=False)[0], 401)
        self.assertEqual(self.request(headers=[('Host', 'example.trycloudflare.com'),
                                              ('Cookie', '__Host-atelier_access=bad')],
                                      authenticated=False)[0], 401)
        self.upstream.request.assert_not_called()

    def test_bootstrap_has_secure_bounded_cookie_and_redirect(self):
        status, headers, body, _ = self.request(path='/access/private-test-token', authenticated=False)
        self.assertEqual(status, 303)
        self.assertEqual(headers['Location'], '/')
        cookie = headers['Set-Cookie']
        for value in ('__Host-atelier_access=private-test-token', 'Secure', 'HttpOnly', 'SameSite=Lax', 'Path=/'):
            self.assertIn(value, cookie)
        self.assertNotIn('Domain=', cookie)
        age = int(cookie.split('Max-Age=')[1].split(';')[0])
        self.assertTrue(0 < age <= 60)
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertEqual(headers['Referrer-Policy'], 'no-referrer')
        self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(self.request(path='/access/wrong', authenticated=False)[0], 401)
        self.upstream.request.assert_not_called()

    def test_authenticated_get_rewrites_only_trusted_headers(self):
        status, headers, raw, _ = self.request(headers=[('Host', 'example.trycloudflare.com:443'),
                                                       ('Authorization', 'secret'), ('X-Other', 'secret')])
        self.assertEqual(status, 200)
        self.assertEqual(raw, b'{"fake_upstream":true}')
        passed = self.upstream.request.call_args.kwargs['headers']
        self.assertEqual(passed['Host'], '127.0.0.1:8130')
        self.assertEqual(passed['Origin'], 'http://127.0.0.1:8130')
        self.assertNotIn('Cookie', passed)
        self.assertNotIn('Authorization', passed)
        self.assertNotIn('X-Other', passed)
        self.assertEqual(headers['Content-Security-Policy'], "default-src 'self'")

    def test_create_proxy_binds_only_ephemeral_loopback(self):
        with patch.object(self.tunnel, 'ThreadingHTTPServer') as factory:
            proxy = self.tunnel.create_proxy(self.state, 8130)
        factory.assert_called_once_with(('127.0.0.1', 0), self.tunnel.ProxyHandler)
        self.assertIs(proxy.state, self.state)
        self.assertEqual(proxy.app_port, 8130)

    def write_headers(self):
        return [('Host', 'example.trycloudflare.com'),
                ('Origin', self.state['origin']), ('Sec-Fetch-Site', 'same-origin'),
                ('Content-Type', 'application/json'), ('Content-Length', '2')]

    def test_post_and_delete_require_exact_single_origin(self):
        for method in ('POST', 'DELETE'):
            for origin in (None, '', 'https://evil.test', 'http://example.trycloudflare.com'):
                headers = [(k, v) for k, v in self.write_headers() if k != 'Origin']
                if origin is not None:
                    headers.append(('Origin', origin))
                self.assertEqual(self.request(method, headers=headers, body=b'{}')[0], 403)
            headers = self.write_headers() + [('Origin', self.state['origin'])]
            self.assertEqual(self.request(method, headers=headers, body=b'{}')[0], 403)
        self.upstream.request.assert_not_called()

    def test_cross_site_write_rejected_before_forward(self):
        headers = [(k, 'cross-site' if k == 'Sec-Fetch-Site' else v) for k, v in self.write_headers()]
        self.assertEqual(self.request('DELETE', headers=headers, body=b'{}')[0], 403)
        self.upstream.request.assert_not_called()

    def test_valid_post_and_delete_forward_bounded_body_and_trusted_origin(self):
        for method in ('POST', 'DELETE'):
            self.assertEqual(self.request(method, '/api/fake', self.write_headers(), b'{}')[0], 200)
            args, kwargs = self.upstream.request.call_args
            self.assertEqual(args, (method, '/api/fake'))
            self.assertEqual(kwargs['body'], b'{}')
            self.assertEqual(kwargs['headers']['Origin'], 'http://127.0.0.1:8130')
            self.assertEqual(kwargs['headers']['Content-Type'], 'application/json')
            self.assertNotIn('Cookie', kwargs['headers'])

    def test_transfer_encoding_even_empty_or_duplicate_is_rejected(self):
        for method in ('GET', 'POST', 'DELETE'):
            for values in ([''], ['chunked'], ['', 'chunked']):
                headers = self.write_headers() + [('Transfer-Encoding', value) for value in values]
                self.assertEqual(self.request(method, headers=headers, body=b'{}')[0], 400)
        self.upstream.request.assert_not_called()

    def test_single_bounded_ascii_content_length_required_for_writes(self):
        for lengths in ([], [''], ['-1'], ['2.0'], ['+2'], ['200001'], ['2', '2']):
            headers = [(k, v) for k, v in self.write_headers() if k != 'Content-Length']
            headers += [('Content-Length', value) for value in lengths]
            status = self.request('POST', headers=headers, body=b'{}')[0]
            self.assertIn(status, (400, 413))
        self.upstream.request.assert_not_called()

    def test_json_content_type_required_single_and_body_timeout(self):
        for types in ([], ['text/plain'], ['application/json', 'application/json']):
            headers = [(k, v) for k, v in self.write_headers() if k != 'Content-Type']
            headers += [('Content-Type', value) for value in types]
            self.assertEqual(self.request('DELETE', headers=headers, body=b'{}')[0], 415)
        self.assertEqual(self.request('POST', headers=self.write_headers(), body=b'{')[0], 400)
        self.upstream.request.assert_not_called()
        status, _, _, transport = self.request('POST', headers=self.write_headers(), body=b'{}')
        self.assertEqual(status, 200)
        self.assertTrue(transport.timeouts)
        self.assertTrue(all(0 < value <= 5 for value in transport.timeouts))

    def test_safe_bounded_request_target_including_parser_normalized_double_slash(self):
        for path in ('//evil.test/x', 'http://evil.test/x', '/' + 'x' * 12000, '/x#fragment', '/x\\y'):
            self.assertEqual(self.request(path=path)[0], 400)
        self.upstream.request.assert_not_called()

    def test_head_uses_upstream_length_without_reading_or_sending_body(self):
        status, headers, body, _ = self.request('HEAD')
        self.assertEqual(status, 200)
        self.assertEqual(headers['Content-Length'], '22')
        self.assertEqual(body, b'')
        self.response.read.assert_not_called()

    def test_response_bound_and_failures_are_generic_without_secret_logs(self):
        self.response.read.return_value = b'x' * (40 * 1024 * 1024 + 1)
        self.assertEqual(self.request()[0], 502)
        self.upstream.request.side_effect = RuntimeError('private-test-token /access/private-test-token prompt')
        status, _, raw, _ = self.request()
        self.assertEqual(status, 502)
        self.assertNotIn(b'private-test-token', raw)

    def test_expiry_rechecked_after_body_before_forward(self):
        state = self.state
        class ExpiringBody(io.BytesIO):
            def read1(self, size):
                result = super().read1(size)
                state['expires_at'] = time.time() - 1
                return result
        def makefile(transport, *args):
            return ExpiringBody(transport.incoming.getvalue())
        with patch.object(MemorySocket, 'makefile', makefile):
            self.assertEqual(self.request('POST', headers=self.write_headers(), body=b'{}')[0], 403)
        self.upstream.request.assert_not_called()


class TunnelLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tunnel = load_tunnel()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_ttl_and_app_port_cli_are_strictly_bounded(self):
        with contextlib.redirect_stderr(io.StringIO()):
            for value in ('0', '-1', '86401', '1.5', 'x'):
                with self.assertRaises(SystemExit):
                    self.tunnel.parse_args(['--ttl', value])
            for value in ('0', '65536', 'x'):
                with self.assertRaises(SystemExit):
                    self.tunnel.parse_args(['--app-port', value])
            with patch.dict(os.environ, {'PORT': 'oops'}):
                with self.assertRaises(SystemExit):
                    self.tunnel.parse_args([])
        self.assertEqual(self.tunnel.parse_args(['--ttl', '1']).ttl, 1)
        self.assertEqual(self.tunnel.parse_args(['--ttl', '86400']).ttl, 86400)
        self.assertEqual(self.tunnel.parse_args([]).ttl, 86400)
        with patch.dict(os.environ, {'PORT': '8130'}):
            self.assertEqual(self.tunnel.parse_args([]).app_port, 8130)

    def test_health_requires_bounded_ok_json_and_never_starts_app(self):
        with patch.object(self.tunnel.http.client, 'HTTPConnection') as factory:
            response = factory.return_value.getresponse.return_value
            response.status = 200
            for raw, expected in ((b'{"status":"ok"}', True), (b'{"status":"bad"}', False),
                                  (b'not json', False), (b'[]', False), (b'x' * 65537, False)):
                response.read.return_value = raw
                self.assertEqual(self.tunnel.app_healthy(8130), expected)
            response.status = 503
            response.read.return_value = b'{"status":"ok"}'
            self.assertFalse(self.tunnel.app_healthy(8130))
            factory.assert_called_with('127.0.0.1', 8130, timeout=2)

    def test_unhealthy_app_fails_before_files_proxy_or_process(self):
        with patch.object(self.tunnel, 'app_healthy', return_value=False), \
             patch.object(self.tunnel, 'create_proxy') as proxy, \
             patch.object(self.tunnel.subprocess, 'Popen') as process, \
             contextlib.redirect_stderr(io.StringIO()) as logs:
            code = self.tunnel.main(['--state-dir', str(self.root / 'state')])
        self.assertNotEqual(code, 0)
        self.assertFalse((self.root / 'state').exists())
        proxy.assert_not_called()
        process.assert_not_called()
        self.assertIn('healthy', logs.getvalue())

    def test_unique_atomic_private_state_and_access_link_modes(self):
        state = {'origin': 'https://example.trycloudflare.com', 'token': 'secret',
                 'expires_at': time.time() + 60}
        first = self.tunnel.create_state_dir(self.root)
        second = self.tunnel.create_state_dir(self.root)
        self.assertNotEqual(first, second)
        self.tunnel.write_state(first, state)
        self.assertEqual(first.stat().st_mode & 0o777, 0o700)
        for name in ('state.json', 'access-link.txt'):
            self.assertEqual((first / name).stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads((first / 'state.json').read_text()), state)
        self.assertEqual((first / 'access-link.txt').read_text().strip(),
                         'https://example.trycloudflare.com/access/secret')
        self.assertEqual({p.name for p in first.iterdir()}, {'state.json', 'access-link.txt'})

    def test_cloudflared_command_and_environment_cannot_inherit_overrides(self):
        with patch.dict(os.environ, {'TUNNEL_TOKEN': 'secret', 'TUNNEL_URL': 'https://evil',
                                     'TUNNEL_LOGLEVEL': 'debug', 'TUNNEL_LOGFILE': '/tmp/private',
                                     'CLOUDFLARE_API_TOKEN': 'secret', 'CF_API_KEY': 'secret'}):
            env = self.tunnel.cloudflared_env(self.root)
        self.assertFalse(any(k.startswith(('TUNNEL_', 'CF_', 'CLOUDFLARE_')) for k in env))
        self.assertEqual(env['HOME'], str(self.root))
        command = self.tunnel.cloudflared_command('/fake/cloudflared', 32123)
        for key, value in (('--url', 'http://127.0.0.1:32123'), ('--metrics', '127.0.0.1:0'),
                           ('--protocol', 'http2'), ('--loglevel', 'info'), ('--config', os.devnull)):
            self.assertEqual(command[command.index(key) + 1], value)
        self.assertIn('--no-autoupdate', command)
        self.assertNotIn('debug', command)

    def test_origin_parser_accepts_only_bare_quick_tunnel_origin(self):
        self.assertEqual(self.tunnel.parse_origin('INF URL https://abc-def.trycloudflare.com |'),
                         'https://abc-def.trycloudflare.com')
        for line in ('https://evil.test', 'https://abc.trycloudflare.com.evil.test',
                     'https://abc.trycloudflare.com/path', 'https://abc.trycloudflare.com:443',
                     'https://abc.trycloudflare.com?token=secret', 'http://abc.trycloudflare.com'):
            self.assertIsNone(self.tunnel.parse_origin(line))

    def test_private_output_only_goes_to_direct_interactive_console(self):
        state = {'origin': 'https://abc.trycloudflare.com', 'token': 'secret', 'expires_at': time.time() + 60}
        for tty, suppress in ((False, False), (True, True), (True, False)):
            output = io.StringIO()
            output.isatty = lambda: tty
            with patch.object(self.tunnel.sys, 'stdout', output):
                self.tunnel.print_ready(state, self.root, suppress)
            value = output.getvalue()
            self.assertIn(state['origin'], value)
            self.assertIn(str(self.root), value)
            self.assertEqual('/access/secret' in value, tty and not suppress)

    def test_cleanup_terminates_waits_then_kills_only_owned_process(self):
        process = Mock()
        process.poll.return_value = None
        process.wait.side_effect = [subprocess.TimeoutExpired('fake', 3), 0]
        self.tunnel.stop_process(process)
        process.terminate.assert_called_once()
        process.kill.assert_called_once()
        self.assertEqual(process.wait.call_count, 2)
        for call in process.wait.call_args_list:
            self.assertLessEqual(call.kwargs['timeout'], 3)

    def supervisor(self, origin=True, exit_early=False):
        proxy = Mock(server_port=32123)
        process = Mock()
        process.stdout = io.StringIO('https://fake.trycloudflare.com\n' if origin else '')
        process.poll.return_value = 2 if exit_early else None
        process.wait.return_value = 0
        mocks = [patch.object(self.tunnel, 'app_healthy', return_value=True),
                 patch.object(self.tunnel, 'find_cloudflared', return_value='/fake/cloudflared'),
                 patch.object(self.tunnel, 'create_proxy', return_value=proxy),
                 patch.object(self.tunnel.subprocess, 'Popen', return_value=process)]
        with contextlib.ExitStack() as stack:
            for mock in mocks:
                stack.enter_context(mock)
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
            code = self.tunnel.main(['--ttl', '1', '--state-dir', str(self.root), '--no-print-private'])
        self.assertTrue(proxy.shutdown.called)
        proxy.server_close.assert_called_once()
        self.assertTrue(process.wait.called)
        return code, process

    def test_lease_expiry_cleans_owned_proxy_and_subprocess(self):
        code, process = self.supervisor()
        self.assertEqual(code, 0)
        process.terminate.assert_called_once()

    def test_cloudflared_early_exit_is_nonzero_and_cleans_proxy(self):
        code, process = self.supervisor(exit_early=True)
        self.assertNotEqual(code, 0)
        process.terminate.assert_not_called()

    def test_readiness_timeout_is_bounded_and_cleans_owned_resources(self):
        with patch.object(self.tunnel, 'READINESS_SECONDS', 0.02):
            code, process = self.supervisor(origin=False)
        self.assertNotEqual(code, 0)
        process.terminate.assert_called_once()

    def test_sigterm_and_keyboard_interrupt_clean_owned_resources(self):
        for mode in ('signal', 'interrupt'):
            proxy, process = Mock(server_port=32123), Mock()
            process.stdout = io.StringIO('https://fake.trycloudflare.com\n')
            process.poll.return_value = None
            process.wait.return_value = 0
            handlers = {}
            def register(signum, handler):
                old = handlers.get(signum)
                handlers[signum] = handler
                return old
            def ready(*args):
                if mode == 'signal':
                    handlers[self.tunnel.signal.SIGTERM](None, None)
                else:
                    raise KeyboardInterrupt()
            with patch.object(self.tunnel, 'app_healthy', return_value=True), \
                 patch.object(self.tunnel, 'find_cloudflared', return_value='/fake/cloudflared'), \
                 patch.object(self.tunnel, 'create_proxy', return_value=proxy), \
                 patch.object(self.tunnel.subprocess, 'Popen', return_value=process), \
                 patch.object(self.tunnel.signal, 'signal', side_effect=register), \
                 patch.object(self.tunnel, 'print_ready', side_effect=ready):
                code = self.tunnel.main(['--state-dir', str(self.root)])
            self.assertEqual(code, 0)
            process.terminate.assert_called_once()
            self.assertTrue(proxy.shutdown.called)
            self.assertTrue(proxy.server_close.called)
            self.assertTrue(all(value is None for value in handlers.values()))

    def test_real_fake_child_is_reaped_after_lease_no_orphan(self):
        # This runs a local fake child, never cloudflared or a tunnel.
        child = None
        original_popen = subprocess.Popen
        def start(*args, **kwargs):
            nonlocal child
            child = original_popen([sys.executable, '-u', '-c',
                'import time; print("https://fake.trycloudflare.com",flush=True); time.sleep(60)'],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            return child
        def cleanup():
            if child is not None and child.poll() is None:
                child.kill()
                child.wait(timeout=3)
        self.addCleanup(cleanup)
        proxy = Mock(server_port=32123)
        with patch.object(self.tunnel, 'app_healthy', return_value=True), \
             patch.object(self.tunnel, 'find_cloudflared', return_value='/fake/cloudflared'), \
             patch.object(self.tunnel, 'create_proxy', return_value=proxy), \
             patch.object(self.tunnel.subprocess, 'Popen', side_effect=start), \
             contextlib.redirect_stdout(io.StringIO()):
            code = self.tunnel.main(['--ttl', '1', '--state-dir', str(self.root)])
        self.assertEqual(code, 0)
        self.assertIsNotNone(child.returncode)
        with self.assertRaises(ProcessLookupError):
            os.kill(child.pid, 0)

    def test_cleanup_failure_is_generic_and_still_closes_proxy(self):
        proxy = Mock(server_port=32123)
        proxy.shutdown.side_effect = RuntimeError('private-token cookie prompt')
        process = Mock()
        process.stdout = io.StringIO('https://fake.trycloudflare.com\n')
        process.poll.return_value = 1
        process.wait.return_value = 1
        with patch.object(self.tunnel, 'app_healthy', return_value=True), \
             patch.object(self.tunnel, 'find_cloudflared', return_value='/fake/cloudflared'), \
             patch.object(self.tunnel, 'create_proxy', return_value=proxy), \
             patch.object(self.tunnel.subprocess, 'Popen', return_value=process), \
             contextlib.redirect_stderr(io.StringIO()) as logs:
            code = self.tunnel.main(['--state-dir', str(self.root)])
        self.assertNotEqual(code, 0)
        proxy.server_close.assert_called_once()
        self.assertNotIn('private-token', logs.getvalue())


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'relocated repo'
        (self.root / 'scripts').mkdir(parents=True)
        for name in ('run-server.sh', 'run-tunnel.sh', 'tunnel.py'):
            source = ROOT / 'scripts' / name
            if source.exists():
                shutil.copy(source, self.root / 'scripts' / name)
        (self.root / 'src').mkdir()
        (self.root / 'src' / 'app.tsx').write_text('source')
        (self.root / 'package-lock.json').write_text('{}')
        (self.root / 'package.json').write_text('{}')
        (self.root / 'dist').mkdir()
        (self.root / 'dist' / 'index.html').write_text('built')
        (self.root / 'node_modules' / '.bin').mkdir(parents=True)
        (self.root / 'node_modules' / '.bin' / 'vite').touch()
        (self.root / 'node_modules' / '.bin' / 'tsc').touch()
        (self.root / 'server.py').write_text(
            'import os,json; print(json.dumps({k:os.environ.get(k) for k in '
            '["HOST","PORT","HERMES_HOME"]}))')
        self.bin = Path(self.tmp.name) / 'bin'
        self.bin.mkdir()
        self.log = Path(self.tmp.name) / 'commands'
        self.command('systemctl', 'import sys; sys.exit(1)')
        self.command('npm', 'import sys; print("npm " + " ".join(sys.argv[1:]))')
        # Only the fixture's server bind probe is mocked; no app is started.
        self.site = Path(self.tmp.name) / 'site'
        self.site.mkdir()
        (self.site / 'sitecustomize.py').write_text(
            'import socket,os\n'
            'class Probe(socket.socket):\n'
            ' def __init__(self,*a,**k): self._closed = True\n'
            ' def close(self): pass\n'
            ' def bind(self, address):\n'
            '  if os.environ.get("FIXTURE_OCCUPIED"): raise OSError("occupied")\n'
            'socket.socket = Probe\n'
            'import http.client,io\n'
            'class Health:\n'
            ' status = 200\n'
            ' def read(self,*a): return os.environ.get("FIXTURE_HEALTH", "{\\"status\\":\\"ok\\"}").encode()\n'
            'class Connection:\n'
            ' def __init__(self,*a,**k): pass\n'
            ' def request(self,*a,**k): pass\n'
            ' def getresponse(self): return Health()\n'
            ' def close(self): pass\n'
            'http.client.HTTPConnection = Connection\n')
        self.env = {**os.environ, 'PATH': str(self.bin) + ':' + os.environ['PATH'],
                    'PYTHON_BIN': sys.executable, 'PORT': '8130',
                    'PYTHONPATH': str(self.site),
                    'HERMES_HOME': str(Path(self.tmp.name) / 'hermes')}

    def command(self, name, code):
        path = self.bin / name
        path.write_text('#!' + sys.executable + '\n' + code + '\n')
        path.chmod(0o755)

    def run_script(self, *args, name='run-server.sh', **env):
        return subprocess.run(['bash', str(self.root / 'scripts' / name), *args],
                              env={**self.env, **env}, cwd='/tmp', text=True,
                              capture_output=True, timeout=15)

    def test_help_is_available_without_dependencies(self):
        result = self.run_script('--help', PYTHON_BIN='/missing', PORT='bad')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--foreground', result.stdout)

    def test_port_and_unknown_arguments_rejected(self):
        for port in ('0', '65536', 'x', '-1', '8123.0', '9' * 5000):
            result = self.run_script('--check', PORT=port)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('PORT', result.stderr)
        self.assertNotEqual(self.run_script('--wat').returncode, 0)

    def test_missing_python_override_is_actionable(self):
        result = self.run_script('--check', PYTHON_BIN='/missing')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('PYTHON_BIN', result.stderr)

    def test_missing_pillow_or_requests_is_actionable(self):
        deps = Path(self.tmp.name) / 'deps'
        deps.mkdir()
        for name in ('PIL', 'requests'):
            with self.subTest(name=name):
                source = deps / (name + '.py')
                source.write_text('raise ImportError("fixture missing dependency")')
                result = self.run_script('--check', PYTHONPATH=str(deps))
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('Pillow', result.stderr)
                self.assertIn('requests', result.stderr)
                source.unlink()

    def test_check_is_read_only_and_relocatable(self):
        result = self.run_script('--check')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(str(self.root), result.stdout)
        self.assertNotIn('npm ', result.stdout)

    def test_foreground_preserves_hermes_and_forces_loopback(self):
        result = self.run_script('--foreground', HOST='0.0.0.0')
        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(result.stdout.splitlines()[-1])
        self.assertEqual(value, {'HOST': '127.0.0.1', 'PORT': '8130',
                                 'HERMES_HOME': self.env['HERMES_HOME']})

    def service(self, working_dir=None, active=True):
        self.command('systemctl',
            'import sys\nfrom pathlib import Path\n'
            f'with Path({str(self.log)!r}).open("a") as log: log.write(" ".join(sys.argv[1:])+"\\n")\n'
            'if "show" in sys.argv:\n'
            f' print("loaded" if "LoadState" in sys.argv else {str(working_dir or self.root)!r})\n'
            f'elif "is-active" in sys.argv: sys.exit({0 if active else 1})')

    def test_matching_active_service_is_health_checked_without_build_or_restart(self):
        self.service()
        shutil.rmtree(self.root / 'dist')
        for args in ((), ('--check',)):
            result = self.run_script(*args, PORT='8123')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn('npm ', result.stdout)
            self.assertNotIn('start', self.log.read_text())
        result = self.run_script(PORT='8123', FIXTURE_HEALTH='{"status":"bad"}')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('health', result.stderr)
        self.assertNotIn('restart', self.log.read_text())

    def test_matching_inactive_service_starts_once_and_checks_real_health(self):
        self.service(active=False)
        result = self.run_script(PORT='8123')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.log.read_text().count('start atelier-image-studio.service'), 1)
        self.assertNotIn('restart', self.log.read_text())

    def test_unmatched_service_and_nondefault_port_use_foreground(self):
        self.service('/different/repo')
        result = self.run_script(PORT='8123')
        self.assertEqual(json.loads(result.stdout.splitlines()[-1])['PORT'], '8123')
        self.service()
        result = self.run_script(PORT='8130')
        self.assertEqual(json.loads(result.stdout.splitlines()[-1])['PORT'], '8130')
        self.assertNotIn('start', self.log.read_text())

    def test_occupied_port_is_refused_even_in_check(self):
        for args in (('--check',), ('--foreground',)):
            result = self.run_script(*args, FIXTURE_OCCUPIED='1')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Port 8130', result.stderr)

    def test_check_stale_ui_does_not_build_then_foreground_ci_and_build(self):
        shutil.rmtree(self.root / 'node_modules')
        shutil.rmtree(self.root / 'dist')
        result = self.run_script('--check')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('npm ', result.stdout)
        result = self.run_script('--foreground')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertLess(result.stdout.index('npm ci'), result.stdout.index('npm run build'))
        (self.root / 'dist').mkdir()
        (self.root / 'dist' / 'index.html').write_text('old')
        os.utime(self.root / 'dist' / 'index.html', (1, 1))
        (self.root / 'node_modules' / '.bin').mkdir(parents=True)
        for name in ('vite', 'tsc'):
            (self.root / 'node_modules' / '.bin' / name).touch()
        result = self.run_script('--foreground')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('npm run build', result.stdout)
        self.assertNotIn('npm ci', result.stdout)

    def test_tunnel_wrapper_help_and_relocatable_python_override(self):
        result = self.run_script('--help', name='run-tunnel.sh')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--ttl', result.stdout)
        (self.root / 'scripts/tunnel.py').write_text('import sys,json; print(json.dumps(sys.argv))')
        result = self.run_script('--app-port', '8130', '--ttl', '8', '--no-print-private', name='run-tunnel.sh')
        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(result.stdout)
        self.assertEqual(value, [str(self.root / 'scripts/tunnel.py'), '--app-port', '8130', '--ttl', '8', '--no-print-private'])

    def test_tunnel_wrapper_missing_python_override_fails_clearly(self):
        result = self.run_script('--ttl', '1', name='run-tunnel.sh', PYTHON_BIN='/missing')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('PYTHON_BIN', result.stderr)


if __name__ == '__main__':
    unittest.main()
