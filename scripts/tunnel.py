#!/usr/bin/env python3
"""Foreground, leased quick tunnel with a fail-closed loopback auth gateway."""
import argparse
import hmac
import http.client
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import queue
import re
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import urlsplit
import uuid

BODY_LIMIT = 200_000
RESPONSE_LIMIT = 40 * 1024 * 1024
PATH_LIMIT = 12_000
READINESS_SECONDS = 90


class ProxyHandler(BaseHTTPRequestHandler):
    # Never log request targets, headers, cookies, bodies, or exception details.
    def log_message(self, *args):
        pass

    def send_error(self, code, message=None, explain=None):
        self.reply(code, b'Gateway request rejected.')

    def reply(self, status, body=b'', headers=None, length=None):
        self.close_connection = True
        self.send_response(status)
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.send_header('Content-Length', str(len(body) if length is None else length))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)

    def authorized(self):
        values = self.headers.get_all('Cookie', [])
        if len(values) != 1:
            return False
        try:
            cookie = SimpleCookie()
            cookie.load(values[0])
            value = cookie.get('__Host-atelier_access')
            return bool(value) and hmac.compare_digest(value.value, self.server.state['token'])
        except (ValueError, TypeError):
            return False

    def handle_proxy(self):
        state = self.server.state
        if time.time() >= state['expires_at']:
            self.reply(403, b'Access lease expired.')
            return
        origin = state['origin']
        if not origin:
            self.reply(503, b'Tunnel is not ready.')
            return
        parsed = urlsplit(origin)
        hosts = self.headers.get_all('Host', [])
        allowed = {parsed.netloc, f'{parsed.hostname}:{parsed.port or 443}'}
        if len(hosts) != 1 or hosts[0] not in allowed:
            self.reply(403, b'Invalid host.')
            return
        # BaseHTTPRequestHandler normalizes leading //; inspect the original target.
        target = self.raw_requestline.decode('iso-8859-1').split()[1]
        if (not target.startswith('/') or target.startswith('//') or len(target) > PATH_LIMIT
                or '#' in target or '\\' in target or any(ord(c) < 33 or ord(c) == 127 for c in target)):
            self.reply(400, b'Invalid path.')
            return
        if self.headers.get_all('Transfer-Encoding') is not None:
            self.reply(400, b'Invalid request framing.')
            return
        if self.command == 'GET' and self.path.startswith('/access/'):
            token = self.path[len('/access/'):]
            try:
                valid = hmac.compare_digest(token, state['token'])
            except (ValueError, TypeError):
                valid = False
            if not valid:
                self.reply(401, b'Access required.')
                return
            age = max(0, math.floor(state['expires_at'] - time.time()))
            if age == 0:
                self.reply(403, b'Access lease expired.')
                return
            self.reply(303, headers={'Location': '/', 'Set-Cookie':
                f'__Host-atelier_access={state["token"]}; Path=/; Max-Age={age}; Secure; HttpOnly; SameSite=Lax'})
            return
        if not self.authorized():
            self.reply(401, b'Access required.')
            return
        body = None
        lengths = self.headers.get_all('Content-Length', [])
        writing = self.command in ('POST', 'DELETE')
        if writing:
            origins = self.headers.get_all('Origin', [])
            fetch = self.headers.get_all('Sec-Fetch-Site', [])
            if (origins != [origin] or len(fetch) > 1
                    or any(value.lower() == 'cross-site' for value in fetch)):
                self.reply(403, b'Invalid request origin.')
                return
        if (len(lengths) > 1 or (writing and not lengths)
                or any(not re.fullmatch(r'[0-9]{1,6}', value) for value in lengths)):
            self.reply(400, b'Invalid request length.')
            return
        size = int(lengths[0]) if lengths else 0
        if size > BODY_LIMIT:
            self.reply(413, b'Request body too large.')
            return
        if not writing and size:
            self.reply(400, b'Unexpected request body.')
            return
        if writing:
            types = self.headers.get_all('Content-Type', [])
            if len(types) != 1 or types[0].split(';')[0].strip().lower() != 'application/json':
                self.reply(415, b'JSON content type required.')
                return
            chunks = []
            deadline = time.monotonic() + 5
            remaining = size
            try:
                while remaining:
                    timeout = deadline - time.monotonic()
                    if timeout <= 0:
                        raise TimeoutError()
                    self.connection.settimeout(timeout)
                    chunk = self.rfile.read1(min(remaining, 65536))
                    if not chunk:
                        raise ValueError()
                    chunks.append(chunk)
                    remaining -= len(chunk)
            except (OSError, ValueError):
                self.reply(400, b'Request body unavailable.')
                return
            body = b''.join(chunks)
        if time.time() >= state['expires_at']:
            self.reply(403, b'Access lease expired.')
            return
        self.forward(body)

    def forward(self, body):
        # Synchronous image edits can exceed ten seconds; keep the app's three-minute budget.
        conn = http.client.HTTPConnection('127.0.0.1', getattr(self.server, 'app_port'), timeout=180)
        try:
            target = f'127.0.0.1:{self.server.app_port}'
            trusted = {'Host': target, 'Origin': 'http://' + target}
            if body is not None:
                trusted['Content-Type'] = 'application/json'
                trusted['Content-Length'] = str(len(body))
            conn.request(self.command, self.path, body=body, headers=trusted)
            response = conn.getresponse()
            raw = b'' if self.command == 'HEAD' else response.read(RESPONSE_LIMIT + 1)
            if len(raw) > RESPONSE_LIMIT:
                self.reply(502, b'Upstream response unavailable.')
                return
            headers = {key: value for key in ('Content-Type', 'Content-Security-Policy', 'Content-Disposition')
                       if (value := response.getheader(key)) is not None}
            length = None
            if self.command == 'HEAD':
                advertised = response.getheader('Content-Length', '0')
                if not re.fullmatch(r'[0-9]{1,9}', advertised) or int(advertised) > RESPONSE_LIMIT:
                    self.reply(502, b'Upstream response unavailable.')
                    return
                length = int(advertised)
            self.reply(response.status, raw, headers, length)
        except Exception:
            self.reply(502, b'Upstream response unavailable.')
        finally:
            conn.close()

    do_GET = handle_proxy
    do_HEAD = handle_proxy
    do_POST = handle_proxy
    do_DELETE = handle_proxy


def create_proxy(state, app_port, port=0):
    """Return an unstarted server; caller owns serve_forever/shutdown/server_close.

    State has only origin (None until ready), token, and expires_at (epoch seconds).
    No endpoint exposes state. Backend destination is always IPv4 loopback.
    """
    proxy = ThreadingHTTPServer(('127.0.0.1', port), ProxyHandler)
    proxy.daemon_threads = True
    proxy.state = state
    proxy.app_port = app_port
    return proxy


def bounded_integer(lower, upper):
    def convert(value):
        if not re.fullmatch(r'[0-9]{1,6}', str(value)) or not lower <= int(value) <= upper:
            raise argparse.ArgumentTypeError(f'must be an integer from {lower} through {upper}')
        return int(value)
    return convert


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app-port', type=bounded_integer(1, 65535), default=os.environ.get('PORT', '8123'),
                        help='already healthy loopback app port (PORT or 8123)')
    parser.add_argument('--ttl', type=bounded_integer(1, 86400), default=86400,
                        help='lease seconds, 1..86400 (default: 86400)')
    parser.add_argument('--state-dir', type=Path, default=Path(__file__).resolve().parent.parent / 'runtime/tunnels')
    parser.add_argument('--no-print-private', action='store_true', help='never print the private access link')
    return parser.parse_args(argv)


def app_healthy(port):
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=2)
    try:
        conn.request('GET', '/api/health')
        response = conn.getresponse()
        raw = response.read(65537)
        return response.status == 200 and len(raw) <= 65536 and json.loads(raw).get('status') == 'ok'
    except (OSError, ValueError, AttributeError, http.client.HTTPException):
        return False
    finally:
        conn.close()


def find_cloudflared():
    found = shutil.which('cloudflared')
    fallback = Path.home() / 'bin/cloudflared'
    return found or (str(fallback) if fallback.is_file() and os.access(fallback, os.X_OK) else None)


def create_state_dir(base):
    base = Path(base).resolve()
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory = base / str(uuid.uuid4())
    directory.mkdir(mode=0o700)
    directory.chmod(0o700)
    return directory


def atomic_private_write(directory, name, text):
    descriptor, temporary = tempfile.mkstemp(dir=directory, prefix='.pending-')
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, 'w', encoding='utf-8') as output:
            output.write(text)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, directory / name)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def write_state(directory, state):
    atomic_private_write(directory, 'state.json', json.dumps(state) + '\n')
    if state['origin']:
        atomic_private_write(directory, 'access-link.txt', state['origin'] + '/access/' + state['token'] + '\n')


def cloudflared_env(directory):
    # A fresh HOME and explicit empty config prevent ambient credentials/config reads.
    env = {key: os.environ[key] for key in ('PATH', 'LANG', 'LC_ALL', 'SYSTEMROOT', 'TMPDIR') if key in os.environ}
    env.update(HOME=str(directory), XDG_CONFIG_HOME=str(directory), XDG_DATA_HOME=str(directory))
    return env


def cloudflared_command(binary, port):
    return [binary, '--config', os.devnull, 'tunnel', '--no-autoupdate',
            '--url', f'http://127.0.0.1:{port}', '--metrics', '127.0.0.1:0',
            '--protocol', 'http2', '--loglevel', 'info']


def parse_origin(line):
    match = re.search(r'(?<![\w:/])https://[a-z0-9]+(?:-[a-z0-9]+)*\.trycloudflare\.com(?=$|[\s|])', line)
    return match.group(0) if match else None


def read_origins(stream, origins):
    try:
        while True:
            line = stream.readline(4097)
            if not line:
                return
            if len(line) > 4096:
                while line and not line.endswith('\n'):
                    line = stream.readline(4097)
                continue
            origin = parse_origin(line)
            if origin:
                try:
                    origins.put_nowait(origin)
                except queue.Full:
                    pass
    except (OSError, ValueError, UnicodeError):
        pass


def print_ready(state, directory, no_print_private):
    print(f'Public origin: {state["origin"]}', flush=True)
    print(f'Private state directory: {directory}', flush=True)
    if not no_print_private and sys.stdout.isatty():
        print('Private access link: ' + state['origin'] + '/access/' + state['token'], flush=True)


def stop_process(process):
    if process is None:
        return
    if process.poll() is None:
        try:
            process.terminate()
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        try:
            process.kill()
        except ProcessLookupError:
            pass
        process.wait(timeout=3)


def main(argv=None):
    args = parse_args(argv)
    if not app_healthy(args.app_port):
        print('A healthy loopback app is required; run scripts/run-server.sh first.', file=sys.stderr)
        return 1
    binary = find_cloudflared()
    if not binary:
        print('cloudflared is required on PATH or in ~/bin; nothing was installed.', file=sys.stderr)
        return 1
    proxy = process = reader = serving = None
    stopping = threading.Event()
    previous_signals = {}
    try:
        directory = create_state_dir(args.state_dir)
        state = {'origin': None, 'token': secrets.token_urlsafe(32), 'expires_at': time.time() + args.ttl}
        write_state(directory, state)
        lease_deadline = time.monotonic() + args.ttl
        proxy = create_proxy(state, args.app_port)
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous_signals[signum] = signal.signal(signum, lambda *_: stopping.set())
        serving = threading.Thread(target=proxy.serve_forever, kwargs={'poll_interval': 0.2}, daemon=True)
        serving.start()
        process = subprocess.Popen(cloudflared_command(binary, proxy.server_port),
                                   stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, encoding='utf-8', errors='replace', bufsize=1,
                                   cwd=directory, env=cloudflared_env(directory))
        origins = queue.Queue(maxsize=1)
        reader = threading.Thread(target=read_origins, args=(process.stdout, origins), daemon=True)
        reader.start()
        ready_deadline = min(time.monotonic() + READINESS_SECONDS, lease_deadline)
        while not stopping.is_set():
            if process.poll() is not None:
                print('cloudflared exited before the lease ended.', file=sys.stderr)
                return 1
            if time.monotonic() >= ready_deadline:
                print('Tunnel did not become ready within its bounded readiness period.', file=sys.stderr)
                return 1
            try:
                origin = origins.get(timeout=0.1)
            except queue.Empty:
                continue
            state['origin'] = origin
            write_state(directory, state)
            print_ready(state, directory, args.no_print_private)
            break
        while not stopping.is_set():
            if process.poll() is not None:
                print('cloudflared exited before the lease ended.', file=sys.stderr)
                return 1
            if time.monotonic() >= lease_deadline:
                return 0
            stopping.wait(min(0.2, max(0, lease_deadline - time.monotonic())))
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception:
        print('Unable to run the tunnel; owned resources are being stopped.', file=sys.stderr)
        return 1
    finally:
        cleanup_failed = False
        try:
            stop_process(process)
        except Exception:
            cleanup_failed = True
        try:
            if reader:
                reader.join(timeout=3)
            if process and process.stdout and (not reader or not reader.is_alive()):
                process.stdout.close()
        except Exception:
            cleanup_failed = True
        if proxy:
            shutdown_errors = []
            def shutdown():
                try:
                    proxy.shutdown()
                except Exception:
                    shutdown_errors.append(True)
            try:
                if serving:
                    # Bound shutdown even if the serving thread failed before entering its loop.
                    closer = threading.Thread(target=shutdown, daemon=True)
                    closer.start()
                    closer.join(timeout=3)
                    cleanup_failed |= closer.is_alive() or bool(shutdown_errors)
                    serving.join(timeout=3)
            except Exception:
                cleanup_failed = True
            try:
                proxy.server_close()
            except Exception:
                cleanup_failed = True
        for signum, previous in previous_signals.items():
            try:
                signal.signal(signum, previous)
            except Exception:
                cleanup_failed = True
        if cleanup_failed:
            print('Owned tunnel cleanup could not complete within bounds.', file=sys.stderr)
            return 1


if __name__ == '__main__':
    sys.exit(main())
