import contextlib
import io
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from xml.etree import ElementTree as ET

import gen_io_page as gen


class ProjectDefaultsTest(unittest.TestCase):
    def test_invalid_project_or_power_object_is_rejected(self):
        for source in ([], 'project', {'power': None}, {'power': []}, {'power': '24V'}):
            with self.subTest(source=source), self.assertRaisesRegex(ValueError, 'オブジェクト'):
                gen.project_config(source)

    def test_defaults_preserve_user_fields_and_do_not_share_power_dict(self):
        source = {'date': '20260101', 'author': '作成者', 'power': {'P': 'DC24', 'P_name': 'P1'}}
        result = gen.project_config(source)
        self.assertEqual(result['date'], source['date'])
        self.assertEqual(result['author'], source['author'])
        self.assertEqual(result['power'], {'P': 'DC24', 'N': '0V', 'P_name': 'P1'})
        self.assertEqual(source['power'], {'P': 'DC24', 'P_name': 'P1'})
        result['power']['N'] = 'changed'
        self.assertEqual(gen.project_config()['power']['N'], '0V')

    def test_screenshot_minimal_project_generates_fx5s_dc_power_page(self):
        config = {'project_title': '',
                  'pages': [{'kind': 'power', 'model': 'FX5S-30MT/DS', 'title': 'aaaa'}]}
        with tempfile.TemporaryDirectory() as folder:
            source, output = Path(folder) / 'input.json', Path(folder) / 'output.qet'
            source.write_text(json.dumps(config), encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()):
                gen.main(str(source), str(output))
            root = ET.parse(output).getroot()
            self.assertIn('aaaa', [d.get('title') for d in root.findall('diagram')])
            self.assertEqual(root.find('diagram').get('date'), date.today().strftime('%Y%m%d'))
            self.assertTrue(output.with_name('output_iolist.csv').exists())


if __name__ == '__main__':
    unittest.main()
