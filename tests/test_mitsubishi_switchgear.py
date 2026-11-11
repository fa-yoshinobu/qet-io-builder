from tests.qet_support import requires_qet
import json
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

from renderers import standard


ROOT = Path(__file__).resolve().parents[1] / 'parts/control/mitsubishi'


def definitions(series):
    return {d['model']: d['definition'] for p in (ROOT / series).glob('*/*.json')
            for d in [json.loads(p.read_text(encoding='utf-8'))]}


class MitsubishiSwitchgearTest(unittest.TestCase):
    def test_contactors_preserve_real_main_and_coil_terminals(self):
        specs = definitions('ms_t')
        self.assertEqual(set(specs), {'S-T10', 'S-T12', 'S-T20', 'SD-T12', 'SD-T20'})
        for model, spec in specs.items():
            self.assertEqual([c['terminals'] for c in spec['contacts']],
                             [['1/L1', '2/T1'], ['3/L2', '4/T2'], ['5/L3', '6/T3']])
            self.assertEqual(spec['coil']['terminals'], ['A1', 'A2'])
            self.assertTrue(spec['coil']['voltage_selection_required'])
            if model.startswith('SD'):
                self.assertEqual(spec['coil']['polarity_by_terminal'], {'A1': '+', 'A2': '-'})
            else:
                self.assertNotIn('polarity_by_terminal', spec['coil'])

    def test_auxiliary_selection_distinguishes_one_nc_and_two_no(self):
        for model, spec in definitions('ms_t').items():
            with self.assertRaisesRegex(ValueError, '補助接点'):
                list(standard.bindings(spec))
            expected = {'1a', '1b'} if model == 'S-T10' else {'1a1b', '2a'}
            self.assertEqual({o['id'] for o in spec['auxiliary_options']}, expected)
            for option in spec['auxiliary_options']:
                if option['id'] == '2a':
                    self.assertEqual([c['terminals'] for c in option['contacts']], [['13', '14'], ['23', '24']])
                    self.assertTrue(all(c['type'] == 'no' for c in option['contacts']))

    def test_thermal_heaters_do_not_imply_setting_or_two_element_geometry(self):
        specs = definitions('th_t')
        self.assertEqual(len(specs), 6)
        expected = {0.9: [0.7, 1.1], 1.3: [1, 1.6], 2.5: [2, 3], 5: [4, 6], 9: [7, 11], 15: [12, 18]}
        for spec in specs.values():
            self.assertEqual(spec['base_model'], 'TH-T18KP')
            self.assertEqual(spec['ratings']['heater_elements'], 3)
            self.assertEqual(spec['ratings']['current_setting_range_a'], expected[spec['heater_designation_a']])
            self.assertIsNone(spec['ratings']['selected_current_a'])
            self.assertIn('実機設定未指定', spec['ratings']['reset'])
            parts = list(standard.bindings(spec))
            self.assertEqual(parts[0][2], {'line1': ['L1'], 'load1': ['2/T1'], 'line2': ['L2'], 'load2': ['4/T2'], 'line3': ['L3'], 'load3': ['6/T3']})
            self.assertEqual(parts[1][1:], ('thermal_contact_nc', {'first': ['95'], 'second': ['96']}))
            self.assertEqual(parts[2][1:], ('thermal_contact_no', {'first': ['97'], 'second': ['98']}))

    @requires_qet
    def test_all_parts_export_with_correct_electrical_terminal_count(self):
        for series in ('ms_t', 'th_t'):
            for model, spec in definitions(series).items():
                for choice in ([o['id'] for o in spec.get('auxiliary_options', [])] or [None]):
                    with self.subTest(model=model, choice=choice), tempfile.TemporaryDirectory() as target:
                        paths = standard.export_model(model, spec, target, auxiliary=choice)
                        actual = [len(ET.parse(p).findall('./description/terminal')) for p in paths]
                        expected = [2, 6] + [2] * (1 if choice in ('1a', '1b') else 2) if series == 'ms_t' else [6, 2, 2]
                        self.assertEqual(actual, expected)


if __name__ == '__main__':
    unittest.main()
