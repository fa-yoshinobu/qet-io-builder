"""T205-E1_2_1 p1～3/p7の定格・外部端子に基づく確認。"""
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1] / 'parts/power_supply/omron/s8vk_s/power_supply'


class OmronS8vkSPartsTest(unittest.TestCase):
    def spec(self, suffix):
        data = json.loads((ROOT / ('S8VK-S' + suffix + '.json')).read_text(encoding='utf-8'))
        self.assertEqual(data['category'], 'power_supply')
        return data['definition']

    def test_all_duplicate_power_connections_are_preserved(self):
        for suffix in ('03024', '06024', '12024', '24024', '48024'):
            with self.subTest(suffix=suffix):
                groups = self.spec(suffix)['terminal_groups']
                self.assertEqual([t['label'] for t in groups[0]['terminals']], ['L1', 'L2', 'N1', 'N2', 'PE'])
                self.assertEqual([t['label'] for t in groups[1]['terminals']], ['+V1', '+V2', '-V1', '-V2', '-V3'])
                self.assertTrue(all('pin' not in t and 'number' not in t for group in groups for t in group['terminals']))

    def test_dc_low_exists_only_on_two_large_models(self):
        for suffix in ('03024', '06024', '12024'):
            self.assertEqual(len(self.spec(suffix)['terminal_groups']), 2)
        for suffix in ('24024', '48024'):
            group = self.spec(suffix)['terminal_groups'][2]
            self.assertEqual(group['role'], 'signal')
            self.assertEqual([t['label'] for t in group['terminals']], ['DC LOW1', 'DC LOW2'])
            self.assertIn('無極性', group['rating'])


if __name__ == '__main__':
    unittest.main()
