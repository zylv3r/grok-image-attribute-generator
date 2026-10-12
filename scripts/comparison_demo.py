#!/usr/bin/env python3
"""Offline synthetic PNG demo; no private media, credentials, provider or publication.

Run with the installed Pillow environment:
  /home/renriquez/.hermes/hermes-agent/venv/bin/python scripts/comparison_demo.py
  ... scripts/comparison_demo.py --output /tmp/atelier-comparison-demo

The output includes staged masters, mask overlays, a contact sheet and complete receipts.
All categories remain draft. Operator baseline/mask approval, pilot acceptance and
publication are separate ComparisonStore.approve calls made by the authenticated UI.
"""
import argparse
import json
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from comparisons import ComparisonStore


def run(destination):
    destination = Path(destination).absolute()
    if destination.is_symlink() or destination.exists() and any(destination.iterdir()):
        raise ValueError('Demo output must be a new or empty directory')
    destination.mkdir(parents=True, exist_ok=True)
    settings = {
        'grain': {'seed': 42, 'amount': 12},
        'white_balance': {'temperature': .4, 'tint': .05},
        'gentlehighlight_rolloff': {'strength': .6, 'threshold': .55},
        'focal_fov': {'factor': 1.5},
        'focus_depth_blur': {'radius': 3, 'depth_assumption': 'Synthetic backdrop plane behind subject'},
        'aperture_blur': {'radius': 5, 'depth_assumption': 'Single backdrop depth plane; fixed brightness'},
        'motion_blur': {'distance': 10, 'direction': 35, 'moving_region': 'Synthetic lower cloth, mask includes swept footprint'},
    }
    library = {'categories': [
        {'id': 'hair', 'name': 'Synthetic hair pigment demo', 'attributes': [
            {'id': 'pigment', 'preview_method': 'masked_recolor', 'preview_scope': 'localized',
             'values': [{'id': 'copper', 'colour': {'hex': '#ae5529'}},
                        {'id': 'ash', 'colour': {'hex': '#776c60'}}]}]},
        {'id': 'optics', 'name': 'Synthetic optical demos', 'attributes': [
            {'id': method, 'preview_method': method,
             'preview_scope': 'localized' if method in ('focus_depth_blur', 'aperture_blur', 'motion_blur') else 'global',
             'values': [{'id': 'demo'}]} for method in settings]},
        {'id': 'fabric', 'name': 'Illustrative texture swatch', 'attributes': [
            {'id': 'color', 'preview_method': 'fabric_swatch', 'preview_scope': 'swatch',
             'values': [{'id': 'purple', 'colour': {'hex': '#905479'}}]}]},
    ]}
    (destination / 'library.json').write_text(json.dumps(library, indent=2) + '\n')
    source = destination / 'generated' / 'synthetic-original.png'
    source.parent.mkdir()
    scene = Image.new('RGB', (256, 320))
    scene.putdata([(80 + (x * 3 + y * 5) % 150, 90 + (x * 7 + y) % 130,
                    100 + (x + y * 4) % 130) for y in range(320) for x in range(256)])
    draw = ImageDraw.Draw(scene)
    draw.ellipse((68, 25, 188, 175), fill=(62, 50, 39))
    draw.ellipse((87, 65, 169, 171), fill=(200, 152, 120))
    draw.polygon([(84, 166), (171, 166), (214, 307), (39, 307)], fill=(63, 96, 130))
    for y in range(167, 305, 5):
        draw.line((70, y, 187, y), fill=(73 + y % 20, 108, 139))
    for x in range(75, 185, 4):
        draw.line((x, 38, x, 68), fill=(78 + x % 30, 63, 49))
    scene.save(source, 'PNG')
    store = ComparisonStore(destination)
    hair = store.set_base('hair', source, 'synthetic-original', 'synthetic-declared-woman-1')
    hair = store.set_mask('hair', 'pigment', [[.29, .1], [.71, .1], [.71, .21], [.29, .21]])
    store.set_base('optics', source, 'synthetic-original', 'synthetic-declared-woman-1')
    # Draw every footprint before any output, so all outputs share one frozen contract.
    for method in settings:
        if method in ('focus_depth_blur', 'aperture_blur'):
            polygon = [[.02, .1], [.23, .1], [.23, .9], [.02, .9]]
        elif method == 'motion_blur':
            polygon = [[.3, .6], [.7, .6], [.75, .93], [.25, .93]]
        else:
            polygon = [[0, 0], [1, 0], [1, 1], [0, 1]]
        store.set_mask('optics', method, polygon)
    artifacts = []
    for color in ('copper', 'ash'):
        artifacts.append(store.render('hair', 'pigment', color, 'masked_recolor', {}, 'demo-' + color, library))
    for method, params in settings.items():
        artifacts.append(store.render('optics', method, 'demo', method, params, 'demo-' + method, library))
    artifacts.append(store.render('fabric', 'color', 'purple', 'fabric_swatch', {}, 'demo-fabric', library))
    cards = [('Original synthetic scene', store.asset(hair['baseline']['asset_id'])),
             ('Operator-drawn mask overlay', store.asset(hair['masks']['pigment']['overlay_asset_id']))]
    cards.extend((a['receipt']['method_label'], store.asset(a['id'])) for a in artifacts)
    card_width, card_height, columns = 300, 360, 4
    sheet = Image.new('RGB', (card_width * columns, card_height * ((len(cards) + columns - 1) // columns)), 'white')
    pen = ImageDraw.Draw(sheet)
    for i, (title, path) in enumerate(cards):
        with Image.open(path) as im:
            im = im.convert('RGB')
            im.thumbnail((256, 310))
            left, top = (i % columns) * card_width, (i // columns) * card_height
            sheet.paste(im, (left + (card_width - im.width) // 2, top + 45))
            words, lines, line = title.split(), [], ''
            for word in words:
                if len(line) + len(word) > 42:
                    lines.append(line)
                    line = ''
                line += (' ' if line else '') + word
            lines.append(line)
            pen.multiline_text((left + 8, top + 4), '\n'.join(lines), fill='black')
    sheet.save(destination / 'contact-sheet.png', 'PNG')
    report = {'kind': 'offline_synthetic_draft_demo', 'provider_calls': 0,
              'catalog_publications': 0, 'artifacts': artifacts,
              'reviews': {c['id']: store.review(c['id']) for c in library['categories']}}
    (destination / 'receipts.json').write_text(json.dumps(report, indent=2) + '\n')
    if any(a['receipt']['outside_delta'] != 0 or a['accepted'] for a in artifacts):
        raise AssertionError('Draft demo invariants violated')
    summary = {'output': str(destination), 'artifacts': len(artifacts),
               'outside_delta': 0, 'provider_calls': 0, 'published': 0,
               'contact_sheet': str(destination / 'contact-sheet.png')}
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', help='New/empty output directory (default: temporary directory)')
    args = parser.parse_args()
    run(args.output or tempfile.mkdtemp(prefix='atelier-comparison-demo-'))
