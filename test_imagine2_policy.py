"""Future app generation/edit requests must never route to legacy Imagine models."""
import base64,sys,unittest
from unittest.mock import patch
import server
from test_server_v2 import NativeEditTests
from test_gallery import image_bytes

class Imagine2PolicyTests(unittest.TestCase):
 def test_generation_pins_imagine2_even_with_stale_legacy_config(self):
  requests,modules=NativeEditTests().modules({'data':[{'b64_json':image_bytes()}]})
  modules['hermes_cli.config'].load_config.return_value={'image_gen':{'xai':{'model':'grok-imagine-image-quality','resolution':'1k'}}}
  with patch.dict(sys.modules,modules):server.generate_native_image('adult persona','9:16')
  self.assertEqual(requests.post.call_args.kwargs['json']['model'],'grok-imagine-image-2.0')
 def test_reference_edit_pins_imagine2_with_actual_reference_even_with_legacy_override(self):
  requests,modules=NativeEditTests().modules({'data':[{'b64_json':image_bytes()}]})
  modules['hermes_cli.config'].load_config.return_value={'image_gen':{'xai':{'edit_model':'grok-imagine-image'}}}
  raw=base64.b64decode(image_bytes())
  with patch.dict(sys.modules,modules):server.edit_native_image('same reference',raw,'image/png','9:16')
  body=requests.post.call_args.kwargs['json'];self.assertEqual(body['model'],'grok-imagine-image-2.0');self.assertEqual(body['image']['url'],'data:image/png;base64,'+base64.b64encode(raw).decode())
if __name__=='__main__':unittest.main()
