"""ミスミの現行仕様と取扱資料で判明した版・接地の違いを保持する。"""
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1] / 'parts/network/misumi/iesh/switch'


def definitions():
    return {d['model']: d['definition'] for p in ROOT.glob('*.json')
            for d in [json.loads(p.read_text(encoding='utf-8'))]}


class MisumiBasicSwitchesTest(unittest.TestCase):
    def test_ports_are_rj45_cables_without_invented_fiber_or_management(self):
        specs = definitions()
        self.assertTrue(specs)
        for model, spec in specs.items():
            count = 5 if '205' in model else 8
            self.assertEqual(spec['component_style'], 'ethernet_switch')
            self.assertEqual([p['label'] for p in spec['ports']], [str(i) for i in range(1, count + 1)])
            self.assertTrue(all(p['type'] == 'rj45' and p['speed'] == '10/100BASE-TX' for p in spec['ports']))
            self.assertFalse(spec['managed'])
            self.assertFalse(spec['poe'])
            self.assertEqual(spec['alarm_terminals'], [])

    def test_basic_r_ac_is_limited_to_current_five_port_revision(self):
        specs = definitions()
        five, eight = specs['IESH-MB205-R'], specs['IESH-MB208-R']
        self.assertEqual(five['power']['ac_voltage_nominal_v'], 24)
        self.assertEqual(five['hardware_revision']['defined_revision'], 'V3.0.0')
        self.assertIn('旧V2.1.2はDCのみ', five['revision_note'])
        self.assertEqual(five['power']['dc_voltage_max_v'], 48)
        self.assertIsNone(eight['power']['ac_voltage_nominal_v'])
        self.assertEqual(eight['power']['dc_voltage_max_v'], 45)
        for spec in (five, eight):
            self.assertEqual(spec['ground']['label'], 'E')
            self.assertEqual(spec['dip_switches'], [])

    def test_c2e_ground_screw_and_terminal_block_are_different(self):
        for model, spec in definitions().items():
            if 'C2E' not in model:
                continue
            metal = 'M-C2E' in model
            self.assertEqual(spec['power']['dc_voltage_nominal_v'], [12, 24, 48])
            self.assertEqual([t['label'] for t in spec['power']['terminals']], ['V-', 'V+'])
            self.assertEqual(spec['ground']['label'], '⏚')
            self.assertEqual(spec['ground']['connection_type'], '別置シャーシ接地ねじ' if metal else '電源端子台の接地端子')
            self.assertEqual({d['label'] for d in spec['dip_switches']}, {'QoS', 'BSP'})
            self.assertTrue(all(d['selected'] is None for d in spec['dip_switches']))


if __name__ == '__main__':
    unittest.main()
