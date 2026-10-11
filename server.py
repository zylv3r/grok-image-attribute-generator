#!/usr/bin/env python3
"""Serve the attribute UI and route generation through Hermes' xAI provider."""
from __future__ import annotations

import base64
import json
import mimetypes
import os
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4
from urllib.parse import urlparse
import sys

ROOT = Path(__file__).resolve().parent
GENERATED_DIR = ROOT / 'generated'
HERMES_SOURCE = Path(os.environ.get('HERMES_SOURCE', Path.home() / '.hermes' / 'hermes-agent'))
if str(HERMES_SOURCE) not in sys.path:
    sys.path.insert(0, str(HERMES_SOURCE))


XAI_ASPECT_RATIOS = {'1:1', '16:9', '9:16', '4:3', '3:4', '3:2', '2:3'}


def generate_native_image(prompt: str, aspect_ratio: str) -> tuple[str, str]:
    """Generate through Hermes' xAI OAuth credentials without exposing them to the browser."""
    import requests
    from hermes_cli.config import load_config
    from tools.xai_http import hermes_xai_user_agent, resolve_xai_http_credentials

    credentials = resolve_xai_http_credentials()
    bearer = str(credentials.get('api_key') or '').strip()
    if not bearer:
        raise RuntimeError('No Hermes xAI OAuth credentials are available')
    config = load_config().get('image_gen', {}).get('xai', {})
    model = str(config.get('model') or 'grok-imagine-image-quality')
    resolution = str(config.get('resolution') or '1k')
    response = requests.post(
        f"{str(credentials.get('base_url') or 'https://api.x.ai/v1').rstrip('/')}/images/generations",
        headers={
            'Authorization': f'Bearer {bearer}',
            'Content-Type': 'application/json',
            'User-Agent': hermes_xai_user_agent(),
        },
        json={'model': model, 'prompt': prompt, 'aspect_ratio': aspect_ratio, 'resolution': resolution},
        timeout=120,
    )
    response.raise_for_status()
    data = response.json().get('data') or []
    if not data:
        raise RuntimeError('xAI returned no image data')
    first = data[0]
    if first.get('b64_json'):
        return first['b64_json'], 'image/jpeg'
    if first.get('url'):
        image = requests.get(first['url'], timeout=60)
        image.raise_for_status()
        return base64.b64encode(image.content).decode('ascii'), image.headers.get('Content-Type', 'image/jpeg')
    raise RuntimeError('xAI returned neither image bytes nor a URL')


def generate_batch(payload: dict, output_dir: Path) -> dict:
    prompt = str(payload.get('prompt', '')).strip()
    if not prompt:
        raise ValueError('prompt is required')
    n = payload.get('n', 1)
    if isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= 4:
        raise ValueError('n must be an integer between 1 and 4')

    aspect_ratio = str(payload.get('aspect_ratio', '9:16'))
    if aspect_ratio not in XAI_ASPECT_RATIOS:
        raise ValueError('aspect_ratio must be one of: ' + ', '.join(sorted(XAI_ASPECT_RATIOS)))

    output_dir.mkdir(parents=True, exist_ok=True)
    data = []
    for _ in range(n):
        encoded, mime = generate_native_image(prompt, aspect_ratio)
        extension = '.png' if mime == 'image/png' else '.jpg'
        name = f'{uuid4().hex}{extension}'
        (output_dir / name).write_bytes(base64.b64decode(encoded))
        data.append({'url': f'/generated/{name}'})
    return {'data': data}


class AppHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def _json(self, status: HTTPStatus, body: dict) -> None:
        raw = json.dumps(body).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self) -> None:
        if urlparse(self.path).path != '/api/generate':
            self._json(HTTPStatus.NOT_FOUND, {'error': 'not found'})
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if length > 200_000:
                raise ValueError('request body is too large')
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError('request body must be an object')
            self._json(HTTPStatus.OK, generate_batch(payload, GENERATED_DIR))
        except ValueError as exc:
            self._json(HTTPStatus.BAD_REQUEST, {'error': str(exc)})
        except Exception as exc:
            self._json(HTTPStatus.BAD_GATEWAY, {'error': f'Hermes generation failed: {exc}'})

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith('/generated/'):
            name = Path(parsed.path).name
            target = GENERATED_DIR / name
            if not target.is_file():
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            mime = mimetypes.guess_type(target.name)[0] or 'application/octet-stream'
            payload = target.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        super().do_GET()


def main() -> None:
    host = os.environ.get('HOST', '127.0.0.1')
    port = int(os.environ.get('PORT', '8123'))
    GENERATED_DIR.mkdir(exist_ok=True)
    print(f'Open http://{host}:{port} in a browser. Images are generated through Hermes xAI OAuth.')
    ThreadingHTTPServer((host, port), AppHandler).serve_forever()


if __name__ == '__main__':
    main()
