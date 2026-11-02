"""公式の定格・接続図に基づく保護部品の端子割当。"""
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1] / 'parts/control'


def load(maker, series, kind, model):
    return json.loads((ROOT / maker / series / kind / (model + '.json')).read_text(encoding='utf-8'))['definition']


class ProtectionThermalPartsTest(unittest.TestCase):
    def test_cp_ratings_and_unconfirmed_numeric_terminal_markings(self):
        # 62D1-J-0039h p15形式規則と公式個別PRODUCT SELECTORを全件照合。
        for current in (1, 2, 3, 5, 10, 20):
            model = f'CP30FM-2P{current:03d}'
            spec = load('fuji', 'cp30f', 'breaker', model)
            self.assertEqual(spec['ratings']['rated_current_a'], current)
            self.assertEqual(spec['ratings']['poles'], 2)
            self.assertFalse(spec['auxiliary_switch'])
            self.assertFalse(spec['alarm_switch'])
            pins = spec['symbol_bindings'][0]['terminals']
            self.assertEqual(pins, {'line1': ['LINE 左'], 'load1': ['LOAD 左'], 'line2': ['LINE 右'], 'load2': ['LOAD 右']})
            self.assertEqual(spec['standard_text_overrides']['breaker_2p']['Calibre __A'], f'{current}A')

    def test_thermal_three_element_standalone_and_trip_contacts(self):
        models = {'TR18X3H-1P4': [1.4, 2.1], 'TR18X3H-005': [5, 7.5],
                  'TR18X3H-009': [9, 13], 'TR38X3H-012': [12, 18],
                  'TR38X3H-020': [20, 26], 'TR65X3H-044': [44, 54]}
        for model, span in models.items():
            spec = load('fuji', 'tr_next', 'thermal', model)
            self.assertEqual(spec['ratings']['current_setting_range_a'], span)
            self.assertIsNone(spec['ratings']['selected_current_a'])
            self.assertEqual(spec['ratings']['heater_elements'], 3)
            main, nc, no = spec['symbol_bindings']
            self.assertEqual(main['terminals'], {'line1': ['1/L1'], 'load1': ['2/T1'], 'line2': ['3/L2'], 'load2': ['4/T2'], 'line3': ['5/L3'], 'load3': ['6/T3']})
            self.assertEqual(nc, {'name': 'trip_nc', 'symbol': 'thermal_contact_nc', 'terminals': {'first': ['95'], 'second': ['96']}})
            self.assertEqual(no, {'name': 'trip_no', 'symbol': 'thermal_contact_no', 'terminals': {'first': ['97'], 'second': ['98']}})

    def test_fuse_holder_limits_are_not_selected_fuse_ratings(self):
        for model, voltage, current in (('FHN-15', 250, 15), ('FH-30', 600, 30), ('FH-60', 600, 60)):
            spec = load('toho', 'fh', 'fuse', model)
            self.assertEqual(spec['ratings']['holder_rated_current_a'], current)
            self.assertEqual(spec['ratings']['holder_rated_voltage_v'], voltage)
            self.assertIsNone(spec['ratings']['selected_fuse_current_a'])
            self.assertFalse(spec['fuse_included'])
            self.assertEqual(spec['symbol_bindings'][0]['terminals'], {'first': ['左側'], 'second': ['右側']})


if __name__ == '__main__':
    unittest.main()
