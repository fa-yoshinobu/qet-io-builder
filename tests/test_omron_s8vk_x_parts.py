"""T210-E1-13 p2・p13–16の型式、定格、接点構成に基づく照合。"""
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1] / 'parts/power_supply/omron/s8vk_x/power_supply'


class S8vkXPartsTest(unittest.TestCase):
    def test_exact_models_and_ratings(self):
        expected = {
            'S8VK-X06024-EIP': (60, 2.5, 3, False),
            'S8VK-X09024-EIP': (90, 3.75, None, False),
            'S8VK-X09024A-EIP': (90, 3.75, None, True),
            'S8VK-X12024-EIP': (120, 5, 6, False),
            'S8VK-X12024A-EIP': (120, 5, 6, True),
            'S8VK-X24024-EIP': (240, 10, 15, False),
            'S8VK-X24024A-EIP': (240, 10, 15, True),
            'S8VK-X48024-EIP': (480, 20, 30, False),
            'S8VK-X48024A-EIP': (480, 20, 30, True),
        }
        self.assertEqual({p.stem for p in ROOT.glob('*.json')}, set(expected))
        for model, (power, current, peak, monitor) in expected.items():
            with self.subTest(model=model):
                data = json.loads((ROOT / (model + '.json')).read_text(encoding='utf-8'))
                s = data['definition']
                self.assertEqual(data['category'], 'power_supply')
                self.assertEqual(s['output'], {'voltage_v': 24, 'current_a': current, 'power_w': power, 'maximum_boost_current_a': peak})
                self.assertEqual(s['indication_monitor'], monitor)
                self.assertTrue(s['communication_supported'])
                self.assertEqual(s['interfaces'][0]['ports'], 1)

    def test_physical_contacts_are_retained_without_invented_pin_numbers(self):
        for path in ROOT.glob('*.json'):
            with self.subTest(model=path.stem):
                s = json.loads(path.read_text(encoding='utf-8'))['definition']
                inp, out = s['terminal_groups']
                self.assertEqual([t['label'] for t in inp['terminals']], ['L1', 'L2', 'N1', 'N2', 'PE'])
                self.assertEqual([t['label'] for t in out['terminals']], ['+V1', '+V2', '-V1', '-V2', '-V3'])
                self.assertEqual([t['signal'] for t in out['terminals']], ['DC24V'] * 2 + ['DC0V'] * 3)
                self.assertFalse(any('pin' in t or 'number' in t for group in s['terminal_groups'] for t in group['terminals']))
                self.assertEqual(s['input']['allowable_ac_voltage_v'], [85, 264])
                self.assertEqual(s['input']['allowable_dc_voltage_v'], [90, 350])


if __name__ == '__main__':
    unittest.main()
