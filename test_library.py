"""Catalog contract and SVG asset checks; no server, credentials or network."""
import hashlib
import importlib.util
import json
import os
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent
SVG = '{http://www.w3.org/2000/svg}'

# Every pre-expansion ID is a saved-selection compatibility contract. Value IDs
# are scoped to their attribute (on/off are intentionally shared by booleans).
LEGACY = {
    'skin': {'skin_tone': 'pale_pinkish porcelain fair', 'freckles': 'on prominent off', 'micro_texture': 'on off'},
    'hair': {'hair_color': 'golden_blonde light_auburn_copper platinum ash_blonde', 'hair_style': 'messy_waves soft_waves straight'},
    'outfit': {'fabric_color': 'pale_pink emerald deep_red ivory champagne black sage', 'drape_effect': 'on off', 'high_slit': 'on off', 'dress_style': 'slip bodycon off_shoulder'},
    'pose': {'pose': 'hands_on_hips weight_shift over_shoulder adjusting_strap finger_near_lips seated three_quarter leaning looking_back hand_in_hair arms_relaxed slight_arch'},
    'scenery': {'scenery': 'window_left garden_path balcony meadow apartment terrace library rainy_window loft courtyard hallway bedroom_window'},
    'phenotype': {'ethnic_inspiration': 'slavic_inspired scandinavian_inspired northern_european_blend', 'complexion_detail': 'porcelain_cool_pink pale_pink_freckled fair_clear', 'cheekbones': 'prominent_soft defined_natural', 'eye_color': 'icy_blue pale_green aqua gray_blue', 'eyelashes': 'dark_long soft_dark', 'facial_balance': 'delicate_harmonious ethereal_natural'},
    'editorial': {'silhouette': 'elegant_hourglass couture_hourglass slender_hourglass slender_toned_legs graceful_curves statuesque', 'face_direction': 'luminous classic_beauty confident soft_sultry', 'editorial_mood': 'quiet_luxury sensual_luxe cinematic_romance modern_glamour'},
    'technical': {'camera': 'on', 'age': '24'},
}


class PortraitLibraryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.library = json.loads((ROOT / 'library.json').read_text(encoding='utf-8'))
        cls.categories = cls.library['categories']
        cls.attributes = [a for c in cls.categories for a in c['attributes']]
        cls.by_id = {a['id']: a for a in cls.attributes}
        spec = importlib.util.spec_from_file_location('build_thumbnails', ROOT / 'scripts/build_thumbnails.py')
        cls.builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.builder)

    def test_catalog_counts_and_domain_coverage(self):
        self.assertGreaterEqual(len(self.categories), 18)
        self.assertGreaterEqual(len(self.attributes), 85)
        self.assertGreaterEqual(sum(len(a['values']) for a in self.attributes), 750)
        self.assertGreaterEqual(len(self.by_id['pose']['values']), 60)
        self.assertGreaterEqual(len(self.by_id['scenery']['values']), 80)
        required = {'skin_tone', 'hair_color', 'hair_style', 'hair_length', 'dress_style',
                    'fabric_material', 'neckline', 'sleeve_length', 'trouser_cut', 'shoe_style',
                    'light_direction', 'light_quality', 'focal_length', 'aperture', 'shot_size',
                    'face_shape', 'eye_color', 'expression', 'body_build', 'subject_placement',
                    'scenery', 'wall_surface', 'weather', 'hand_prop', 'photo_genre', 'focus_target'}
        self.assertTrue(required.issubset(self.by_id))

    def test_ids_names_and_schema_are_valid_and_unique(self):
        self.assertEqual(len(self.categories), len({c['id'] for c in self.categories}))
        self.assertEqual(len(self.attributes), len(self.by_id))
        self.assertEqual(len(self.attributes), len({a['name'].casefold() for a in self.attributes}))
        for category in self.categories:
            self.assertRegex(category['id'], r'^[a-z][a-z0-9_]*$')
            self.assertTrue(category['name'].strip())
            self.assertGreater(len(category['attributes']), 0)
        for attribute in self.attributes:
            with self.subTest(attribute=attribute['id']):
                self.assertRegex(attribute['id'], r'^[a-z][a-z0-9_]*$')
                self.assertIn(attribute['type'], {'exclusive', 'boolean', 'multi'})
                self.assertGreaterEqual(len(attribute['description']), 30)
                self.assertGreaterEqual(len(attribute['values']), 2)
                vals = attribute['values']
                self.assertEqual(len(vals), len({v['id'] for v in vals}))
                self.assertEqual(len(vals), len({v['name'].casefold() for v in vals}))
                self.assertEqual(len(vals), len({v['steers'].casefold() for v in vals}))
                for value in vals:
                    self.assertRegex(value['id'], r'^[a-z0-9][a-z0-9_]*$')
                    self.assertTrue(value['name'].strip())
                    self.assertGreaterEqual(len(value['description']), 20)
                    self.assertGreaterEqual(len(value['steers'].split()), 4)
                    self.assertNotRegex(value['steers'], r'(?i)\b(?:placeholder|lorem ipsum|option \d+|variant \d+)\b')

    def test_legacy_saved_selection_ids_are_preserved(self):
        category_map = {c['id']: {a['id']: a for a in c['attributes']} for c in self.categories}
        for cid, attributes in LEGACY.items():
            self.assertIn(cid, category_map)
            for aid, value_ids in attributes.items():
                self.assertIn(aid, category_map[cid])
                actual = {v['id'] for v in category_map[cid][aid]['values']}
                self.assertTrue(set(value_ids.split()).issubset(actual), aid)

    def test_primary_choices_and_boolean_contract(self):
        for aid in ('pose', 'scenery'):
            self.assertEqual(self.by_id[aid]['type'], 'exclusive')
        booleans = [a for a in self.attributes if a['type'] == 'boolean']
        self.assertGreaterEqual(len(booleans), 3)
        for attribute in booleans:
            self.assertEqual({v['id'] for v in attribute['values']}, {'on', 'off'})
            self.assertEqual(len(attribute['values']), 2)
            self.assertTrue(all(v['steers'].strip() for v in attribute['values']))

    def test_base_retains_adult_realism_and_opaque_fashion_without_fixed_traits(self):
        base = self.library['base_locks'].lower()
        always = self.library['always_on'].lower()
        self.assertIn('adult', base)
        self.assertIn('21 or older', base)
        self.assertIn('photorealistic', base)
        self.assertIn('opaque', base)
        self.assertIn('opaque', always)
        self.assertIn('nonexplicit', base)
        for text in (base, always):
            self.assertNotRegex(text, r'\b(?:24|blonde|auburn|orange hair|pale|porcelain|young|woman|50mm|f/2)\b')
        for v in self.by_id['hair_color']['values']:
            self.assertNotRegex(v['steers'], r'(?i)\b(?:long|short|waves|ponytail|bun)\b')
        for v in self.by_id['eye_color']['values']:
            self.assertNotRegex(v['steers'], r'(?i)\b(?:large|wide.set|catchlights)\b')
        self.assertGreaterEqual(len(self.by_id['age']['values']), 8)

    def asset_path(self, url):
        self.assertIsInstance(url, str)
        self.assertTrue(url.startswith('/thumbnails/'), url)
        path = PurePosixPath(url)
        self.assertNotIn('..', path.parts)
        self.assertNotIn('?', url)
        self.assertNotIn('#', url)
        target = ROOT / url.lstrip('/')
        self.assertTrue(target.is_file(), url)
        self.assertEqual(target.suffix, '.svg')
        self.assertTrue(target.resolve().is_relative_to(ROOT / 'thumbnails'))
        return target

    def test_every_thumbnail_is_local_safe_svg_with_guide_label(self):
        records = [record for a in self.attributes for record in [a, *a['values']]]
        paths = set()
        allowed_tags = {'svg', 'g', 'title', 'desc', 'rect', 'circle', 'ellipse', 'line', 'path', 'polygon', 'text'}
        for record in records:
            with self.subTest(record=record['id'], thumbnail=record.get('thumbnail')):
                path = self.asset_path(record['thumbnail'])
                self.assertNotIn(path, paths)
                paths.add(path)
                source = path.read_text(encoding='utf-8')
                self.assertNotRegex(source, r'(?i)<!DOCTYPE|<!ENTITY|<script|<foreignObject|javascript:|url\(')
                root = ET.fromstring(source)
                self.assertEqual(root.tag, SVG + 'svg')
                self.assertEqual(root.attrib['viewBox'], '0 0 320 242')
                self.assertIn('Illustrative steering guide', ''.join(root.itertext()))
                self.assertIn('Not an actual AI example', ''.join(root.itertext()))
                self.assertTrue(root.find(SVG + 'title').text)
                self.assertIn(record['description'], root.find(SVG + 'desc').text)
                for node in root.iter():
                    self.assertIn(node.tag.removeprefix(SVG), allowed_tags)
                    for key, value in node.attrib.items():
                        self.assertFalse(key.lower().startswith('on'), key)
                        self.assertNotIn('href', key.lower())
                        self.assertNotRegex(value, r'(?i)(?:https?://|data:|javascript:|url\()')
                        if key in {'width', 'height', 'r', 'rx', 'ry'}:
                            self.assertGreaterEqual(float(value), 0)
        self.assertEqual(paths, set((ROOT / 'thumbnails').rglob('*.svg')))

    def test_each_value_has_distinct_graphical_steering_within_its_attribute(self):
        for attribute in self.attributes:
            seen = {}
            for value in attribute['values']:
                root = ET.parse(self.asset_path(value['thumbnail'])).getroot()
                graphic = root.find(f"{SVG}svg[@data-art='steering']")
                self.assertIsNotNone(graphic)
                # Text cannot make a duplicated illustration pass this check.
                for parent in graphic.iter():
                    for child in list(parent):
                        if child.tag == SVG + 'text':
                            parent.remove(child)
                self.assertGreaterEqual(sum(1 for _ in graphic.iter()), 2)
                digest = hashlib.sha256(ET.tostring(graphic)).hexdigest()
                self.assertNotIn(digest, seen, f"Repeated graphic in {attribute['id']}: {seen.get(digest)} and {value['id']}")
                seen[digest] = value['id']

    def test_thumbnail_builder_is_reproducible_and_does_not_rewrite_library(self):
        library_bytes = (ROOT / 'library.json').read_bytes()
        with tempfile.TemporaryDirectory(prefix='thumbnail-test-', dir=os.environ.get('TMPDIR', tempfile.gettempdir())) as temp:
            output = Path(temp)
            count = self.builder.build(self.library, output)
            expected = sum(1 + len(a['values']) for a in self.attributes)
            self.assertEqual(count, expected)
            for path in output.rglob('*.svg'):
                self.assertEqual(path.read_bytes(), (ROOT / 'thumbnails' / path.relative_to(output)).read_bytes())
        self.assertEqual((ROOT / 'library.json').read_bytes(), library_bytes)


if __name__ == '__main__':
    unittest.main()
