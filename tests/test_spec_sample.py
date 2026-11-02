import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

import gen_io_page as gen
from tools.make_spec_sample import COLUMNS, make


class SpecSampleTest(unittest.TestCase):
    def test_editable_single_page_fits_the_common_frame_without_invented_ratings(self):
        with tempfile.TemporaryDirectory() as folder:
            root = ET.parse(make(Path(folder) / 'sample.qet')).getroot()
        self.assertEqual(len(root.findall('diagram')), 1)
        page = root.find('diagram')
        self.assertEqual((page.get('cols'), page.get('colsize'), page.get('rows'), page.get('rowsize')),
                         ('20', '62', '10', '80'))
        self.assertFalse(page.findall('./images/image'))
        for shape in page.findall('./shapes/shape'):
            self.assertTrue(all(20 <= float(shape.get(k)) <= 1260 for k in ('x1', 'x2')))
            self.assertTrue(all(20 <= float(shape.get(k)) <= 820 for k in ('y1', 'y2')))
        for text in page.findall('./inputs/input'):
            size = float(text.get('font').split(',')[1])
            self.assertGreaterEqual(size, 8)
            self.assertLessEqual(float(text.get('x')) + gen.text_w(text.get('text'), size) + 8, 1260)
            self.assertLessEqual(float(text.get('y')) + size * 96 / 72 + 8, 820)
        body = [text for text in page.findall('./inputs/input') if 144 <= float(text.get('y')) < 780]
        self.assertGreater(sum('□ ' in text.get('text') for text in body), 70)
        self.assertGreater(sum('■ ' in text.get('text') for text in body), 0)
        for text in body:
            x = float(text.get('x'))
            column = int((x - 50) // 395)
            self.assertLessEqual(x + gen.text_w(text.get('text'), 8) + 8, 50 + column * 395 + 370)
        electricity = next(rows for column in COLUMNS for title, rows in column if title == '電源条件')
        self.assertFalse(any(checked for _, options in electricity for _, checked in options))
        displayed = '\n'.join(text.get('text') for text in page.findall('./inputs/input'))
        for removed in ('検査・提出物', '外観検査', '配線検査', '動作試験', '試験条件',
                        '提出資料', '別表・特記', '別表指定', 'ヒータ'):
            self.assertNotIn(removed, displayed)


if __name__ == '__main__':
    unittest.main()
