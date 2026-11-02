import tempfile
import unittest
from xml.etree import ElementTree as ET

import gen_io_page as gen
import gui_core
from renderers import standard


class HesiFuseHoldersTest(unittest.TestCase):
    def test_holder_limits_do_not_become_selected_fuse_ratings(self):
        catalog = gui_core.part_catalog('standard_model', '')
        for model, voltage, current, size in [
            ('PT 4-HESI (5X20)', 400, 6.3, [5, 20]),
            ('PTV 4-HESI (5X20)', 500, 6.3, [5, 20]),
            ('PT 6-HESI (6,3X32)', 630, 10, [6.3, 32]),
        ]:
            with self.subTest(model=model), tempfile.TemporaryDirectory() as folder:
                self.assertIn(model, catalog['phoenix_contact']['hesi'])
                spec = gen.STANDARD_DEVICES[model]
                self.assertEqual(spec['ratings']['holder_rated_voltage_v'], voltage)
                self.assertEqual(spec['ratings']['holder_rated_current_a'], current)
                self.assertEqual(spec['ratings']['applicable_fuse_size_mm'], size)
                self.assertIsNone(spec['ratings']['selected_fuse_current_a'])
                self.assertTrue(spec['fuse_selection_required'])
                self.assertFalse(spec['fuse_included'])
                self.assertFalse(spec['indicator'])
                paths = standard.export_model(model, spec, folder)
                self.assertEqual(len(paths), 1)
                root = ET.parse(paths[0]).getroot()
                self.assertEqual({t.get('name') for t in root.findall('./description/terminal')},
                                 {'配線口1', '配線口2'})
                self.assertIn('ヒューズ未選択', root.findtext(
                    "./elementInformations/elementInformation[@name='comment']"))


if __name__ == '__main__':
    unittest.main()
