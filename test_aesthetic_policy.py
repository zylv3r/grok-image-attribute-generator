"""Always-on adult aesthetic policy; no real provider calls."""
import json
from pathlib import Path
import re
import unittest
import server

class AestheticPolicyTests(unittest.TestCase):
    def test_actual_catalog_prompts_always_include_all_three_keywords(self):
        root=Path(__file__).resolve().parent
        library=json.loads((root/'catalog/v2/library.json').read_text())
        catalog=server.Catalog(library)
        for selections in ({}, {'pose':['standing_neutral']}, {'top_style':['crewneck_tee']}, {'gender':['man']}, {'gender':['nonbinary']}):
            with self.subTest(selections=selections):
                prompt=catalog.preview({'selections':selections,'seed':0,'extra_prompt':'Plain neutral studio.'})['plans'][0]['prompt']
                for word in ('cute','beautiful','gorgeous'):
                    self.assertRegex(prompt,rf'\b{word}\b')
                self.assertIn('adult',prompt.lower())
                self.assertIn('natural',prompt.lower())

if __name__=='__main__':unittest.main()
