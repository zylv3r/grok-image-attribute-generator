#!/usr/bin/env python3
"""Independently verify the physical preview inventory; never generates images."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
from PIL import Image, ImageStat

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--allow-partial', action='store_true')
    args = parser.parse_args()
    library = json.loads((ROOT / 'library.json').read_text())
    expected = {a['id'] + ':' + v['id'] for c in library['categories'] for a in c['attributes'] for v in a['values']}
    aids = {a['id'] for c in library['categories'] for a in c['attributes']}
    state = json.loads((ROOT / 'generated' / 'photographic-previews.json').read_text())
    assert set(state['tasks']) == expected, 'Task inventory mismatch'
    assert state['library_hash'] == hashlib.sha256((ROOT / 'library.json').read_bytes()).hexdigest()
    db = sqlite3.connect('file:' + str(ROOT / 'gallery.sqlite3') + '?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    completed = [task for task in state['tasks'].values() if task['status'] == 'completed']
    ids, hashes, dimensions = set(), {}, set()
    for task in completed:
        image_id = task['image_id']; assert image_id not in ids, 'Reused image ID'; ids.add(image_id)
        row = db.execute('SELECT * FROM images WHERE id=?', (image_id,)).fetchone(); assert row is not None
        selected = {task['attribute']: [task['value']]}
        assert json.loads(row['selections']) == selected
        assert row['library_hash'] == state['library_hash']
        assert task['thumbnail_url'] == '/generated/' + row['thumbnail']
        assert task['example_url'] == '/generated/' + row['filename']
        for field in ['filename', 'thumbnail']:
            path = ROOT / 'generated' / row[field]
            assert path.resolve().is_relative_to((ROOT / 'generated').resolve()) and not path.is_symlink()
            with Image.open(path) as image:
                assert image.format == 'JPEG'; image.load()
                assert abs(image.width / image.height - 1) <= .02
                if field == 'filename':
                    assert image.size == (row['width'], row['height'])
                    dimensions.add(image.size)
                    assert max(ImageStat.Stat(image.convert('RGB')).var) > 9, 'Near-blank image'
                else:
                    assert max(image.size) <= 320
        digest = hashlib.sha256((ROOT / 'generated' / row['filename']).read_bytes()).hexdigest()
        hashes.setdefault(digest, []).append(task['attribute'] + ':' + task['value'])
    atlas_count = 0
    for aid in aids:
        path = ROOT / 'generated' / 'preview-atlases' / (aid + '.jpg')
        if not path.exists(): continue
        assert not path.is_symlink()
        with Image.open(path) as image:
            assert image.format == 'JPEG'; image.load(); assert image.size == (320, 240)
        atlas_count += 1
    db.close()
    duplicate_groups = [group for group in hashes.values() if len(group) > 1]
    result = {'total':len(expected), 'verified_value_photos':len(completed), 'verified_attribute_sheets':atlas_count,
              'unique_photo_ids':len(ids), 'unique_photo_bytes':len(hashes), 'duplicate_groups':duplicate_groups,
              'dimensions':sorted(dimensions), 'failed':sum(t['status'] in {'failed','ambiguous'} for t in state['tasks'].values()),
              'status':state['status'], 'scope':'actual files, decoded pixels, catalog identity and read-only gallery rows; not universal visual-adherence proof'}
    print(json.dumps(result, indent=2))
    assert not duplicate_groups, 'Duplicate photographic outputs require review'
    assert state['completed'] == len(completed)
    if not args.allow_partial:
        assert len(completed) == len(expected) == 893
        assert atlas_count == len(aids) == 97
        assert state['status'] == 'completed' and result['failed'] == 0


if __name__ == '__main__': main()
