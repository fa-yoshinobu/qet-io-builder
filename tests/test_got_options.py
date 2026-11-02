"""通信オプションの物理コネクタと適用条件（個別取扱説明書に基づく）。"""
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1] / 'parts/hmi/mitsubishi/got_options/communication'


def definition(model):
    return json.loads((ROOT / (model + '.json')).read_text(encoding='utf-8'))['definition']


class GotOptionsTest(unittest.TestCase):
    def test_options_use_half_or_full_height_including_module_variants(self):
        import gen_io_page as gen

        for model, spec in gen.GOT_OPTION.items():
            for module in ['', *spec.get('module_interfaces', {})]:
                with self.subTest(model=model, module=module):
                    page = {'kind': 'gotoption', 'left_model': model, 'left_module': module,
                            'right_model': 'GT15-QBUS'}
                    root, _ = gen.build_project(gen.project_config({'front_pages': False}), [(page, None)])
                    boxes = {float(s.get('x1')): float(s.get('y2'))
                             for s in root.findall('./diagram/shapes/shape')
                             if s.get('type') == 'Rectangle' and float(s.get('y1')) == 52}
                    self.assertEqual(boxes[895], 422)
                    if model in ('GT01-RS4-M', 'GT10-9PT5S'):
                        self.assertGreater(boxes[275], 700)
                        self.assertLessEqual(boxes[275], 790)
                    else:
                        self.assertEqual(boxes[275], 422)
                    for element in root.findall('./diagram/elements/element'):
                        x, y = float(element.get('x')), float(element.get('y'))
                        if 275 <= x <= 585:
                            self.assertLess(y, boxes[275])

    def test_twenty_four_models_keep_option_roles(self):
        models = list(ROOT.glob('*.json'))
        self.assertEqual(len(models), 24)
        self.assertFalse((ROOT / 'GT25-WLAN.json').exists())
        for path in models:
            data = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(data['category'], 'got_option')
            self.assertEqual(data['model'], path.stem)
            self.assertTrue(data['definition']['source'])
        self.assertEqual(definition('GT35-C02HR2-9P')['option_type'], 'serial_conversion_cable')
        self.assertEqual(definition('GT37-IF2000')['option_type'], 'extension_converter')
        for model in ('GT37-IF2000', 'GT25-FNADP'):
            self.assertEqual(definition(model)['interfaces'], [])

    def test_real_terminal_labels_and_numbers(self):
        # IB-0800325E-P / SH-081200ENG-AS 図5
        terminal = definition('GT15-RS4-TE')['interfaces'][0]
        self.assertEqual(terminal['port_pins'], [str(i) for i in range(1, 11)])
        self.assertEqual(terminal['ports'], ['SDA1', 'SDB1', 'RDA1', 'RDB1', 'SDA2', 'SDB2', 'RDA2', 'RDB2', 'SG', 'FG'])
        # IB-0800351E-M 端子台の外観順。仮の端子番号を付けない。
        cc = definition('GT15-J61BT13')
        self.assertEqual(cc['interfaces'][0]['ports'], ['FG', 'SLD', 'DG', 'DB', 'DA'])
        self.assertNotIn('port_pins', cc['interfaces'][0])
        self.assertEqual(cc['internal_connections'], [['SLD', 'FG']])
        adapter = definition('GT10-9PT5S')['interfaces']
        self.assertEqual(adapter[1]['port_pins'] + adapter[2]['port_pins'], [str(i) for i in range(1, 11)])

    def test_cable_connectors_are_not_guessed_signal_conversion(self):
        self.assertEqual(definition('GT15-J71BR13')['interfaces'][0]['kind'], 'coax_bnc')
        self.assertEqual([i['connector_label'] for i in definition('GT15-J71GP23-SX')['interfaces']], ['Duplex LC'] * 2)
        self.assertEqual([i['connector_label'] for i in definition('GT15-J71LP23-25')['interfaces']], ['2心光'] * 2)
        for model in ('GT15-QBUS', 'GT15-ABUS', 'GT15-75QBUSL', 'GT15-75ABUSL'):
            self.assertEqual([i['name'] for i in definition(model)['interfaces']], ['IN'])
        for model in ('GT15-QBUS2', 'GT15-ABUS2', 'GT15-75QBUS2L', 'GT15-75ABUS2L'):
            self.assertEqual([i['name'] for i in definition(model)['interfaces']], ['IN', 'OUT'])
        self.assertTrue(all(i['kind'] == 'dsub9_neutral' for i in definition('GT35-C02HR2-9P')['interfaces']))

    def test_got3000_requires_if2000_and_not_all_options_compatible(self):
        specs = [json.loads(p.read_text(encoding='utf-8'))['definition'] for p in ROOT.glob('*.json')]
        self.assertEqual(sum(bool(s['adapter_required']) for s in specs), 13)
        for model in ('GT25-J71E71-100', 'GT25-FNADP', 'GT01-RS4-M'):
            self.assertNotIn('GOT3000', definition(model)['compatible_series'])
        self.assertEqual(definition('GT15-ABUS')['unconfirmed_series'], ['GOT3000'])


if __name__ == '__main__':
    unittest.main()
