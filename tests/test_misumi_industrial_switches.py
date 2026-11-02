"""ミスミ上位掲載スイッチの電源・警報を取り違えない。"""
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1] / 'parts/network/misumi/industrial_switch/switch'


def records():
    return {p.stem: json.loads(p.read_text(encoding='utf-8')) for p in ROOT.glob('*.json')}


class MisumiIndustrialSwitchesTest(unittest.TestCase):
    def test_models_have_valid_category_style_and_source(self):
        items = records()
        self.assertTrue(items)
        for model, raw in items.items():
            d = raw['definition']
            self.assertEqual(raw['category'], 'standard_device')
            self.assertEqual(raw['model'], model)
            self.assertEqual(d['component_style'], 'ethernet_switch')
            self.assertTrue(d['source'])

    def test_ac_input_and_dips_belong_only_to_fast_model(self):
        for model in ('E-IESH-MB1005-T-R', 'E-IESH-MB1008-T-R'):
            d = records()[model]['definition']
            self.assertEqual([t['label'] for t in d['power']['terminals']], ['L/+', 'N/-'])
            self.assertEqual(d['ratings']['supply_vac_range'], [18, 30])
            self.assertEqual(d['ground']['function'], '筐体接地ねじ')
            self.assertNotIn('alarm', d)
            self.assertEqual([s['label'] for s in d['dip_switches']], ['QoS', 'BSP'])
            self.assertTrue(all(s['selected'] is None for s in d['dip_switches']))

    def test_gigabit_separates_power_and_unlabelled_relay_pins(self):
        for model in ('IESH-MB205G-R', 'IESH-MB208G-R'):
            d = records()[model]['definition']
            self.assertEqual([t['label'] for t in d['power']['terminals']], ['V2-', 'V2+', 'V1-', 'V1+'])
            self.assertIsNone(d['ratings']['supply_vac_range'])
            self.assertEqual([t['label'] for t in d['alarm']['terminals']], ['P-Fail 左', 'P-Fail 右'])
            self.assertIn('メーカーの端子番号ではない', d['alarm']['note'])
            self.assertEqual(d['dip_switches'], [])
            self.assertNotIn('ground', d)
            self.assertIn('未確認', ' '.join(d['notes']))

    def test_ports_are_cables_not_eight_internal_signal_pins(self):
        for model, raw in records().items():
            d = raw['definition']
            count = 5 if model in ('E-IESH-MB1005-T-R', 'IESH-MB205G-R') else 8
            self.assertEqual([p['label'] for p in d['ports']], [str(n) for n in range(1, count + 1)])
            self.assertTrue(all(p['type'] == 'rj45' for p in d['ports']))
            self.assertEqual(d['managed'], False)
            self.assertEqual(d['ratings']['speed_mbps'], [10, 100] if model.startswith('E-') else [10, 100, 1000])


if __name__ == '__main__':
    unittest.main()
