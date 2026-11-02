import json
from pathlib import Path
import unittest
from xml.etree import ElementTree as ET
from renderers import standard

ROOT = Path(__file__).resolve().parents[1] / 'parts/control/idec'

def spec(series, kind, model):
    return json.loads((ROOT / series / kind / (model + '.json')).read_text(encoding='utf-8'))['definition']


class IDECStandardPartsTest(unittest.TestCase):
    def test_parts_have_sources_and_use_existing_symbols(self):
        paths = list(ROOT.glob('*/*/*.json'))
        self.assertTrue(paths)
        for p in paths:
            item = json.loads(p.read_text(encoding='utf-8'))
            self.assertEqual(item['category'], 'standard_device')
            self.assertEqual(item['model'], p.stem)
            d = item['definition']
            self.assertTrue(d['source'])
            self.assertTrue(d['official_html'].startswith('https://www.idec.com/'))
            configured = standard.configured_spec(d)
            self.assertTrue(list(standard.bindings(configured)))
            for _, symbol, _ in standard.bindings(configured):
                self.assertIn(symbol, standard.catalog())

    def test_rj_one_and_two_pole_pin_numbers_are_not_interchanged(self):
        one = spec('rj', 'relay', 'RJ1S-CL-D24')
        two = spec('rj', 'relay', 'RJ2S-CL-D24')
        self.assertEqual(one['coil']['terminals'], ['1', '5'])
        self.assertEqual(two['coil']['terminals'], ['1', '8'])
        self.assertEqual(one['contacts'][0], {'type': 'changeover', 'common': ['4'], 'no': ['3'], 'nc': ['2']})
        self.assertEqual(two['contacts'][0], {'type': 'changeover', 'common': ['3'], 'no': ['4'], 'nc': ['2']})
        for model in ('RU2S-D24', 'RU2S-C-D24'):
            d = spec('ru', 'relay', model)
            self.assertEqual(d['coil']['terminals'], ['13', '14'])
            self.assertEqual(d['contacts'][1], {'type': 'changeover', 'common': ['12'], 'no': ['8'], 'nc': ['4']})
            self.assertEqual(d['manual_test_lever'], model == 'RU2S-D24')
        for series in ('rj', 'ru'):
            for p in (ROOT / series / 'relay').glob('*.json'):
                c = json.loads(p.read_text(encoding='utf-8'))['definition']['coil']
                self.assertEqual(c['rated_voltage'], 'DC24V')
                self.assertFalse(c['voltage_selection_required'])
                self.assertEqual(c['surge'], 'none')

    def test_hw_lamp_is_separate_and_selector_positions_match_manufacturer(self):
        d = spec('hw', 'switch', 'HW1L-M111Q4G')
        self.assertEqual(len(d['symbol_bindings']), 3)
        self.assertEqual(d['mechanically_linked'], ['pushbutton', 'nc'])
        self.assertEqual(d['lamp']['terminals'], ['X1', 'X2'])
        self.assertEqual(d['lamp']['polarity'], 'none')
        d = spec('hw', 'switch', 'HW1S-2T11')
        part, template, labels = next(standard.bindings(d))
        xml = standard.bind_definition('HW1S-2T11', d, part, template, labels)
        self.assertEqual({n.get('text') for n in xml.findall('./description/text')}, {'1', '2'})
        self.assertEqual(d['position_contact_table']['2'], {'no': 'closed', 'nc': 'open'})

    def test_sj_is_passive_socket_with_verified_nema_to_iec_map(self):
        for model, count in [('SJ1S-05BS', 5), ('SJ2S-05BS', 8)]:
            d = spec('sj', 'socket', model)
            self.assertEqual(d['electrical_terminals'], count)
            self.assertEqual(len(d['terminal_map']), count)
            self.assertEqual(len(d['symbol_bindings']), count)
            self.assertTrue(all(b['symbol'] == 'terminal' for b in d['symbol_bindings']))
        d = spec('sj', 'socket', 'SJ1S-05BS')
        self.assertIn({'socket_marking': '4(11)', 'relay_pin': '4', 'function': 'common', 'wire_entries': 1}, d['terminal_map'])
        d = spec('sj', 'socket', 'SJ2S-05BS')
        self.assertIn({'socket_marking': '3(11)', 'relay_pin': '3', 'function': 'common', 'wire_entries': 1}, d['terminal_map'])


if __name__ == '__main__':
    unittest.main()
