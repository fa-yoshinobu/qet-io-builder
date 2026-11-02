"""富士標準接触器の資料端子と、選択が必要な補助接点を確認する。"""
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / 'parts/control/fuji'


def definitions():
    return {data['model']: data['definition'] for path in ROOT.glob('*/contactor/*.json')
            for data in [json.loads(path.read_text(encoding='utf-8'))]}


class FujiStandardDevicesTest(unittest.TestCase):
    def test_fifty_base_models_and_real_main_terminals(self):
        specs = definitions()
        self.assertEqual(len(specs), 50)
        self.assertEqual(sum(s['series'] == 'SC-NEXT' for s in specs.values()), 26)
        expected = [['1/L1', '2/T1'], ['3/L2', '4/T2'], ['5/L3', '6/T3']]
        for model, spec in specs.items():
            with self.subTest(model=model):
                self.assertEqual(spec['device_type'], 'contactor')
                self.assertEqual(spec['standard_family'], 'contactor')
                self.assertEqual([c['terminals'] for c in spec['contacts']], expected)
                self.assertTrue(all(c['type'] == 'no' and c['role'] == 'main' for c in spec['contacts']))
                self.assertEqual(spec['coil']['terminals'], ['A1', 'A2'])
                self.assertTrue(spec['coil']['voltage_selection_required'])
                self.assertNotIn('voltage_v', spec['coil'])
                self.assertTrue(spec['source'])

    def test_dc_polarity_is_not_shared_across_series(self):
        specs = definitions()
        self.assertEqual(specs['SC09XG']['coil']['polarity_by_terminal'], {'A1': '+', 'A2': '-'})
        self.assertIn('無極性', specs['SC-03/G']['coil']['polarity'])
        self.assertNotIn('polarity_by_terminal', specs['SC-03/G']['coil'])
        self.assertNotIn('SC40XS', specs)
        self.assertNotIn('SC-N6', specs)
        self.assertNotIn('SC09XV', specs)

    def test_selectable_auxiliaries_are_not_given_a_default(self):
        specs = definitions()
        small = specs['SC09XA']
        self.assertTrue(small['auxiliary_selection_required'])
        self.assertNotIn('default_auxiliary_option', small)
        self.assertEqual([o['id'] for o in small['auxiliary_options']], ['1a', '1b'])
        medium = specs['SC20DA']
        self.assertEqual([o['id'] for o in medium['auxiliary_options']], ['2a', '1a1b', '2b'])
        self.assertEqual(medium['auxiliary_options'][2]['contacts'], [
            {'type': 'nc', 'terminals': ['11', '12'], 'role': 'auxiliary'},
            {'type': 'nc', 'terminals': ['21', '22'], 'role': 'auxiliary'}])

    def test_fixed_auxiliaries_preserve_next_vs_neo_numbers(self):
        specs = definitions()
        next_spec = specs['SC40XA']
        neo_spec = specs['SC-N1']
        self.assertFalse(next_spec['auxiliary_selection_required'])
        self.assertEqual(next_spec['default_auxiliary_option'], 'standard')
        self.assertEqual([c['terminals'] for c in next_spec['auxiliary_options'][0]['contacts']],
                         [['13', '14'], ['21', '22']])
        self.assertEqual([c['terminals'] for c in neo_spec['auxiliary_options'][0]['contacts']],
                         [['13', '14'], ['43', '44'], ['21', '22'], ['31', '32']])


if __name__ == '__main__':
    unittest.main()
