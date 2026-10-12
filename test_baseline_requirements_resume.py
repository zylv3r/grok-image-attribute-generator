"""Offline human baseline metadata and byte-stable catalog regeneration.

No image detection, sockets, providers, runtime databases or configuration reads.
Builder outputs go only to an isolated temporary tree; workspace history is read-only.
"""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parent
BASE_LIBRARY_SEMANTIC_SHA256 = 'ff827f39d8b0b243b628fbc30392b4e5d80e1cd2a207f9d0ba87f0c39252b4c0'
FROZEN_SHA256 = {
    'library.json': '8e593b186c7ac5c68e49176771860bc9d0ab877da3029c0b426d2405c1552ea8',
    'catalog/v1/library.json': '8e593b186c7ac5c68e49176771860bc9d0ab877da3029c0b426d2405c1552ea8',
    'catalog/v2/active.json': 'dd11200c826f4c65017af5c0ecf1fe9c3b90adca4e593b991140ec80f05c7cc4',
    'catalog/v2/aliases.json': 'd7f710aa3bf31bb47a483543d45dd9c24a56a69353bf31fd596a260665e34199',
    'catalog/v2/coverage.json': '0159725c6069f7f397ebb357c6d346a86f6a790d0670a9dd5b8d2f43ddf433ff',
    'catalog/v2/retired.json': '26a298541e734979eee9448090e905c295ed91c90dcbd4e8a9615b27e427469c',
}
HAIR_REFERENCE_IDS = {
    'hair_length', 'hair_fringe', 'hair_accessory', 'hair_cut', 'hair_texture',
    'hair_arrangement', 'hair_parting', 'hair_finish', 'hair_color_treatment',
}
HAIR_ORIGINAL = (
    'Operator reviewed the immutable original of the same approved adult woman '
    'with neutral medium-brown uniform hair pigment.'
)
EYES_ORIGINAL = (
    'Operator reviewed the same approved close-eye view of the immutable original '
    'for every Eyes group, with the iris and lash boundary clearly visible.'
)
EYES_TARGETS = {
    'eye_color': 'Iris recoloring is confined to the reviewed iris mask; iris geometry, radial pattern and eyelashes remain unchanged.',
    'iris_pattern': 'Iris-pattern edits preserve iris pigment, pupil geometry, eye geometry and eyelashes.',
    'eyelashes': 'Lash edits preserve iris pigment, iris and pupil geometry, and non-target eye geometry.',
}
FACE_ORIGINAL = (
    'Operator reviewed the immutable original of the same approved adult woman; '
    'identity and face viewing angle remain unchanged throughout this group.'
)
OPTICS_ORIGINAL = [
    'Operator reviewed one approved immutable original scene shared by every rendered photography:same_scene control.',
    'Identity, scene contents, pose and camera position remain fixed; only the selected optical or photographic treatment and its declared consequences may change.',
    'Field-of-view crop, regional blur, synthetic grain and global color or tone changes are permitted only when declared by the selected target contract; no missing source detail, perspective change or camera equivalence is implied.',
]


def expected_requirements(category, attribute):
    """Independent acceptance contract, without importing builder policy helpers."""
    aid = attribute['id']
    if category == 'hair':
        if attribute['preview_method'] == 'reference_edit':
            target = (
                'Only the selected hair_color_treatment distribution and its declared tones may change; non-target hair geometry and base pigment remain fixed.'
                if aid == 'hair_color_treatment' else
                f'Only the selected {aid} target and its reviewed consequences may change; non-target hair geometry, pigment and distribution remain fixed.'
            )
            return [HAIR_ORIGINAL, target]
        if aid == 'hair_color':
            return [
                'Operator reviewed a suitable immutable original of the same approved adult woman; the original hair pigment may be any suitable color.',
                'Hair recoloring is confined to the reviewed hair-pigment mask; strand texture, geometry and distribution remain unchanged.',
            ]
    if category == 'eyes':
        return [
            EYES_ORIGINAL,
            f'Identity, face viewing angle and non-target eye details remain unchanged; only the selected {aid} target may change.',
            EYES_TARGETS[aid],
        ]
    if category == 'face_expression_makeup':
        return [
            FACE_ORIGINAL,
            f'Constraints apply to the selected {aid} target: only that target and its reviewed consequences may change; all non-target facial geometry, pigment, expression and gaze remain fixed.',
        ]
    if (attribute['comparison_group'] == 'photography:same_scene'
            and attribute['preview_method'] != 'control_only'):
        return OPTICS_ORIGINAL[:]
    return []


class BaselineRequirementsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.library = json.loads((ROOT / 'catalog/v2/library.json').read_bytes())
        cls.categories = {c['id']: c['attributes'] for c in cls.library['categories']}
        cls.attributes = {a['id']: a for attrs in cls.categories.values() for a in attrs}

    def requirements(self, attribute):
        contract = attribute['preview_contract']
        self.assertIn('baseline_requirements', contract, attribute['id'])
        return contract['baseline_requirements']

    def test_every_attribute_has_the_exact_human_string_list(self):
        for cid, attributes in self.categories.items():
            for attribute in attributes:
                with self.subTest(category=cid, attribute=attribute['id']):
                    requirements = self.requirements(attribute)
                    self.assertIsInstance(requirements, list)
                    self.assertTrue(all(isinstance(s, str) and s.strip() for s in requirements))
                    self.assertEqual(len(requirements), len(set(requirements)))
                    self.assertEqual(requirements, expected_requirements(cid, attribute))

    def test_all_nine_hair_reference_groups_start_uniform_neutral_medium_brown(self):
        reference = [a for a in self.categories['hair'] if a['preview_method'] == 'reference_edit']
        self.assertEqual({a['id'] for a in reference}, HAIR_REFERENCE_IDS)
        for attribute in reference:
            with self.subTest(attribute=attribute['id']):
                self.assertEqual(self.requirements(attribute)[0], HAIR_ORIGINAL)
                self.assertIn(attribute['id'], self.requirements(attribute)[1])
        self.assertIn('declared tones may change', self.requirements(self.attributes['hair_color_treatment'])[1])

    def test_hair_recolor_accepts_any_suitable_original_pigment(self):
        color = self.attributes['hair_color']
        self.assertEqual(color['preview_method'], 'masked_recolor')
        requirements = self.requirements(color)
        self.assertIn('any suitable color', requirements[0])
        self.assertNotIn('medium-brown', ' '.join(requirements))
        self.assertNotIn('uniform', ' '.join(requirements))

    def test_every_eyes_group_uses_visible_iris_and_lash_boundary_view(self):
        self.assertEqual({a['id'] for a in self.categories['eyes']}, set(EYES_TARGETS))
        for attribute in self.categories['eyes']:
            with self.subTest(attribute=attribute['id']):
                requirements = self.requirements(attribute)
                self.assertEqual(requirements[0], EYES_ORIGINAL)
                self.assertEqual(requirements[2], EYES_TARGETS[attribute['id']])
                # A human approves the view; this contract prescribes no crop algorithm.
                self.assertNotIn('crop', ' '.join(requirements))

    def test_all_face_controls_keep_identity_and_view_with_target_specific_constraints(self):
        self.assertEqual(len(self.categories['face_expression_makeup']), 12)
        for attribute in self.categories['face_expression_makeup']:
            with self.subTest(attribute=attribute['id']):
                requirements = self.requirements(attribute)
                self.assertEqual(requirements[0], FACE_ORIGINAL)
                self.assertIn(f"selected {attribute['id']} target:", requirements[1])
                self.assertIn('non-target facial geometry, pigment, expression and gaze', requirements[1])

    def test_same_scene_optics_allow_only_declared_target_effects(self):
        rendered = [a for a in self.attributes.values()
                    if a['comparison_group'] == 'photography:same_scene'
                    and a['preview_method'] != 'control_only']
        self.assertEqual(len(rendered), 11)
        for attribute in rendered:
            with self.subTest(attribute=attribute['id']):
                self.assertEqual(self.requirements(attribute), OPTICS_ORIGINAL)
        self.assertEqual(self.requirements(self.attributes['camera']), [])
        focal = self.attributes['focal_length']['preview_contract']
        self.assertNotIn('crop', focal['locked_fields'])
        self.assertEqual(focal['allowed_changes'], ['fixed-position field-of-view crop and resampling; no perspective change'])
        for aid in ('white_balance', 'highlight_rolloff', 'color_grade', 'contrast', 'palette'):
            self.assertEqual(self.attributes[aid]['preview_contract']['allowed_changes'], ['global colour and tone'])

    def test_controls_counts_ids_and_all_existing_metadata_are_preserved(self):
        self.assertEqual(len(self.categories), 12)
        self.assertEqual(len(self.attributes), 129)
        self.assertEqual(sum(len(a['values']) for a in self.attributes.values()), 1596)
        without_requirements = copy.deepcopy(self.library)
        for category in without_requirements['categories']:
            for attribute in category['attributes']:
                attribute['preview_contract'].pop('baseline_requirements', None)
        canonical = json.dumps(without_requirements, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()
        self.assertEqual(hashlib.sha256(canonical).hexdigest(), BASE_LIBRARY_SEMANTIC_SHA256)

    def test_frozen_history_aliases_migrations_and_pointers_keep_exact_bytes(self):
        for path, digest in FROZEN_SHA256.items():
            with self.subTest(path=path):
                self.assertEqual(hashlib.sha256((ROOT / path).read_bytes()).hexdigest(), digest)

    def test_isolated_build_regenerates_exact_bytes_twice_without_history_changes(self):
        spec = importlib.util.spec_from_file_location('baseline_resume_builder', ROOT / 'scripts/build_catalog_v2.py')
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        workspace_paths = ['catalog/v2/library.json', *FROZEN_SHA256]
        workspace_before = {p: (ROOT / p).read_bytes() for p in workspace_paths}
        with tempfile.TemporaryDirectory(prefix='baseline-metadata-offline-') as temporary:
            isolated = Path(temporary)
            shutil.copyfile(ROOT / 'library.json', isolated / 'library.json')
            plans = isolated / 'docs/plans/anchored-v2'
            plans.mkdir(parents=True)
            for name in ('HAIR-PROPOSAL.json', 'WARDROBE-PROPOSAL.json', 'COVERAGE.json', 'HAIR-MIGRATIONS.json'):
                shutil.copyfile(ROOT / 'docs/plans/anchored-v2' / name, plans / name)
            for path in FROZEN_SHA256:
                target = isolated / path
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / path, target)
            for cycle in range(2):
                previous_path = sys.path[:]
                try:
                    builder.build(isolated)
                finally:
                    sys.path[:] = previous_path
                rebuilt = json.loads((isolated / 'catalog/v2/library.json').read_bytes())
                for category in rebuilt['categories']:
                    for attribute in category['attributes']:
                        with self.subTest(cycle=cycle, attribute=attribute['id']):
                            self.assertEqual(self.requirements(attribute), expected_requirements(category['id'], attribute))
                for path, original in workspace_before.items():
                    with self.subTest(cycle=cycle, path=path):
                        self.assertEqual((isolated / path).read_bytes(), original)
        self.assertEqual({p: (ROOT / p).read_bytes() for p in workspace_paths}, workspace_before)


if __name__ == '__main__':
    unittest.main()
