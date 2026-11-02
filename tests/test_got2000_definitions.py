"""GOT2000: SH-081194ENG-AWとSH-081200ENG-ASの機種差を保持する。"""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'parts/hmi/mitsubishi/got2000/body'
MODELS = [path.stem for path in sorted(ROOT.glob("*.json"))]


def definition(model):
    return json.loads((ROOT / (model + '.json')).read_text(encoding='utf-8'))['definition']


class Got2000DefinitionsTest(unittest.TestCase):
    def test_models_have_category_and_source(self):
        self.assertTrue(MODELS)
        for model in MODELS:
            data = json.loads((ROOT / (model + '.json')).read_text(encoding='utf-8'))
            self.assertEqual(data['category'], 'got_body')
            self.assertEqual(data['model'], model)
            self.assertTrue(data['definition']['source'])

    def test_power_marks_and_no_invented_independent_supply(self):
        self.assertEqual(definition('GT2715-XTBA')['power']['ports'], ['〜', '〜', '⏚', '⏚'])
        self.assertEqual(definition('GT2715-XTBD')['power']['ports'], ['−', '＋', '⏚', '⏚'])
        self.assertEqual(definition('GT2705-VTBD')['power']['ports'], ['⏚', '−', '＋'])
        self.assertEqual(definition('GT2104-PMBD')['power']['ports'], ['＋', '−', '⏚'])
        for model in ('GT2104-PMBLS', 'GT2103-PMBLS', 'GT2506HS-VTBD', 'GT2505HS-VTBD'):
            self.assertEqual(definition(model)['power']['ports'], [])

    def test_gt21_port_variants_do_not_inherit_gt27_equipment(self):
        for model in ('GT2105-QTBDS', 'GT2104-PMBDS', 'GT2103-PMBDS2'):
            self.assertFalse(any(i['kind'] == 'rj45' for i in definition(model)['interfaces']))
        self.assertEqual(sum(i['kind'] == 'rj45' for i in definition('GT2510-WXTBD')['interfaces']), 2)
        spec = definition('GT2104-RTBD')
        terminals = [i for i in spec['interfaces'] if i['kind'] == 'terminal']
        self.assertEqual(len(terminals), 1)
        self.assertEqual(terminals[0]['ports'], ['CSB','CSA','RSA','RSB','SG','RDB','RDA','SDB','SDA'])
        self.assertEqual(set(terminals[0]['modes']), {'RS-232', 'RS-422/485'})
        self.assertFalse(any(i['kind'].startswith('dsub') for i in spec['interfaces']))

    def test_handy_and_card_battery_variants(self):
        for model, kind, battery in [('GT2506HS-VTBD','handheld42','GT15-BAT'), ('GT2505HS-VTBD','handheld32','GT11-50BAT')]:
            spec = definition(model)
            self.assertEqual(spec['interfaces'][0]['kind'], kind)
            self.assertEqual(spec['battery_type'], battery)
            self.assertFalse(any(i['kind'] == 'rj45' for i in spec['interfaces']))
        for suffix in ('PMBD', 'PMBDS', 'PMBDS2'):
            spec = definition('GT2103-' + suffix)
            self.assertFalse(spec['sd_card_supported'])
            self.assertTrue(spec['sd_card_optional'])
            self.assertEqual(spec['sd_card_option'], 'GT21-03SDCD')
            self.assertFalse(spec['battery_supported'])
            self.assertFalse(any(i['kind']=='sd' for i in spec['interfaces']))
        for model in ('GT2104-PMBLS', 'GT2103-PMBLS'):
            self.assertFalse(definition(model)['sd_card_supported'])
            self.assertFalse(definition(model)['sd_card_optional'])

    def test_nc_is_not_a_connectable_terminal(self):
        for model in MODELS:
            for interface in definition(model)['interfaces']:
                self.assertNotIn('NC', interface.get('ports', []))
                for pin in interface.get('pinout', []):
                    if pin['signal'] == 'NC':
                        self.assertFalse(pin['connectable'])


if __name__ == '__main__':
    unittest.main()
