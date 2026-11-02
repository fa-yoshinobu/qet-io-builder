import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1] / 'parts/control/omron'


def get(series, kind, model):
    return json.loads((ROOT / series / kind / (model + '.json')).read_text(encoding='utf-8'))['definition']


class OmronSwitchTimerPartsTest(unittest.TestCase):
    def test_confirmed_model_definitions(self):
        files = [p for series in ('a22n', 'm22n', 'h3y') for p in (ROOT / series).glob('*/*.json')]
        self.assertTrue(files)
        for p in files:
            d = json.loads(p.read_text(encoding='utf-8'))
            self.assertEqual(d['category'], 'standard_device')
            self.assertEqual(d['model'], p.stem)
            self.assertTrue(d['definition']['source'])
            self.assertTrue(d['definition']['symbol_bindings'])

    def test_a22_contact_numbers_and_illumination_are_separate(self):
        no = get('a22n', 'switch', 'A22NN-BNM-NGA-G100-NN')['symbol_bindings'][0]
        nc = get('a22n', 'switch', 'A22NN-BNM-NRA-G002-NN')['symbol_bindings'][0]
        self.assertEqual(no['terminals'], {'first': ['3'], 'second': ['4']})
        self.assertEqual(nc['terminals'], {'first': ['1'], 'second': ['2']})
        self.assertEqual(nc['symbol'], 'pushbutton_nc')
        lighted = get('a22n', 'switch', 'A22NL-BNM-TGA-G102-GC')
        self.assertEqual([b['symbol'] for b in lighted['symbol_bindings']], ['pushbutton_no', 'contact_nc', 'lamp'])
        self.assertEqual(lighted['symbol_bindings'][2]['terminals'], {'first': ['X1'], 'second': ['X2']})

    def test_selector_positions_follow_manufacturer_not_generic_zero_one(self):
        d = get('a22n', 'switch', 'A22NS-2BM-NBA-G100-NN')
        self.assertEqual(d['contact_operation'], {'1': 'open', '2': 'closed'})
        self.assertEqual(d['standard_text_overrides']['selector_2position'], {'0': '1', '1': '2'})
        self.assertEqual(d['operation_angle_deg'], 90)

    def test_m22_24v_and_typical_current_are_not_confused(self):
        for code, color, current in [('TRA-RC', '赤', 12), ('TGA-GC', '緑', 5), ('TWA-WC', '白', 5)]:
            for suffix in ('', '-P'):
                d = get('m22n', 'lamp', 'M22N-BN-' + code + suffix)
                self.assertEqual(d['ratings']['voltage'], 'AC/DC24V')
                self.assertEqual(d['ratings']['rated_current_ma'], 12)
                self.assertEqual(d['ratings']['typical_current_ma'], current)
                self.assertEqual(d['color'], color)

    def test_timer_contacts_are_delayed_and_voltage_is_unselected(self):
        for model, com, no, nc in [('H3Y-2', ['9', '12'], ['5', '8'], ['1', '4']),
                                   ('H3Y-4', ['9', '10', '11', '12'], ['5', '6', '7', '8'], ['1', '2', '3', '4'])]:
            for suffix in ('', '-B'):
                d = get('h3y', 'timer', model + suffix)
                self.assertEqual(d['operation'], 'power_on_delay')
                self.assertEqual(d['instantaneous_contacts'], 0)
                self.assertIn('supply_voltage', d['selection_required'])
                self.assertEqual(d['coil']['polarity_by_terminal'], {'13': '- (DC)', '14': '+ (DC)'})
                contacts = d['symbol_bindings'][1:]
                self.assertTrue(all(c['symbol'] == 'timer_changeover_on_delay' for c in contacts))
                self.assertEqual([c['terminals']['common'][0] for c in contacts], com)
                self.assertEqual([c['terminals']['no'][0] for c in contacts], no)
                self.assertEqual([c['terminals']['nc'][0] for c in contacts], nc)


if __name__ == '__main__':
    unittest.main()
