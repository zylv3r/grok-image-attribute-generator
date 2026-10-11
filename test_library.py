import json
import unittest
from pathlib import Path


class PortraitLibraryTests(unittest.TestCase):
    def test_northern_european_face_and_figure_controls_exist(self):
        library = json.loads((Path(__file__).parent / 'library.json').read_text())
        attributes = {
            attribute['id']: {value['id'] for value in attribute['values']}
            for category in library['categories']
            for attribute in category['attributes']
        }
        self.assertTrue({'ethnic_inspiration', 'complexion_detail', 'cheekbones', 'eye_color', 'eyelashes', 'facial_balance'}.issubset(attributes))
        self.assertTrue({'slender_hourglass', 'slender_toned_legs'}.issubset(attributes['silhouette']))
        self.assertTrue({'icy_blue', 'pale_green', 'aqua', 'gray_blue'}.issubset(attributes['eye_color']))
        self.assertIn('prominent_soft', attributes['cheekbones'])
        self.assertIn('dark_long', attributes['eyelashes'])
        self.assertIn('prominent', attributes['freckles'])


if __name__ == '__main__':
    unittest.main()
