"""Saved persona reference sets: immutable asset hashes, no comparison approvals."""
import hashlib,json,pathlib,tempfile,unittest,shutil
import persona_base
class PersonaBaseTests(unittest.TestCase):
 def test_repo_base_is_selected_with_caveats_and_imagine2_future_policy(self):
  summary=persona_base.summary(pathlib.Path(__file__).resolve().parent)
  self.assertTrue(summary['available']);self.assertEqual(summary['id'],'persona-b');self.assertEqual(summary['revision'],1)
  self.assertEqual(summary['future_image_model'],'grok-imagine-image-2.0');self.assertFalse(summary['controlled_masks_approved'])
  self.assertIn('right-facing',str(summary['caveats']))
 def test_asset_allowlist_rejects_traversal_and_unlisted_files(self):
  root=pathlib.Path(__file__).resolve().parent;summary=persona_base.summary(root);path=summary['overview_url'].split('/base-personas/',1)[1]
  result=persona_base.asset(root,path);self.assertEqual(result[1],'image/jpeg');self.assertGreater(len(result[0]),100)
  for bad in ['../gallery.sqlite3','persona-b/v1/../../server.py','persona-b/v1/unlisted.jpg']:
   with self.assertRaises(ValueError):persona_base.asset(root,bad)
 def test_every_saved_asset_matches_hash_and_decodes(self):
  root=pathlib.Path(__file__).resolve().parent;summary=persona_base.summary(root)
  self.assertEqual(len(summary['assets']),35);self.assertEqual(len(summary['selected_views']),17)
  for url,metadata in summary['assets'].items():
   with self.subTest(url=url):
    raw,_=persona_base.asset(root,url.split('/base-personas/',1)[1])
    self.assertEqual(hashlib.sha256(raw).hexdigest(),metadata['sha256'])
 def test_corrupt_asset_is_rejected_without_changing_saved_original(self):
  root=pathlib.Path(__file__).resolve().parent
  with tempfile.TemporaryDirectory() as directory:
   fixture=pathlib.Path(directory);shutil.copytree(root/'base-personas',fixture/'base-personas')
   summary=persona_base.summary(fixture);relative=summary['overview_url'].split('/base-personas/',1)[1]
   (fixture/'base-personas'/relative).write_bytes(b'corrupt')
   with self.assertRaisesRegex(ValueError,'integrity failed'):persona_base.asset(fixture,relative)
 def test_corrupt_manifest_and_symlink_asset_are_rejected(self):
  root=pathlib.Path(__file__).resolve().parent
  with tempfile.TemporaryDirectory() as directory:
   fixture=pathlib.Path(directory);shutil.copytree(root/'base-personas',fixture/'base-personas')
   summary=persona_base.summary(fixture);relative=summary['overview_url'].split('/base-personas/',1)[1]
   target=fixture/'base-personas'/relative;target.unlink();target.symlink_to(root/'base-personas'/relative)
   with self.assertRaisesRegex(ValueError,'symlink'):persona_base.asset(fixture,relative)
   manifest=fixture/'base-personas/persona-b/v1/persona.json';manifest.write_text('{}')
   with self.assertRaisesRegex(ValueError,'manifest integrity failed'):persona_base.summary(fixture)
 def test_missing_base_in_fixture_root_is_not_error_or_false_approval(self):
  with tempfile.TemporaryDirectory() as p:self.assertEqual(persona_base.summary(pathlib.Path(p)),{'available':False})
if __name__=='__main__':unittest.main()
