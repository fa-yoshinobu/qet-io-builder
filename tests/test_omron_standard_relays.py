"""MY/LYの本体端子図を根拠に、標準記号へ渡す端子情報を確認する。"""
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1] / 'parts/control/omron'


def spec(model):
    family = 'my' if model.startswith('MY') else 'ly'
    return json.loads((ROOT / family / 'relay' / (model + '.json')).read_text(encoding='utf-8'))['definition']


class OmronStandardRelaysTest(unittest.TestCase):
    def test_twenty_five_basic_types_do_not_invent_voltage_skus(self):
        paths = [path for family in ('my', 'ly') for path in (ROOT / family / 'relay').glob('*.json')]
        self.assertEqual(len(paths), 25)
        self.assertEqual(sum(p.parent.parent.name == 'my' for p in paths), 15)
        self.assertEqual(sum(p.parent.parent.name == 'ly' for p in paths), 10)
        for path in paths:
            data = json.loads(path.read_text(encoding='utf-8'))
            with self.subTest(model=data['model']):
                self.assertEqual(data['category'], 'standard_device')
                self.assertEqual(data['model'], path.stem)
                self.assertNotIn(' DC24', data['model'])
                self.assertNotIn('rated_voltage', data['definition']['coil'])
                self.assertEqual(data['definition']['coil']['surge'], 'none')
                self.assertEqual(data['definition']['coil']['polarity'], 'none')
                self.assertTrue(data['definition']['source'])

    def test_real_relay_numbers_are_not_iec_socket_numbers(self):
        # MY: SGFR-223AK p20-23、LY: CSM_LY_DS_J_6_1 p12-13。
        cases = {
            'MY2N': (['13', '14'], [('9', '5', '1'), ('12', '8', '4')]),
            'MY3N': (['10', '11'], [('7', '4', '1'), ('8', '5', '2'), ('9', '6', '3')]),
            'MY4N': (['13', '14'], [('9', '5', '1'), ('10', '6', '2'), ('11', '7', '3'), ('12', '8', '4')]),
            'LY2N': (['7', '8'], [('5', '3', '1'), ('6', '4', '2')]),
        }
        for model, (coil, expected) in cases.items():
            with self.subTest(model=model):
                item = spec(model)
                self.assertEqual(item['coil']['terminals'], coil)
                self.assertEqual([(c['common'][0], c['no'][0], c['nc'][0]) for c in item['contacts']], expected)
                self.assertEqual(item['terminal_numbering'], 'relay_body')
                self.assertTrue(item['socket_candidates'])

    def test_ly1_parallel_physical_pins_remain_one_changeover(self):
        for model in ('LY1', 'LY1N'):
            with self.subTest(model=model):
                item = spec(model)
                self.assertEqual(item['coil']['terminals'], ['7', '8'])
                self.assertEqual(item['contacts'], [{'type': 'changeover', 'common': ['5', '6'], 'no': ['3', '4'], 'nc': ['1', '2']}])
                self.assertTrue(any('資料不一致' in note for note in item['notes']))

    def test_every_body_terminal_is_accounted_for_without_duplication(self):
        for path in [path for family in ('my', 'ly') for path in (ROOT / family / 'relay').glob('*.json')]:
            data = json.loads(path.read_text(encoding='utf-8'))
            item = data['definition']
            pins = item['coil']['terminals'] + [p for c in item['contacts'] for group in ('common', 'no', 'nc') for p in c[group]]
            with self.subTest(model=data['model']):
                self.assertEqual(len(pins), len(set(pins)))
                expected = 14 if len(item['contacts']) == 4 else 11 if len(item['contacts']) == 3 else 8
                self.assertEqual(len(pins), expected)


if __name__ == '__main__':
    unittest.main()
