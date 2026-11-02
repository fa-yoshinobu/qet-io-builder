import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

import gen_io_page as gen
from tools import make_sample


class ExcelCsvTest(unittest.TestCase):
    def test_excel_csv_encodings_and_generated_bom(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d) / 'fx'
            with contextlib.redirect_stdout(io.StringIO()):
                make_sample.make('FX5U-32MR/ES', str(base))
            input_csv = base.with_name(base.name + '_in.csv')
            output_csv = base.with_name(base.name + '_out.csv')
            self.assertTrue(input_csv.read_bytes().startswith(b'\xef\xbb\xbf'))
            self.assertTrue(output_csv.read_bytes().startswith(b'\xef\xbb\xbf'))
            input_csv.write_bytes(input_csv.read_text(encoding='utf-8-sig').encode('cp932'))
            with contextlib.redirect_stdout(io.StringIO()):
                gen.main(str(base.with_suffix('.json')), str(base.with_suffix('.qet')))
            root = ET.parse(base.with_suffix('.qet')).getroot()
            self.assertIn('運転押釦', [item.text for item in root.findall('.//elementInformation')])
            result = base.with_name(base.name + '_iolist.csv')
            self.assertTrue(result.read_bytes().startswith(b'\xef\xbb\xbf'))
            self.assertIn('運転押釦', result.read_text(encoding='utf-8-sig'))


if __name__ == '__main__':
    unittest.main()
