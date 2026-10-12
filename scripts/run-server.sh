#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
if [[ "${1:-}" == --help || "${1:-}" == -h ]]; then
  echo 'Usage: scripts/run-server.sh [--check | --foreground | --help]'
  echo 'PORT defaults to 8123. PYTHON_BIN overrides Python. --check changes no state.'
  exit 0
fi
if [[ -n "${PYTHON_BIN:-}" ]]; then
  PYTHON="$PYTHON_BIN"
elif [[ -x "$HOME/.hermes/hermes-agent/venv/bin/python" ]]; then
  PYTHON="$HOME/.hermes/hermes-agent/venv/bin/python"
elif [[ -x "$HOME/.local/share/hermes-owner/home/.hermes/hermes-agent/venv/bin/python" ]]; then
  PYTHON="$HOME/.local/share/hermes-owner/home/.hermes/hermes-agent/venv/bin/python"
else
  PYTHON=python3
fi
if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo 'Python unavailable; set PYTHON_BIN to a Python with Pillow and requests.' >&2
  exit 1
fi
exec "$PYTHON" - "$ROOT" "$@" <<'PY'
import os
import http.client
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time

root = Path(sys.argv[1])
args = sys.argv[2:]
def fail(message):
    print(message, file=sys.stderr)
    sys.exit(1)
if args not in ([], ['--check'], ['--foreground']):
    fail('Usage: scripts/run-server.sh [--check | --foreground | --help]')
raw_port = os.environ.get('PORT', '8123')
normalized_port = raw_port.lstrip('0') or '0'
if (not raw_port.isascii() or not raw_port.isdigit() or len(normalized_port) > 5
        or not 1 <= int(normalized_port) <= 65535):
    fail('PORT must be an integer from 1 through 65535.')
port = int(normalized_port)
try:
    import PIL.Image
    import requests
except ImportError:
    fail('Python requires Pillow and requests; select an installed environment with PYTHON_BIN.')
unit = 'atelier-image-studio.service'
def systemctl(*arguments):
    try:
        return subprocess.run(['systemctl', '--user', *arguments], capture_output=True,
                              text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
def property_value(name):
    result = systemctl('show', unit, '-p', name, '--value')
    return result.stdout.strip() if result and result.returncode == 0 else ''
def healthy():
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=2)
    try:
        conn.request('GET', '/api/health')
        response = conn.getresponse()
        raw = response.read(65537)
        return (response.status == 200 and len(raw) <= 65536
                and json.loads(raw).get('status') == 'ok')
    except (OSError, ValueError, AttributeError, http.client.HTTPException):
        return False
    finally:
        conn.close()
matching = False
if args != ['--foreground'] and port == 8123 and shutil.which('systemctl'):
    if property_value('LoadState') == 'loaded':
        directory = property_value('WorkingDirectory')
        matching = bool(directory) and Path(directory).resolve() == root
if matching:
    active = systemctl('is-active', '--quiet', unit)
    if active and active.returncode == 0:
        if not healthy():
            fail('Installed service is active but its health probe failed; nothing was restarted.')
        print(f'Healthy existing service: http://127.0.0.1:{port}; {root}')
        sys.exit(0)
try:
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', port))
except OSError:
    fail(f'Port {port} is unavailable; choose a free PORT. Nothing was stopped.')
index = root / 'dist/index.html'
inputs = [root / name for name in ('package.json', 'package-lock.json', 'index.html')]
inputs += list(root.glob('vite.config.*')) + list(root.glob('tsconfig*.json'))
inputs += [path for path in (root / 'src').rglob('*') if path.is_file()]
stale = not index.is_file() or any(path.is_file() and path.stat().st_mtime > index.stat().st_mtime
                                  for path in inputs)
missing_deps = any(not (root / 'node_modules/.bin' / name).exists() for name in ('vite', 'tsc'))
if stale or missing_deps:
    if not shutil.which('npm'):
        fail('UI needs building; install Node/npm before launching.')
    if not (root / 'package-lock.json').is_file():
        fail('UI needs package-lock.json for npm ci.')
    if args == ['--check']:
        fail('UI is absent/stale or dependencies are missing; run the launcher to npm ci/build.')
    try:
        if missing_deps:
            subprocess.run(['npm', 'ci'], cwd=root, check=True)
        subprocess.run(['npm', 'run', 'build'], cwd=root, check=True)
    except (OSError, subprocess.CalledProcessError):
        fail('UI build failed; server was not started.')
if args == ['--check']:
    print(f'Prerequisites OK: {root}; loopback port {port}')
    sys.exit(0)
if matching:
    started = systemctl('start', unit)
    if not started or started.returncode:
        fail('Unable to start installed service.')
    deadline = time.monotonic() + 30
    while not healthy():
        if time.monotonic() >= deadline:
            fail('Service started but health probe failed; inspect it without restarting paid jobs.')
        time.sleep(0.25)
    print(f'Healthy service: http://127.0.0.1:{port}; {root}')
    sys.exit(0)
env = dict(os.environ, HOST='127.0.0.1', PORT=str(port))
if not env.get('HERMES_HOME'):
    owner = Path.home() / '.local/share/hermes-owner/home'
    env['HERMES_HOME'] = str(owner if owner.is_dir() else Path.home() / '.hermes')
os.chdir(root)
os.execvpe(sys.executable, [sys.executable, str(root / 'server.py')], env)
PY
