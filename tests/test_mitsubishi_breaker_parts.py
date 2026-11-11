from tests.qet_support import requires_qet
import json
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

from renderers import standard

ROOT = Path(__file__).resolve().parents[1] / 'parts/control/mitsubishi'


def records(series):
    return [json.loads(p.read_text(encoding='utf-8')) for p in (ROOT / series / 'breaker').glob('*.json')]


class MitsubishiBreakerPartsTest(unittest.TestCase):
    def test_cp_order_combinations_and_dc_restriction(self):
        items = records('cp30_ba')
        self.assertEqual(len(items), 39)
        for record in items:
            spec = record['definition']
            poles = spec['ratings']['poles']
            self.assertEqual(record['category'], 'standard_device')
            self.assertEqual(spec['ratings']['elements'], poles)
            self.assertEqual(spec['ratings']['current_type'], 'AC' if poles == 3 else 'AC/DC')
            self.assertEqual(spec['ratings']['ul1077_rated_voltage']['dc_v'], {1: 65, 2: 125, 3: None}[poles])
            self.assertIn('1-M', record['model'])
            self.assertFalse(spec['auxiliary_switch'])
            self.assertFalse(spec['alarm_switch'])

    def test_nf_ratings_are_not_assigned_to_single_pole(self):
        items = records('nf')
        self.assertEqual(len(items), 12)
        for record in items:
            spec = record['definition']
            self.assertIn(spec['ratings']['poles'], (2, 3))
            self.assertIn(spec['ratings']['rated_current_a'], (3, 5, 10, 15, 20, 30))
            self.assertIn('直流では2つの極', ' '.join(spec['notes']))
            self.assertIn('直接接続不可', ' '.join(spec['notes']))
            self.assertFalse(spec['shunt_trip'])

    @requires_qet
    def test_pole_count_and_function_labels_survive_native_export(self):
        for series in ('cp30_ba', 'nf'):
            for record in records(series):
                model, spec = record['model'], record['definition']
                with self.subTest(model=model), tempfile.TemporaryDirectory() as folder:
                    paths = standard.export_model(model, spec, folder)
                    self.assertEqual(len(paths), 1)
                    root = ET.parse(paths[0]).getroot()
                    pins = root.findall('./description/terminal')
                    self.assertEqual(len(pins), spec['ratings']['poles'] * 2)
                    self.assertTrue(all(p.get('name').startswith(('LINE', 'LOAD')) for p in pins))
                    texts = [n.get('text') for n in root.findall('./description/text')]
                    texts += [n.findtext('text') for n in root.findall('./description/dynamic_text')]
                    self.assertFalse({'1', '2', '3', '4', '5', '6', 'C, 16A'} & set(texts))
                    self.assertIn(spec['source'], root.findtext('informations'))


if __name__ == '__main__':
    unittest.main()
