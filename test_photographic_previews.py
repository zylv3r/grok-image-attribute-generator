"""Manifest overrides use real, tagged local gallery photos; no provider calls."""
import base64
import copy
import io
import json
import os
import unittest
from unittest.mock import patch

from PIL import Image

import server
import test_server
from gallery import save_image


class PhotographicPreviewTests(unittest.TestCase):
    setUp = test_server.HTTPTests.setUp
    request = test_server.HTTPTests.request

    def tearDown(self):
        self.provider.assert_not_called()
        test_server.HTTPTests.tearDown(self)

    @property
    def manifest_path(self):
        return self.app.store.output_dir / 'photographic-previews.json'

    def publish(self, manifest):
        temporary = self.manifest_path.with_suffix('.tmp')
        temporary.write_text(json.dumps(manifest))
        os.replace(temporary, self.manifest_path)

    def photo(self, aid='color', vid='red'):
        buffer = io.BytesIO()
        Image.new('RGB', (400, 400), '#ba495a').save(buffer, format='PNG')
        record = save_image(base64.b64encode(buffer.getvalue()).decode(), self.app.store.output_dir, '1:1')
        public = self.app.store.add_image(record, 'PRIVATE fixture photo', {aid: [vid]})
        return dict(status='ready', image_id=public['id'], thumbnail_url=public['thumbnail_url'],
                    example_url=public['url'])

    def atlas(self, aid='color', size=(320, 240), format='JPEG'):
        directory = self.app.store.output_dir / 'preview-atlases'
        directory.mkdir(exist_ok=True)
        target = directory / (aid + '.jpg')
        Image.new('RGB', size, '#ba495a').save(target, format=format)
        return target

    def manifest(self, photo=None):
        return dict(version=1, total=893, completed=893, failed=0, status='running', attributes={
            'color': {'thumbnail_url': '/preview-atlases/color.jpg', 'values': {'red': photo or self.photo()}}})

    def library(self):
        status, body, _ = self.request('GET', '/api/library')
        self.assertEqual(status, 200)
        return body

    def items(self, library=None):
        library = library or self.library()
        attribute = library['categories'][0]['attributes'][0]
        return attribute, attribute['values'][0]

    def assert_pending(self):
        _, value = self.items()
        self.assertEqual((value['thumbnail_url'], value['thumbnail_kind'], value['thumbnail_status']),
                         ('', 'pending', 'pending'))
        self.assertNotIn('example_url', value)
        self.assertEqual(self.library()['thumbnail_progress']['value_completed'], 0)

    def test_no_manifest_preserves_library_and_status_counts_illustrations(self):
        self.assertEqual(self.library(), self.app.catalog.library)
        status, progress, _ = self.request('GET', '/api/thumbnail-status')
        self.assertEqual(status, 200)
        self.assertEqual(progress, dict(mode='illustrative', total=8, value_completed=1,
                                       attribute_completed=1, failed=0, status='completed', version=0))

    def test_valid_photo_and_atlas_override_copy_and_remain_searchable(self):
        original = copy.deepcopy(self.app.catalog.library)
        manifest = self.manifest()
        self.atlas()
        self.publish(manifest)
        library = self.library()
        attribute, value = self.items(library)
        self.assertEqual(library['thumbnail_mode'], 'photographic')
        self.assertEqual((value['thumbnail_kind'], value['thumbnail_status']), ('photographic', 'ready'))
        self.assertEqual(value['example_url'], manifest['attributes']['color']['values']['red']['example_url'])
        self.assertEqual(value['illustration_url'], '/thumbnails/color/red.svg')
        self.assertNotIn('thumbnail', value)
        self.assertEqual((attribute['thumbnail_kind'], attribute['thumbnail_status']), ('contact_sheet', 'ready'))
        self.assertEqual(library['thumbnail_progress'], dict(total=8, value_completed=1, attribute_completed=1,
                                                           failed=0, status='running', version=1))
        self.assertEqual(self.app.catalog.library, original)
        self.assertEqual(self.app.store.query(filters={'color': ['red']})['total'], 1)
        for url in [value['thumbnail_url'], value['example_url']]:
            for method in ['GET', 'HEAD']:
                status, raw, headers = self.request(method, url)
                self.assertEqual(status, 200)
                self.assertEqual(headers['Content-Type'], 'image/jpeg')
                self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')
                if method == 'HEAD':
                    self.assertEqual(raw, b'')

    def test_missing_values_default_to_pending_with_supplemental_illustration(self):
        self.publish(dict(version=2, status='paused', attributes={}, completed=893, total=893))
        library = self.library()
        for category in library['categories']:
            for attribute in category['attributes']:
                for item in [attribute, *attribute['values']]:
                    self.assertEqual((item['thumbnail_url'], item['thumbnail_kind'], item['thumbnail_status']),
                                     ('', 'pending', 'pending'))
        _, value = self.items(library)
        self.assertEqual(value['illustration_url'], '/thumbnails/color/red.svg')
        self.assertEqual(library['thumbnail_progress']['status'], 'paused')

    def test_false_mapping_unregistered_photo_and_missing_tags_are_pending(self):
        photo = self.photo('color', 'blue')
        manifest = self.manifest(photo)
        self.publish(manifest)
        self.assert_pending()
        manifest['attributes']['color']['values']['red'] = self.photo()
        photo = manifest['attributes']['color']['values']['red']
        with self.app.store.connect() as db:
            db.execute('DELETE FROM image_tags WHERE image_id=?', (photo['image_id'],))
        self.publish(manifest)
        self.assert_pending()
        photo = dict(photo, image_id='a' * 32, thumbnail_url='/generated/' + 'a' * 32 + '-thumb.jpg',
                     example_url='/generated/' + 'a' * 32 + '.jpg')
        manifest['attributes']['color']['values']['red'] = photo
        Image.new('RGB', (20, 20)).save(self.app.store.output_dir / ('a' * 32 + '.jpg'))
        Image.new('RGB', (20, 20)).save(self.app.store.output_dir / ('a' * 32 + '-thumb.jpg'))
        self.publish(manifest)
        self.assert_pending()

    def test_selection_json_must_agree_with_registered_tags(self):
        manifest = self.manifest()
        photo = manifest['attributes']['color']['values']['red']
        for selections in ['{}', '[]', 'malformed', '{"color":"red"}', '{"color":["blue"]}']:
            with self.app.store.connect() as db:
                db.execute('UPDATE images SET selections=? WHERE id=?', (selections, photo['image_id']))
            self.publish(manifest)
            self.assert_pending()

    def test_exact_photo_urls_and_ids_are_required(self):
        manifest = self.manifest()
        photo = manifest['attributes']['color']['values']['red']
        bad = [('image_id', photo['image_id'].upper()), ('image_id', ['private']),
               ('image_id', '../server.py'), ('example_url', '/server.py'),
               ('example_url', photo['example_url'] + '?private'),
               ('thumbnail_url', 'https://example.invalid/secret.jpg'),
               ('thumbnail_url', '/generated/../server.py'), ('status', 'pending')]
        for key, value in bad:
            with self.subTest(key=key, value=value):
                changed = copy.deepcopy(manifest)
                changed['attributes']['color']['values']['red'][key] = value
                self.publish(changed)
                self.assert_pending()

    def test_missing_corrupt_or_symlink_photo_files_cannot_count_as_ready(self):
        manifest = self.manifest()
        self.publish(manifest)
        photo = manifest['attributes']['color']['values']['red']
        for field in ['example_url', 'thumbnail_url']:
            target = self.app.store.output_dir / photo[field].split('/')[-1]
            raw = target.read_bytes()
            self.assertEqual(self.library()['thumbnail_progress']['value_completed'], 1)
            target.unlink()
            self.assert_pending()
            target.write_bytes(b'PRIVATE invalid JPEG')
            self.assert_pending()
            target.unlink()
            other = self.root / 'secret.jpg'
            other.write_bytes(raw)
            target.symlink_to(other)
            self.assert_pending()
            target.unlink()
            target.write_bytes(raw)

    def test_unknown_manifest_ids_and_injected_fields_never_escape(self):
        manifest = self.manifest()
        manifest['attributes']['../../server.py'] = {'thumbnail_url': '/server.py', 'values': {}}
        manifest['attributes']['color']['values']['unknown'] = self.photo()
        manifest['attributes']['color']['values']['red']['secret'] = 'PRIVATE TOKEN'
        manifest['secret'] = 'PRIVATE TOKEN'
        self.publish(manifest)
        text = json.dumps(self.library())
        self.assertNotIn('PRIVATE', text)
        self.assertNotIn('/server.py', text)
        self.assertNotIn(str(self.root), text)
        self.assertEqual(self.library()['thumbnail_progress']['value_completed'], 1)

    def test_malformed_or_oversized_manifest_is_safe_pending_not_500(self):
        bad = [b'{PRIVATE TOKEN', b'[]', b'{"attributes":[]}', b'{"attributes":{},"failed":NaN}',
               b'{"attributes":{},"attributes":{}}', b'\xff',
               b'[' * 2000 + b']' * 2000, b' ' * (server.PREVIEW_MANIFEST_LIMIT + 1)]
        for raw in bad:
            with self.subTest(length=len(raw)):
                self.manifest_path.write_bytes(raw)
                self.assert_pending()
                status, progress, _ = self.request('GET', '/api/thumbnail-status')
                self.assertEqual(status, 200)
                self.assertEqual((progress['mode'], progress['status']), ('photographic', 'failed'))
                self.assertNotIn('PRIVATE', json.dumps(progress))

    def test_manifest_symlink_or_directory_is_safe_and_never_exposed(self):
        self.manifest_path.symlink_to(self.root / 'server.py')
        self.assert_pending()
        self.manifest_path.unlink()
        self.manifest_path.mkdir()
        self.assert_pending()
        for method in ['GET', 'HEAD']:
            for url in ['/generated/photographic-previews.json', '/generated/photographic-previews.tmp',
                        '/photographic-previews.json', '/preview-atlases/photographic-previews.json']:
                self.assertEqual(self.request(method, url)[0], 404)

    def test_manifest_and_source_are_denied_even_if_gallery_filename_is_corrupt(self):
        photo = self.photo()
        for filename in ['photographic-previews.json', 'provider.log', 'server.py']:
            (self.app.store.output_dir / filename).write_text('PRIVATE TOKEN')
            with self.app.store.connect() as db:
                db.execute('UPDATE images SET filename=? WHERE id=?', (filename, photo['image_id']))
            for method in ['GET', 'HEAD']:
                self.assertEqual(self.request(method, '/generated/' + filename)[0], 404)

    def test_preview_routes_keep_loopback_host_guard(self):
        self.atlas()
        for url in ['/api/library', '/api/thumbnail-status', '/preview-atlases/color.jpg']:
            for method in ['GET', 'HEAD']:
                self.assertEqual(self.request(method, url, headers={'Host': 'evil.example:8123'})[0], 403)

    def test_contact_sheet_get_head_exact_allowlist_and_no_traversal(self):
        target = self.atlas()
        for method in ['GET', 'HEAD']:
            status, raw, headers = self.request(method, '/preview-atlases/color.jpg')
            self.assertEqual(status, 200)
            self.assertEqual(headers['Content-Type'], 'image/jpeg')
            self.assertEqual(int(headers['Content-Length']), target.stat().st_size)
            self.assertEqual(raw, b'' if method == 'HEAD' else target.read_bytes())
        self.atlas('unknown')
        denied = ['/preview-atlases/', '/preview-atlases/unknown.jpg', '/preview-atlases/color.JPG',
                  '/preview-atlases/color.jpg/extra', '/preview-atlases/../server.py',
                  '/preview-atlases/%2e%2e/server.py', '/preview-atlases/%2e%2e%2fserver.py',
                  '/preview-atlases/sub/color.jpg', '/preview-atlases/color%5c.jpg',
                  '/preview-atlases/.color.jpg', '/generated/preview-atlases/color.jpg']
        for url in denied:
            for method in ['GET', 'HEAD']:
                with self.subTest(url=url, method=method):
                    self.assertEqual(self.request(method, url)[0], 404)

    def test_atlas_must_be_real_bounded_jpeg_and_not_symlink(self):
        self.publish(self.manifest())
        for size, format in [((320, 240), 'PNG'), ((401, 240), 'JPEG'), ((320, 401), 'JPEG')]:
            self.atlas(size=size, format=format)
            self.assertEqual(self.items()[0]['thumbnail_kind'], 'pending')
            for method in ['GET', 'HEAD']:
                self.assertEqual(self.request(method, '/preview-atlases/color.jpg')[0], 404)
        target = self.atlas()
        target.write_text('PRIVATE source')
        self.assertEqual(self.request('GET', '/preview-atlases/color.jpg')[0], 404)
        target.unlink()
        target.symlink_to(self.root / 'server.py')
        self.assertEqual(self.request('GET', '/preview-atlases/color.jpg')[0], 404)
        target.unlink()
        directory = target.parent
        directory.rmdir()
        other = self.root / 'other'
        other.mkdir()
        Image.new('RGB', (320, 240)).save(other / 'color.jpg')
        directory.symlink_to(other, target_is_directory=True)
        self.assertEqual(self.items()[0]['thumbnail_kind'], 'pending')
        self.assertEqual(self.request('GET', '/preview-atlases/color.jpg')[0], 404)

    def test_stat_cache_reuses_decodes_and_invalidates_atomic_replacement(self):
        self.publish(self.manifest())
        self.atlas()
        self.library()
        with patch.object(server.Image, 'open', side_effect=AssertionError('unexpected repeat decode')):
            self.library()
            self.request('GET', '/api/thumbnail-status')
            self.assertEqual(self.request('GET', '/preview-atlases/color.jpg')[0], 200)
        target = self.app.store.output_dir / 'preview-atlases' / 'color.jpg'
        replacement = target.with_suffix('.tmp')
        replacement.write_bytes(b'PRIVATE not JPEG')
        os.replace(replacement, target)
        self.assertEqual(self.items()[0]['thumbnail_kind'], 'pending')
        self.assertEqual(self.request('GET', '/preview-atlases/color.jpg')[0], 404)
        self.atlas(size=(400, 400))
        self.assertEqual(self.items()[0]['thumbnail_kind'], 'contact_sheet')

    def test_atomic_manifest_updates_and_removal_take_effect_without_restart(self):
        manifest = self.manifest()
        self.publish(manifest)
        self.assertEqual(self.library()['thumbnail_progress']['version'], 1)
        manifest['version'] = 2
        manifest['status'] = 'paused'
        manifest['attributes']['color']['values']['blue'] = self.photo('color', 'blue')
        self.publish(manifest)
        library = self.library()
        self.assertEqual((library['thumbnail_progress']['version'], library['thumbnail_progress']['value_completed']), (2, 2))
        status, progress, _ = self.request('GET', '/api/thumbnail-status')
        self.assertEqual(status, 200)
        self.assertEqual(progress, dict(mode='photographic', **library['thumbnail_progress']))
        self.manifest_path.unlink()
        self.assertEqual(self.library(), self.app.catalog.library)

    def test_claimed_totals_and_status_cannot_fabricate_completion(self):
        manifest = self.manifest()
        manifest.update(status='completed', completed=10**9, total=10**9, failed=10**9, version=True)
        self.publish(manifest)
        progress = self.library()['thumbnail_progress']
        self.assertEqual(progress, dict(total=8, value_completed=1, attribute_completed=0,
                                       failed=7, version=0, status='running'))
        manifest.update(status=['PRIVATE'], failed=-1, version='PRIVATE')
        self.publish(manifest)
        self.assertEqual(self.library()['thumbnail_progress']['status'], 'failed')
        self.assertEqual(self.library()['thumbnail_progress']['failed'], 0)

    def test_completed_requires_all_catalog_values_and_atlases_verified(self):
        # The final all-values control is independent of the progressive URL version.
        attributes = {}
        for aid, attribute in self.app.catalog.attributes.items():
            attributes[aid] = {'thumbnail_url': '/preview-atlases/' + aid + '.jpg',
                               'values': {v['id']: self.photo(aid, v['id']) for v in attribute['values']}}
            self.atlas(aid)
        self.publish(dict(version=3, status='completed', attributes=attributes, failed=0))
        progress = self.library()['thumbnail_progress']
        self.assertEqual((progress['value_completed'], progress['attribute_completed'], progress['status']),
                         (8, 3, 'completed'))


    def test_contact_sheet_url_changes_on_new_manifest_version_and_remains_served(self):
        manifest = self.manifest()
        self.atlas()
        self.publish(manifest)
        first = self.items(self.library())[0]['thumbnail_url']
        self.assertTrue(first.endswith('?v=1'))
        manifest['version'] = 2
        self.publish(manifest)
        second = self.items(self.library())[0]['thumbnail_url']
        self.assertTrue(second.endswith('?v=2'))
        self.assertNotEqual(first, second)
        self.assertEqual(self.request('GET', second)[0], 200)
        self.assertEqual(self.request('HEAD', second)[0], 200)


if __name__ == '__main__':
    unittest.main()
