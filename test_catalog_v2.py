"""Versioned catalog data, lossless migration and executable rule contracts.

These checks use local JSON fixtures only; they never read provider configuration
or generate photographs. The v1 digest pins the reviewed source bytes.
"""
import copy
import hashlib
import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import catalog_v2


ROOT = Path(__file__).resolve().parent
V1_SHA256 = '8e593b186c7ac5c68e49176771860bc9d0ab877da3029c0b426d2405c1552ea8'
CATEGORIES = {
    'hair', 'face_expression_makeup', 'eyes', 'skin_pigmentation',
    'body_avatar', 'wardrobe', 'poses', 'identity_controls', 'photography',
    'editorial_recipes', 'lighting_composition', 'environment_props',
}


def attributes(library):
    return {a['id']: a for c in library['categories'] for a in c['attributes']}


def values(attribute):
    return {v['id']: v for v in attribute['values']}


def rule_fixture():
    def attr(aid, ids):
        return {
            'id': aid, 'name': aid.replace('_', ' ').title(), 'type': 'exclusive',
            'description': 'A distinct choice whose allowed combinations are declared.',
            'control': 'select', 'preview_method': 'reference_edit',
            'preview_scope': 'localized', 'comparison_group': 'fixture',
            'values': [{'id': vid, 'name': vid.replace('_', ' ').title(),
                        'description': 'A visible target change confined to the reviewed region.',
                        'steers': 'Show ' + vid.replace('_', ' ') + ' with all other controls fixed.'}
                       for vid in ids],
        }
    result = {
        'categories': [{'id': 'fixture', 'name': 'Fixture', 'attributes': [
            attr('outerwear', ['none', 'coat']), attr('outerwear_length', ['none', 'long']),
            attr('hair_cut', ['buzz', 'long']), attr('hair_arrangement', ['down', 'bun']),
            attr('recipe', ['coat_recipe', 'neutral_recipe']),
        ]}],
        'base_locks': 'Same adult woman in an opaque outfit; fixed identity and camera.',
        'always_on': 'Natural photographic texture.',
        'compatibility_rules': [
            {'id': 'no_coat_length', 'when': {'outerwear': ['none']},
             'excludes': {'outerwear_length': ['long']},
             'message': 'A long outerwear length requires an outerwear garment.'},
            {'id': 'bun_requires_length', 'when': {'hair_arrangement': ['bun']},
             'requires': {'hair_cut': ['long']},
             'message': 'A bun requires sufficient hair length.'},
        ],
    }
    attributes(result)['recipe']['values'][0]['recipe'] = {
        'selections': {'outerwear': ['coat'], 'outerwear_length': ['long']},
        'allowed_component_changes': ['outerwear', 'outerwear_length'],
    }
    return result


class CatalogDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = catalog_v2.load_bundle(ROOT)
        if cls.bundle is None:
            raise AssertionError('Catalog v2 must be built and activated for the reviewed root.')
        cls.library = cls.bundle['library']
        cls.by_id = attributes(cls.library)
        cls.legacy = json.loads((ROOT / 'library.json').read_text())

    def test_v1_bytes_are_frozen_without_changing_root(self):
        root_bytes = (ROOT / 'library.json').read_bytes()
        self.assertEqual(hashlib.sha256(root_bytes).hexdigest(), V1_SHA256)
        self.assertEqual((ROOT / 'catalog/v1/library.json').read_bytes(), root_bytes)
        self.assertEqual(self.bundle['legacy_library'], self.legacy)

    def test_catalog_schema_counts_and_unique_ids(self):
        catalog_v2.validate_library(self.library)
        self.assertEqual({c['id'] for c in self.library['categories']}, CATEGORIES)
        all_attrs = [a for c in self.library['categories'] for a in c['attributes']]
        self.assertEqual(len(all_attrs), len(self.by_id))
        for attr in all_attrs:
            with self.subTest(attribute=attr['id']):
                self.assertEqual(len(attr['values']), len(values(attr)))
                self.assertEqual(len(attr['values']), len({v['name'].casefold() for v in attr['values']}))
                self.assertEqual(len(attr['values']), len({v['steers'].casefold() for v in attr['values']}))
                self.assertIn(attr['control'], {'swatch', 'range', 'select', 'cards'})
                for field in ('preview_method', 'preview_scope', 'comparison_group'):
                    self.assertTrue(attr.get(field), field)
                self.assertGreaterEqual(len(attr['description']), 20)
                for val in attr['values']:
                    self.assertGreaterEqual(len(val['description']), 20)
                    self.assertGreaterEqual(len(val['steers'].split()), 4)
                    self.assertNotRegex(val['steers'], r'(?i)\b(?:placeholder|lorem ipsum|variant \d+|option \d+)\b')
                    self.assertNotIn('/api/comparisons/', val.get('thumbnail', ''))

    def test_every_legacy_attribute_and_value_has_a_disposition(self):
        old_attrs = attributes(self.legacy)
        self.assertEqual(len(old_attrs), 97)
        self.assertEqual(sum(len(a['values']) for a in old_attrs.values()), 893)
        aliases = self.bundle['aliases']
        expected_pairs = {f'{aid}:{v["id"]}' for aid, a in old_attrs.items() for v in a['values']}
        self.assertEqual(set(aliases), expected_pairs)
        coverage = self.bundle['coverage']['attributes']
        self.assertEqual(set(coverage), set(old_attrs))
        for aid, record in coverage.items():
            self.assertIn(record['owner_category'], CATEGORIES)
            self.assertTrue(record['disposition'], aid)
        for aid, attr in old_attrs.items():
            for vid in values(attr):
                with self.subTest(attribute=aid, value=vid):
                    record = aliases[f'{aid}:{vid}']
                    self.assertTrue(record['disposition'])
                    self.assertIn('targets', record)
                    for target in record['targets']:
                        self.assertIn(target['attribute_id'], self.by_id)
                        self.assertIn(target['value_id'], values(self.by_id[target['attribute_id']]))

    def test_control_activation_preserves_preview_review_and_rollback_gate(self):
        active = json.loads((ROOT / 'catalog/v2/active.json').read_text())
        self.assertEqual(active['version'], 2)
        self.assertEqual(set(active['categories']), CATEGORIES)
        for cid, pointer in active['categories'].items():
            with self.subTest(category=cid):
                self.assertEqual(pointer['controls'], {
                    'version': 2, 'source': 'catalog/v2/library.json', 'status': 'active'})
                self.assertEqual(pointer['comparison_previews'], {
                    'status': 'awaiting_operator_review', 'source': None})
                self.assertEqual(pointer['previous'], {
                    'version': 1, 'source': 'catalog/v1/library.json'})

    def test_hair_is_reconciled_and_expression_is_one_movement_control(self):
        proposal = json.loads((ROOT / 'docs/plans/anchored-v2/HAIR-PROPOSAL.json').read_text())
        expected = {vid for family in proposal['base_color_values'].values() for vid in family}
        self.assertEqual(set(values(self.by_id['hair_color'])), expected)
        self.assertEqual(len(expected), 44)
        for aid in proposal['controls']:
            self.assertIn(aid, self.by_id)
        expressions = values(self.by_id['expression'])
        self.assertEqual(len(expressions), 43)
        self.assertNotIn('face_direction', self.by_id)
        for val in expressions.values():
            self.assertRegex(val['steers'].lower(), r'mouth|lip|brow|lid|cheek|eye')
        self.assertGreaterEqual(len(values(self.by_id['eye_color'])), 24)
        self.assertIn('iris_pattern', self.by_id)
        lash_contract = json.dumps(self.by_id['eyelashes']).lower()
        for requirement in ('close_eye', 'iris', 'geometry'):
            self.assertIn(requirement, lash_contract)

    def test_age_and_gender_are_generation_controls(self):
        age = self.by_id['age']
        self.assertEqual(age['type'], 'exclusive')
        self.assertEqual(age['control'], 'range')
        self.assertEqual(age['range'], {'min': 21, 'max': 85, 'step': 1})
        self.assertEqual(set(values(age)), {f'age_{n}' for n in range(21, 86)})
        gender = self.by_id['gender']
        self.assertEqual(gender['type'], 'exclusive')
        self.assertEqual(len(gender['values']), 3)
        self.assertEqual(gender['default'], 'woman')
        self.assertEqual(gender['preview_method'], 'control_only')
        self.assertEqual(len({v['steers'] for v in gender['values']}), 3)

    def test_body_wardrobe_pose_and_editorial_scope(self):
        owned = {c['id']: c['attributes'] for c in self.library['categories']}
        body = {a['id']: a for a in owned['body_avatar']}
        controls = [a for a in body.values() if not any('recipe' in v for v in a['values'])]
        self.assertGreaterEqual(len(controls), 14)
        body_names = ' '.join(body).lower()
        for component in ('bust', 'thigh', 'calf', 'glute', 'frame', 'waist', 'hip', 'muscle'):
            self.assertIn(component, body_names)
        self.assertGreaterEqual(sum(len(a['values']) for a in owned['wardrobe']), 340)
        wardrobe_ids = {v['id'] for a in owned['wardrobe'] for v in a['values']}
        self.assertFalse({'qipao_inspired', 'cheongsam_inspired'} <= wardrobe_ids)
        self.assertGreaterEqual(len(values(self.by_id['pose'])), 150)
        self.assertGreaterEqual(len(values(self.by_id['editorial_mood'])), 24)
        self.assertGreaterEqual(len(values(self.by_id['narrative'])), 32)
        for aid in ('ethnic_inspiration', 'complexion_detail', 'facial_balance'):
            self.assertNotIn(aid, self.by_id)
        for aid in ('editorial_mood', 'narrative'):
            for val in self.by_id[aid]['values']:
                self.assertTrue(val['recipe']['allowed_component_changes'])
                wardrobe_attrs = {a['id'] for a in owned['wardrobe']}
                self.assertFalse(wardrobe_attrs & set(val['recipe']['allowed_component_changes']))

    def test_palette_values_have_rgb_swatch_metadata(self):
        color = self.by_id['fabric_color']
        self.assertEqual(color['control'], 'swatch')
        for value in color['values']:
            swatch = value.get('swatch')
            self.assertIsNotNone(swatch)
            encoded = json.dumps(swatch)
            self.assertTrue('rgb' in encoded.lower() or '#' in encoded)
            self.assertEqual(len(swatch['rgb']), 3)
            self.assertTrue(all(isinstance(n, int) and 0 <= n <= 255 for n in swatch['rgb']))
            self.assertIn('same', swatch['texture'])

    def test_historical_filter_library_contains_all_legacy_vocabulary(self):
        historical = attributes(catalog_v2.historical_library(self.bundle))
        for aid, attr in attributes(self.legacy).items():
            self.assertIn(aid, historical)
            self.assertTrue(set(values(attr)) <= set(values(historical[aid])), aid)
        for aid, attr in self.by_id.items():
            self.assertTrue(set(values(attr)) <= set(values(historical[aid])), aid)

    def test_real_catalog_constraints_have_positive_and_negative_examples(self):
        cases = [
            ({'outerwear_style': ['none'], 'outerwear_length': ['none']},
             {'outerwear_style': ['none'], 'outerwear_length': ['knee_coat']}),
            ({'sleeve_length': ['none'], 'sleeve_shape': ['none']},
             {'sleeve_length': ['none'], 'sleeve_shape': ['puff']}),
            ({'neckline': ['strapless_secure'], 'collar': ['none']},
             {'neckline': ['strapless_secure'], 'collar': ['shirt_point']}),
            ({'high_slit': ['on'], 'garment_set': ['dress']},
             {'high_slit': ['on'], 'garment_set': ['separates_trousers']}),
            ({'shoe_style': ['ballet_flat'], 'heel_shape': ['flat']},
             {'shoe_style': ['ballet_flat'], 'heel_shape': ['stiletto']}),
            ({'hair_length': ['shaved'], 'hair_arrangement': ['worn_down']},
             {'hair_length': ['shaved'], 'hair_arrangement': ['low_bun']}),
            ({'hair_length': ['shaved'], 'hair_color_treatment': ['uniform']},
             {'hair_length': ['shaved'], 'hair_color_treatment': ['highlights']}),
            ({'garment_set': ['dress'], 'dress_silhouette': ['sheath'],
              'trouser_cut': ['straight'], 'layering': ['dress_over_trousers']},
             {'garment_set': ['dress'], 'dress_silhouette': ['sheath'], 'trouser_cut': ['straight']}),
            ({'garment_set': ['dress'], 'dress_silhouette': ['sheath'],
              'top_style': ['crewneck_tee'], 'layering': ['top_over_dress']},
             {'garment_set': ['dress'], 'dress_silhouette': ['sheath'], 'top_style': ['crewneck_tee']}),
        ]
        for valid, invalid in cases:
            with self.subTest(valid=valid, invalid=invalid):
                self.assertIsNone(catalog_v2.validate_compatibility(valid, self.library))
                self.assertIsInstance(catalog_v2.validate_compatibility(invalid, self.library), str)

    def test_every_real_recipe_is_generatable_without_contradictory_components(self):
        recipe_count = 0
        for aid, attr in self.by_id.items():
            for value in attr['values']:
                if 'recipe' in value:
                    recipe_count += 1
                    with self.subTest(attribute=aid, value=value['id']):
                        self.assertIsNone(catalog_v2.validate_compatibility(
                            {aid: [value['id']]}, self.library))
        self.assertGreaterEqual(recipe_count, 60)


class CatalogResolutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = catalog_v2.load_bundle(ROOT)
        if cls.bundle is None:
            raise AssertionError('Catalog v2 must be built before resolver verification.')

    def test_missing_bundle_leaves_custom_roots_on_v1(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertIsNone(catalog_v2.load_bundle(Path(directory)))
            (Path(directory) / 'library.json').write_text('{}')
            self.assertIsNone(catalog_v2.load_bundle(Path(directory)))

    def test_present_but_malformed_v2_is_rejected_instead_of_legacy_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / 'catalog/v2'
            destination.mkdir(parents=True)
            (destination / 'library.json').write_text('{not valid JSON')
            with self.assertRaises(ValueError):
                catalog_v2.load_bundle(Path(directory))

    def test_age_alias_and_current_draft_are_idempotent(self):
        raw = {'selections': {'age': ['24'], 'hair_color': ['platinum']},
               'whitelist': {'age': ['24', 'age_35']}, 'attributeModes': {'age': 'whitelist'},
               'future': {'retain': [True, None, {'nested': 'raw'}]}}
        original = copy.deepcopy(raw)
        resolved = catalog_v2.resolve_draft(raw, self.bundle)
        self.assertEqual(raw, original)
        self.assertEqual(resolved['draft']['selections']['age'], ['age_24'])
        self.assertEqual(resolved['draft']['whitelist']['age'], ['age_24', 'age_35'])
        self.assertEqual(resolved['draft']['future'], raw['future'])
        self.assertTrue(resolved['changes'])
        self.assertEqual(resolved['unresolved'], [])
        again = catalog_v2.resolve_draft(resolved['draft'], self.bundle)
        self.assertEqual(again['draft'], resolved['draft'])
        self.assertEqual(again['changes'], [])

    def test_unknown_retired_and_ambiguous_records_stay_displayable(self):
        raw = {'selections': {'ethnic_inspiration': ['slavic_inspired'],
                              'face_direction': ['luminous'], 'hair_style': ['side_part'],
                              'future_control': ['future_value']},
               'whitelist': {'future_control': ['future_value']},
               'attributeModes': {'future_control': 'whitelist'}, 'extra_prompt': 'preserve me'}
        original = copy.deepcopy(raw)
        result = catalog_v2.resolve_draft(raw, self.bundle)
        self.assertEqual(raw, original)
        self.assertTrue(result['unresolved'])
        report = json.dumps(result['unresolved'])
        for aid, selected in raw['selections'].items():
            self.assertEqual(result['draft']['selections'][aid], selected)
            self.assertIn(aid, report)
            self.assertIn(selected[0], report)
        self.assertEqual(result['draft']['extra_prompt'], 'preserve me')

    def test_compound_hair_recipe_cannot_overwrite_locked_parting(self):
        raw = {'selections': {'hair_style': ['sleek_center_part'], 'hair_parting': ['left']}}
        result = catalog_v2.resolve_draft(raw, self.bundle)
        self.assertEqual(result['draft']['selections']['hair_parting'], ['left'])
        self.assertTrue(result['unresolved'])
        self.assertIn('sleek_center_part', json.dumps(result['unresolved']))

    def test_every_legacy_value_migration_converges_in_one_resolution(self):
        for aid, attr in attributes(self.bundle['legacy_library']).items():
            for value in attr['values']:
                with self.subTest(attribute=aid, value=value['id']):
                    first = catalog_v2.resolve_draft({'selections': {aid: [value['id']]}}, self.bundle)
                    second = catalog_v2.resolve_draft(first['draft'], self.bundle)
                    self.assertEqual(second['draft'], first['draft'])
                    self.assertEqual(second['changes'], [])


class CatalogRuleTests(unittest.TestCase):
    def setUp(self):
        self.library = rule_fixture()

    def test_exclusion_and_requirement_rules_execute(self):
        self.assertIsNone(catalog_v2.validate_compatibility(
            {'outerwear': ['coat'], 'outerwear_length': ['long']}, self.library))
        conflict = catalog_v2.validate_compatibility(
            {'outerwear': ['none'], 'outerwear_length': ['long']}, self.library)
        self.assertEqual(conflict, 'A long outerwear length requires an outerwear garment.')
        self.assertEqual(catalog_v2.validate_compatibility(
            {'hair_arrangement': ['bun'], 'hair_cut': ['buzz']}, self.library),
            'A bun requires sufficient hair length.')
        self.assertIsNone(catalog_v2.validate_compatibility(
            {'hair_arrangement': ['bun'], 'hair_cut': ['long']}, self.library))

    def test_recipe_conflicts_report_instead_of_silently_overriding(self):
        self.assertIsNone(catalog_v2.validate_compatibility(
            {'recipe': ['coat_recipe'], 'outerwear': ['coat']}, self.library))
        conflict = catalog_v2.validate_compatibility(
            {'recipe': ['coat_recipe'], 'outerwear': ['none']}, self.library)
        self.assertIsInstance(conflict, str)
        self.assertIn('outerwear', conflict.lower())

    def test_recipe_components_participate_in_compatibility_rules(self):
        attributes(self.library)['recipe']['values'][0]['recipe']['selections'] = {
            'outerwear': ['none'], 'outerwear_length': ['long']}
        self.assertEqual(catalog_v2.validate_compatibility(
            {'recipe': ['coat_recipe']}, self.library),
            'A long outerwear length requires an outerwear garment.')

    def test_multi_condition_rule_triggers_only_when_all_conditions_match(self):
        self.library['compatibility_rules'] = [{
            'id': 'compound', 'when': {'outerwear': ['coat'], 'hair_cut': ['buzz']},
            'excludes': {'hair_arrangement': ['bun']},
            'message': 'This compound combination is unavailable.',
        }]
        self.assertIsNone(catalog_v2.validate_compatibility(
            {'outerwear': ['none'], 'hair_cut': ['buzz'], 'hair_arrangement': ['bun']}, self.library))
        self.assertEqual(catalog_v2.validate_compatibility(
            {'outerwear': ['coat'], 'hair_cut': ['buzz'], 'hair_arrangement': ['bun']}, self.library),
            'This compound combination is unavailable.')

    def test_schema_validation_rejects_duplicate_and_dangling_references(self):
        catalog_v2.validate_library(self.library)
        corruptions = []
        duplicate = copy.deepcopy(self.library)
        duplicate['categories'][0]['attributes'].append(copy.deepcopy(duplicate['categories'][0]['attributes'][0]))
        corruptions.append(duplicate)
        duplicate_value = copy.deepcopy(self.library)
        duplicate_value['categories'][0]['attributes'][0]['values'].append(copy.deepcopy(duplicate_value['categories'][0]['attributes'][0]['values'][0]))
        corruptions.append(duplicate_value)
        bad_rule = copy.deepcopy(self.library)
        bad_rule['compatibility_rules'][0]['excludes'] = {'missing_attribute': ['missing_value']}
        corruptions.append(bad_rule)
        bad_value = copy.deepcopy(self.library)
        bad_value['compatibility_rules'][0]['excludes'] = {'outerwear': ['missing_value']}
        corruptions.append(bad_value)
        bad_recipe = copy.deepcopy(self.library)
        attributes(bad_recipe)['recipe']['values'][0]['recipe']['selections'] = {'outerwear': ['missing_value']}
        corruptions.append(bad_recipe)
        bad_allowance = copy.deepcopy(self.library)
        attributes(bad_allowance)['recipe']['values'][0]['recipe']['allowed_component_changes'] = ['missing_attribute']
        corruptions.append(bad_allowance)
        for index, corrupted in enumerate(corruptions):
            with self.subTest(corruption=index), self.assertRaises(ValueError):
                catalog_v2.validate_library(corrupted)

    def test_invalid_active_selection_is_not_generatable(self):
        self.assertIsInstance(catalog_v2.validate_compatibility(
            {'outerwear': ['missing_value']}, self.library), str)
        self.assertIsInstance(catalog_v2.validate_compatibility(
            {'retired_attribute': ['historic']}, self.library), str)
        self.assertIsInstance(catalog_v2.validate_compatibility(
            {'outerwear': ['none', 'coat']}, self.library), str)

    def test_cyclic_recipes_and_self_exclusions_are_rejected(self):
        cyclic = copy.deepcopy(self.library)
        attributes(cyclic)['outerwear']['values'][1]['recipe'] = {
            'selections': {'recipe': ['coat_recipe']},
            'allowed_component_changes': ['recipe'],
        }
        with self.assertRaises(ValueError):
            catalog_v2.validate_library(cyclic)
        self_exclusion = copy.deepcopy(self.library)
        attributes(self_exclusion)['outerwear']['values'][0]['excludes'] = ['outerwear:none']
        with self.assertRaises(ValueError):
            catalog_v2.validate_library(self_exclusion)
        undeclared = copy.deepcopy(self.library)
        attributes(undeclared)['recipe']['values'][0]['recipe']['allowed_component_changes'] = ['outerwear']
        with self.assertRaises(ValueError):
            catalog_v2.validate_library(undeclared)

    def test_malformed_enum_payloads_raise_validation_errors(self):
        for field, malformed in [('type', ['exclusive']), ('control', {'future': 'cards'}),
                                 ('default', ['coat'])]:
            corrupted = copy.deepcopy(self.library)
            attributes(corrupted)['outerwear'][field] = malformed
            with self.subTest(field=field), self.assertRaises(ValueError):
                catalog_v2.validate_library(corrupted)


class SyntheticMigrationTests(unittest.TestCase):
    def setUp(self):
        self.bundle = {'library': rule_fixture(), 'aliases': {
            'old_upper:empty': {'disposition': 'move', 'targets': [
                {'attribute_id': 'outerwear', 'value_id': 'none'}]},
            'old_lower:covered': {'disposition': 'move', 'targets': [
                {'attribute_id': 'outerwear', 'value_id': 'coat'}]},
            'old_style:coat_long': {'disposition': 'disclosed_recipe', 'targets': [
                {'attribute_id': 'outerwear', 'value_id': 'coat'},
                {'attribute_id': 'outerwear_length', 'value_id': 'long'}]},
        }}

    def test_independent_whitelist_moves_union_pools_and_modes(self):
        raw = {'whitelist': {'old_upper': ['empty'], 'old_lower': ['covered']},
               'attributeModes': {'old_upper': 'whitelist', 'old_lower': 'whitelist'}}
        result = catalog_v2.resolve_draft(raw, self.bundle)
        self.assertEqual(result['draft']['whitelist'], {'outerwear': ['none', 'coat']})
        self.assertEqual(result['draft']['attributeModes'], {'outerwear': 'whitelist'})
        self.assertEqual(result['unresolved'], [])

    def test_active_recipe_expansion_is_idempotent_and_keeps_recipe_source(self):
        raw = {'selections': {'recipe': ['coat_recipe']}}
        first = catalog_v2.resolve_draft(raw, self.bundle)
        self.assertEqual(first['draft']['selections'], {
            'recipe': ['coat_recipe'], 'outerwear': ['coat'], 'outerwear_length': ['long']})
        self.assertTrue(first['changes'])
        self.assertEqual(first['unresolved'], [])
        second = catalog_v2.resolve_draft(first['draft'], self.bundle)
        self.assertEqual(second['draft'], first['draft'])
        self.assertEqual(second['changes'], [])
        self.assertEqual(second['unresolved'], [])

    def test_recipe_migration_is_atomic_when_later_component_conflicts(self):
        raw = {'selections': {'old_style': ['coat_long'], 'outerwear_length': ['none']}}
        result = catalog_v2.resolve_draft(raw, self.bundle)
        self.assertEqual(result['draft']['selections'], raw['selections'])
        self.assertEqual(result['changes'], [])
        self.assertTrue(result['unresolved'])

    def test_recipe_and_equivalent_simple_alias_converge_across_key_order(self):
        self.bundle['aliases']['outerwear:old_coat'] = {
            'disposition': 'move', 'targets': [{'attribute_id': 'outerwear', 'value_id': 'coat'}]}
        selections = [
            {'old_style': ['coat_long'], 'outerwear': ['old_coat']},
            {'outerwear': ['old_coat'], 'old_style': ['coat_long']},
        ]
        for selected in selections:
            with self.subTest(selected=selected):
                result = catalog_v2.resolve_draft({'selections': selected}, self.bundle)
                self.assertEqual(result['draft']['selections'], {
                    'outerwear': ['coat'], 'outerwear_length': ['long']})
                self.assertEqual(result['unresolved'], [])

    def test_alias_into_active_recipe_waits_for_equivalent_component_alias(self):
        self.bundle['aliases']['old_family:legacy_coat'] = {
            'disposition': 'move', 'targets': [{'attribute_id': 'recipe', 'value_id': 'coat_recipe'}]}
        self.bundle['aliases']['outerwear:old_coat'] = {
            'disposition': 'move', 'targets': [{'attribute_id': 'outerwear', 'value_id': 'coat'}]}
        for selected in [{'old_family': ['legacy_coat'], 'outerwear': ['old_coat']},
                         {'outerwear': ['old_coat'], 'old_family': ['legacy_coat']}]:
            with self.subTest(selected=selected):
                result = catalog_v2.resolve_draft({'selections': selected}, self.bundle)
                self.assertEqual(result['draft']['selections'], {
                    'recipe': ['coat_recipe'], 'outerwear': ['coat'], 'outerwear_length': ['long']})
                self.assertEqual(result['unresolved'], [])

    def test_coupled_recipe_whitelist_stays_raw_until_explicit_resolution(self):
        raw = {'whitelist': {'old_style': ['coat_long']}}
        result = catalog_v2.resolve_draft(raw, self.bundle)
        self.assertEqual(result['draft']['whitelist'], raw['whitelist'])
        self.assertEqual(result['changes'], [])
        self.assertTrue(result['unresolved'])

    def test_explicit_other_mode_with_empty_pool_is_a_lock(self):
        raw = {'selections': {'old_upper': ['empty']},
               'whitelist': {'outerwear': []}, 'attributeModes': {'outerwear': 'whitelist'}}
        result = catalog_v2.resolve_draft(raw, self.bundle)
        self.assertEqual(result['draft']['selections'], raw['selections'])
        self.assertEqual(result['draft']['whitelist'], raw['whitelist'])
        self.assertEqual(result['draft']['attributeModes'], raw['attributeModes'])
        self.assertEqual(result['changes'], [])
        self.assertTrue(result['unresolved'])

    def test_unsupported_raw_mode_payloads_remain_visible(self):
        for mode in [['whitelist'], {'future': 'mode'}]:
            raw = {'attributeModes': {'future': mode}}
            with self.subTest(mode=mode):
                result = catalog_v2.resolve_draft(raw, self.bundle)
                self.assertEqual(result['draft']['attributeModes'], raw['attributeModes'])
                self.assertTrue(result['unresolved'])

    def test_empty_unknown_controls_and_malformed_arrays_remain_archived(self):
        cases = [
            {'selections': {'future': []}, 'attributeModes': {'future': 'whitelist'}},
            {'selections': {'outerwear': [['coat']]}},
            {'selections': {'outerwear': [{'historic': 'coat'}], 'old_upper': ['empty']}},
            {'selections': {'hair_cut': [['buzz']], 'old_upper': ['empty']}},
        ]
        for raw in cases:
            original = copy.deepcopy(raw)
            with self.subTest(raw=raw):
                result = catalog_v2.resolve_draft(raw, self.bundle)
                self.assertEqual(raw, original)
                self.assertTrue(result['unresolved'])
                for aid, selected in raw['selections'].items():
                    if aid != 'old_upper':
                        self.assertEqual(result['draft']['selections'][aid], selected)


class CatalogBuildTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        shutil.copyfile(ROOT / 'library.json', self.root / 'library.json')
        plans = self.root / 'docs/plans/anchored-v2'
        plans.mkdir(parents=True)
        for name in ('HAIR-PROPOSAL.json', 'WARDROBE-PROPOSAL.json', 'COVERAGE.json', 'HAIR-MIGRATIONS.json'):
            shutil.copyfile(ROOT / 'docs/plans/anchored-v2' / name, plans / name)
        spec = importlib.util.spec_from_file_location('test_catalog_builder', ROOT / 'scripts/build_catalog_v2.py')
        self.builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.builder)

    def tearDown(self):
        self.temp.cleanup()

    def build(self):
        previous_path = sys.path[:]
        try:
            return self.builder.build(self.root)
        finally:
            sys.path[:] = previous_path

    def test_offline_build_reproduces_reviewed_bytes_and_preserves_unrelated_files(self):
        sentinel = self.root / 'generated/photos/operator-owned.jpg'
        sentinel.parent.mkdir(parents=True)
        sentinel.write_bytes(b'private photograph fixture remains unchanged')
        preset = self.root / 'presets.sqlite3'
        preset.write_bytes(b'private archived draft fixture remains unchanged')
        self.build()
        outputs = ['catalog/v1/library.json'] + [f'catalog/v2/{name}.json'
                   for name in ('library', 'aliases', 'retired', 'coverage', 'active')]
        first = {path: (self.root / path).read_bytes() for path in outputs}
        for path, content in first.items():
            self.assertEqual(content, (ROOT / path).read_bytes(), path)
        self.build()
        self.assertEqual({path: (self.root / path).read_bytes() for path in outputs}, first)
        self.assertEqual((self.root / 'library.json').read_bytes(), (ROOT / 'library.json').read_bytes())
        self.assertEqual(sentinel.read_bytes(), b'private photograph fixture remains unchanged')
        self.assertEqual(preset.read_bytes(), b'private archived draft fixture remains unchanged')

    def test_frozen_snapshot_mismatch_refuses_to_overwrite_history(self):
        self.build()
        frozen = self.root / 'catalog/v1/library.json'
        frozen.write_bytes(b'immutable historical snapshot fixture')
        active = (self.root / 'catalog/v2/library.json').read_bytes()
        with self.assertRaises(ValueError):
            self.build()
        self.assertEqual(frozen.read_bytes(), b'immutable historical snapshot fixture')
        self.assertEqual((self.root / 'catalog/v2/library.json').read_bytes(), active)

    def test_missing_alias_disposition_is_rejected_at_bundle_load(self):
        self.build()
        path = self.root / 'catalog/v2/aliases.json'
        ledger = json.loads(path.read_text())
        ledger.pop(next(iter(ledger)))
        path.write_text(json.dumps(ledger))
        with self.assertRaises(ValueError):
            catalog_v2.load_bundle(self.root)


class CatalogBundleIntegrityTests(unittest.TestCase):
    def test_bundle_rejects_inconsistent_history_coverage_retirement_and_activation(self):
        def mutate(document, operation):
            changed = copy.deepcopy(document)
            operation(changed)
            return changed

        cases = [
            ('retired', lambda d: d['values'].pop('hair_style:side_part')),
            ('retired', lambda d: d['attributes'].pop('hair_style')),
            ('coverage', lambda d: d['attributes']['skin_tone'].update(owner_category='hair')),
            ('coverage', lambda d: d['attributes']['age'].update(disposition='keep')),
            ('coverage', lambda d: d['attributes']['age']['value_dispositions'].update({'24': 'keep'})),
            ('coverage', lambda d: d['active_counts']['hair'].update(values=999)),
            ('coverage', lambda d: d.update(legacy_attribute_count=96)),
            ('coverage', lambda d: d.update(legacy_value_count=892)),
            ('coverage', lambda d: d.update(v1_sha256='0' * 64)),
            ('aliases', lambda d: d['age:24'].update(legacy_steer='altered archived wording')),
            ('active', lambda d: d.update(version=1)),
            ('active', lambda d: d['categories'].pop('hair')),
            ('active', lambda d: d['categories']['hair']['controls'].update(source='../../private/config.json')),
            ('active', lambda d: d['categories']['hair']['controls'].update(version=1)),
            ('active', lambda d: d['categories']['hair']['controls'].update(status='inactive')),
            ('active', lambda d: d['categories']['hair']['comparison_previews'].update(status='published')),
            ('active', lambda d: d['categories']['hair']['comparison_previews'].update(source='/api/comparisons/assets/fake.png')),
            ('active', lambda d: d['categories']['hair']['previous'].update(source='catalog/v2/library.json')),
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(ROOT / 'catalog', root / 'catalog')
            shutil.copyfile(ROOT / 'library.json', root / 'library.json')
            for index, (name, operation) in enumerate(cases):
                path = root / 'catalog/v2' / f'{name}.json'
                original = path.read_bytes()
                with self.subTest(case=index, document=name):
                    try:
                        path.write_text(json.dumps(mutate(json.loads(original), operation)))
                        with self.assertRaises(ValueError):
                            catalog_v2.load_bundle(root)
                    finally:
                        path.write_bytes(original)

    def test_root_and_frozen_v1_byte_divergence_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(ROOT / 'catalog', root / 'catalog')
            shutil.copyfile(ROOT / 'library.json', root / 'library.json')
            with (root / 'library.json').open('ab') as stream:
                stream.write(b'\n')
            with self.assertRaises(ValueError):
                catalog_v2.load_bundle(root)


if __name__ == '__main__':
    unittest.main()
