"""Offline real-catalog local previews: per-value pixels, provenance and rule contracts."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from PIL import Image

import catalog_v2
from comparisons import ComparisonStore


ROOT = Path(__file__).resolve().parent
LOCAL = {'hair_color', 'eye_color', 'fabric_color', 'focal_length', 'aperture',
         'shutter_motion', 'grain', 'focus_target', 'white_balance', 'highlight_rolloff',
         'color_grade', 'contrast', 'palette', 'editorial_mood'}


class LocalPreviewIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.library = copy.deepcopy(catalog_v2.load_bundle(ROOT)['library'])
        self.attributes = {a['id']: (c['id'], a) for c in self.library['categories']
                           for a in c['attributes']}
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'original.png'
        image = Image.new('RGBA', (72, 96))
        image.putdata([((x * 17 + y * 3) % 256, (y * 19 + x * 7) % 256,
                        (x * 11 + y * 13) % 256, 130 + (x + y) % 126)
                       for y in range(96) for x in range(72)])
        image.save(self.source)
        self.store = ComparisonStore(self.root)
        self.store.list_categories(self.library)
        self.provider = Mock(side_effect=AssertionError('Local effects never call providers'))

    def base(self, aid, image_id='owned-original'):
        cid, attr = self.attributes[aid]
        review = self.store.review(cid, attribute_id=aid)
        # Only a simulated-human attestation for this private pixel fixture.
        confirmations = ({'baseline_confirmations': list(review['baseline_requirements'])}
                         if review['baseline_requirements'] else {})
        self.store.set_base(cid, self.source, image_id, attribute_id=aid, **confirmations)
        return cid, attr

    def prepare(self, aid):
        cid, attr = self.base(aid)
        polygon = ([[0, 0], [1, 0], [1, 1], [0, 1]] if attr['preview_scope'] == 'global'
                   else [[.08, .08], [.65, .08], [.65, .8], [.08, .8]])
        self.store.set_mask(cid, aid, polygon)
        return cid, attr

    def test_every_value_has_native_valid_rules_and_executable_distinct_targets(self):
        catalog_v2.validate_library(self.library)
        self.assertEqual(sum(len(self.attributes[aid][1]['values']) for aid in LOCAL), 197)
        for aid in sorted(LOCAL):
            cid, attr = self.prepare(aid)
            hashes, signatures = set(), set()
            for value in attr['values']:
                with self.subTest(attribute=aid, value=value['id']):
                    self.assertIsNone(catalog_v2.validate_compatibility({aid: [value['id']]}, self.library))
                    self.assertTrue(value.get('preview_params') or value.get('colour'))
                    self.assertTrue(attr.get('preview_parameter_schema'))
                    result = self.store.render(cid, aid, value['id'], attr['preview_method'], {},
                                               aid + ':' + value['id'], self.library, self.provider)
                    receipt = result['receipt']
                    self.assertTrue(result['url'])
                    self.assertTrue(receipt['method_label'])
                    self.assertTrue(receipt['method_label'].startswith(attr['preview_method_label']))
                    self.assertEqual(receipt['method'], attr['preview_method'])
                    self.assertFalse(set(receipt['params']) - set(attr['preview_parameter_schema']['properties']))
                    self.assertFalse(set(attr['preview_parameter_schema']['required']) - set(receipt['params']))
                    self.assertEqual(receipt['outside_delta'], 0)
                    self.assertEqual(receipt['base_sha256'], self.store.review(cid, attribute_id=aid)['baseline']['sha256'])
                    if value.get('preview_baseline'):
                        self.assertEqual(receipt['status'], 'baseline')
                        self.assertEqual(receipt['effect_role'], 'baseline')
                        self.assertEqual(receipt['inside_change']['changed_pixels'], 0)
                        self.assertEqual(receipt['output_sha256'], receipt['base_sha256'])
                    else:
                        self.assertEqual(receipt['status'], 'staged')
                        self.assertGreater(receipt['inside_change']['changed_pixels'], 0)
                    with Image.open(self.store.asset(result['id'])) as output, Image.open(self.source) as original:
                        self.assertEqual(output.getchannel('A').tobytes(), original.getchannel('A').tobytes())
                    signatures.add(json.dumps(receipt['params'], sort_keys=True))
                    hashes.add(receipt['output_sha256'])
            # Equivalent explicitly declared baselines can share pixels; effect choices cannot collapse.
            baseline_count = sum(bool(v.get('preview_baseline')) for v in attr['values'])
            expected = len(attr['values']) - max(0, baseline_count - 1)
            self.assertGreaterEqual(len(hashes), expected, aid)
            self.assertGreaterEqual(len(signatures), expected, aid)
        self.provider.assert_not_called()

    def test_hair_iris_and_fabric_rgb_are_explicit_artistic_targets(self):
        for aid, count in [('hair_color', 44), ('eye_color', 27), ('fabric_color', 16)]:
            attr = self.attributes[aid][1]
            self.assertEqual(len(attr['values']), count)
            self.assertIn('illustrative', attr['palette_policy'].lower())
            for value in attr['values']:
                self.assertRegex(value['colour']['hex'], r'^#[0-9a-f]{6}$')
                if aid == 'fabric_color':
                    self.assertEqual(value['colour']['hex'], '#' + ''.join(f'{c:02x}' for c in value['swatch']['rgb']))

    def test_editorial_preserves_selected_components_in_pixels_and_receipt(self):
        cid, attr = self.prepare('editorial_mood')
        for value in attr['values']:
            result = self.store.render(cid, attr['id'], value['id'], attr['preview_method'], {},
                                       value['id'], self.library)
            receipt = result['receipt']
            self.assertEqual(receipt['recipe_components'], value['recipe']['selections'])
            for key, aid in [('grade', 'color_grade'), ('contrast', 'contrast')]:
                selected = value['recipe']['selections'][aid][0]
                component = next(v for v in self.attributes[aid][1]['values'] if v['id'] == selected)
                self.assertEqual(receipt['params'][key], component['preview_params'])
            self.assertIn('global colour and tone', receipt['allowed_effects'])
            self.assertIn('global colour and tone', receipt['target_contract']['allowed_changes'])

    def test_recipe_pixels_preserve_warm_component_and_never_chain_previous_output(self):
        cid, attr = self.prepare('color_grade')
        warm = self.store.render(cid, 'color_grade', 'warm_grade', attr['preview_method'], {},
                                 'warm-component', self.library)
        # Render a very different preceding grade to catch output/reference chaining.
        self.store.render(cid, 'color_grade', 'monochrome', attr['preview_method'], {},
                          'preceding-monochrome', self.library)
        mood_cid, mood_attr = self.prepare('editorial_mood')
        result = self.store.render(mood_cid, 'editorial_mood', 'warm_documentary', mood_attr['preview_method'], {},
                                   'warm-recipe', self.library)
        with Image.open(self.source) as original, Image.open(self.store.asset(warm['id'])) as grade:
            expected = Image.blend(original, grade, .8)
        with Image.open(self.store.asset(result['id'])) as actual:
            self.assertEqual(actual.tobytes(), expected.tobytes())

    def test_schema_and_explicit_overrides_keep_other_recipe_components(self):
        cid, attr = self.prepare('editorial_mood')
        result = self.store.render(cid, 'editorial_mood', 'sensual_luxe', attr['preview_method'],
                                   {'grade': {'saturation': .8}}, 'adjusted-recipe', self.library)
        self.assertEqual(result['receipt']['params']['grade']['temperature'], .2)
        self.assertEqual(result['receipt']['params']['grade']['saturation'], .8)
        self.assertEqual(result['receipt']['params']['contrast']['highlights'], -22)
        for index, params in enumerate([{'grade': {'prompt': 'invent a scene'}}, {'mix': -1},
                {'grade': {'shadow_tint': [0, 0]}}, {'contrast': {'slope': 3}},
                {'grade': {'temperature': True}}, {'image_path': str(self.source)}]):
            with self.subTest(params=params), self.assertRaises(ValueError):
                self.store.render(cid, 'editorial_mood', 'sensual_luxe', attr['preview_method'],
                                  params, 'bad-params-' + str(index), self.library, self.provider)
        self.provider.assert_not_called()

    def test_catalog_baseline_does_not_allow_empty_custom_effect_or_publication(self):
        cid, attr = self.prepare('grain')
        with self.assertRaisesRegex(ValueError, 'empty'):
            self.store.render(cid, 'grain', 'fine_grain', attr['preview_method'], {'amount': 0},
                              'not-a-baseline', self.library)
        baseline = self.store.render(cid, 'grain', 'clean_digital', attr['preview_method'], {},
                                     'baseline', self.library)
        review = self.store.review(cid, attribute_id='grain')
        self.store.approve(cid, 'contract', review['contract_hash'], attribute_id='grain',
                           approval_note='Simulated-human fixture review of original and mask')
        with self.assertRaisesRegex(ValueError, 'target-effect mismatch'):
            self.store.approve(cid, 'pilot', review['contract_hash'], [baseline['id']],
                               attribute_id='grain',
                               approval_note='Unchanged source cannot be accepted as an effect')
        # An unchanged baseline comparison must not poison later original-base selection.
        self.base('eye_color', 'same-owned-original')

    def test_depth_and_motion_require_local_masks_and_explicit_declarations(self):
        for aid, declaration in [('aperture', 'depth_assumption'), ('focus_target', 'depth_assumption'),
                                 ('shutter_motion', 'moving_region')]:
            cid, attr = self.base(aid, 'original')
            value = attr['values'][-1]
            with self.assertRaisesRegex(ValueError, 'mask'):
                self.store.render(cid, aid, value['id'], attr['preview_method'], {}, 'missing-' + aid, self.library)
            with self.assertRaisesRegex(ValueError, 'wholeframe'):
                self.store.set_mask(cid, aid, [[0, 0], [1, 0], [1, 1], [0, 1]])
            self.store.set_mask(cid, aid, [[.1, .1], [.6, .1], [.6, .8], [.1, .8]])
            with self.assertRaises(ValueError):
                self.store.render(cid, aid, value['id'], attr['preview_method'], {declaration: ''},
                                  'undeclared-' + aid, self.library)


if __name__ == '__main__':
    unittest.main()
