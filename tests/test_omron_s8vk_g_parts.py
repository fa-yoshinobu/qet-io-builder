import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'parts/power_supply/omron/s8vk_g/power_supply'


class S8vkGPartsTest(unittest.TestCase):
    def spec(self, model):
        data = json.loads((ROOT / (model + '.json')).read_text(encoding='utf-8'))
        self.assertEqual(data['category'], 'power_supply')
        self.assertEqual(data['model'], model)
        return data['definition']

    def test_official_twenty_four_volt_lineup_and_currents(self):
        expected = {'S8VK-G01524': (15, 0.65), 'S8VK-G03024': (30, 1.3),
                    'S8VK-G06024': (60, 2.5), 'S8VK-G12024': (120, 5),
                    'S8VK-G24024': (240, 10), 'S8VK-G48024': (480, 20)}
        self.assertEqual({p.stem for p in ROOT.glob('*.json')}, set(expected))
        for model, (watts, amps) in expected.items():
            spec = self.spec(model)
            self.assertEqual(spec['output']['voltage_v'], 24)
            self.assertEqual((spec['output']['power_w'], spec['output']['current_a']), (watts, amps))
            self.assertEqual(spec['input']['ac_voltage_range_v'], [85, 264])
            self.assertEqual(spec['input']['dc_voltage_range_v'], [90, 350])

    def test_all_physical_parallel_output_contacts_are_preserved(self):
        # T056-E1-14 p8-10: 15W has four output contacts; all other models have five.
        for path in ROOT.glob('*.json'):
            spec = self.spec(path.stem)
            input_group, output_group = spec['terminal_groups']
            self.assertEqual([t['signal'] for t in input_group['terminals']], ['L', 'N', 'PE'])
            expected = ['+V', '+V'] + ['-V'] * (2 if path.stem == 'S8VK-G01524' else 3)
            self.assertEqual([t['signal'] for t in output_group['terminals']], expected)
            all_terms = input_group['terminals'] + output_group['terminals']
            self.assertEqual(len({t['id'] for t in all_terms}), len(all_terms))
            self.assertTrue(all('pin' not in t for t in all_terms))
            self.assertFalse(any('input_n' in group or 'input_pe' in group for group in spec['internal_connections']))

    def test_four_hundred_eighty_watt_terminal_position_is_different(self):
        self.assertEqual(self.spec('S8VK-G48024')['terminal_groups'][1]['location'], '下側右')
        self.assertEqual(self.spec('S8VK-G12024')['terminal_groups'][1]['location'], '上側')


if __name__ == '__main__':
    unittest.main()
