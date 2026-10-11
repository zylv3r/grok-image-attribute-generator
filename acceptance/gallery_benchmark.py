#!/usr/bin/env python3
"""Isolated synthetic metadata benchmark; NOT provider/image-generation evidence."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gallery import Gallery

with tempfile.TemporaryDirectory(prefix='atelier-gallery-benchmark-', dir=os.environ.get('TMPDIR')) as tmp:
    store = Gallery(Path(tmp) / 'fixture.sqlite3', Path(tmp) / 'images')
    count = 10000
    started = time.perf_counter()
    with store.connect() as db:
        for i in range(count):
            record = {'id': f'fixture-{i:05d}', 'filename': f'fixture-{i:05d}.jpg', 'thumbnail': f'fixture-{i:05d}-thumb.jpg', 'width': 720, 'height': 1280, 'aspect_ratio': '9:16'}
            tags = {'hair_color': ['golden_blonde' if i % 2 else 'ash_blonde'], 'scenery': ['garden_path' if i % 3 else 'library'], 'props': ['book', 'flower']}
            store._insert_image(db, record, 'synthetic garden fashion fixture' if i % 3 else 'synthetic library fashion fixture', tags)
    insert_ms = (time.perf_counter() - started) * 1000
    cases = [('all', {}, 10000), ('OR within hair', {'filters': {'hair_color': ['golden_blonde', 'ash_blonde']}}, 10000), ('AND across attributes', {'filters': {'hair_color': ['golden_blonde'], 'scenery': ['library']}}, len([i for i in range(count) if i % 2 and not i % 3])), ('multi tag dedup', {'filters': {'props': ['book', 'flower']}}, 10000), ('FTS', {'q': 'garden fashion'}, len([i for i in range(count) if i % 3]))]
    results = []
    for name, kwargs, expected in cases:
        start = time.perf_counter()
        response = store.query(page=1, page_size=24, **kwargs)
        elapsed = (time.perf_counter() - start) * 1000
        assert response['total'] == expected, (name, response['total'], expected)
        assert len(response['items']) <= 24
        assert elapsed < 2000, (name, elapsed)
        results.append({'case': name, 'total': response['total'], 'returned': len(response['items']), 'latency_ms': round(elapsed, 2)})
    p1, p2 = store.query(page=1), store.query(page=2)
    assert not set(x['id'] for x in p1['items']) & set(x['id'] for x in p2['items'])
    assert store.query(page=10000)['items'] == []
    print(json.dumps({'fixture_records': count, 'fixture_insert_ms': round(insert_ms, 2), 'cases': results, 'pagination': 'distinct ordered pages; out-of-range empty', 'evidence_type': 'isolated synthetic metadata benchmark, no paid generation'}, indent=2))
