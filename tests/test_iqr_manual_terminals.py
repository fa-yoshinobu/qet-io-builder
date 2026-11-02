"""SH-081232/081235/081580/081655の端子表などに基づく回帰確認。"""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

import gen_io_page as g


class IqrManualTerminalsTest(unittest.TestCase):
    def test_terminal_block_signal_order(self):
        # R60AD4/DA4は定義の信号順と実番号順が一致しない。
        cases = {
            'R60AD4': (['1', '3', '2', '4'], ['13', '15', '14', '16'], ['17', '18']),
            'R60ADH4': (['1', '2', '3', '4'], ['13', '14', '15', '16'], ['17', '18']),
            'R60ADV8': (['1', '2'], ['15', '16'], ['17', '18']),
            'R60ADI8': (['1', '2'], ['15', '16'], ['17', '18']),
            'R60DA4': (['1', '3', '2'], ['13', '15', '14'], ['16', '17', '18']),
            'R60DAH4': (['1', '2', '3'], ['13', '14', '15'], ['16', '17', '18']),
            'R60DAV8': (['1', '2'], ['15', '16'], ['17', '18']),
            'R60DAI8': (['1', '2'], ['15', '16'], ['17', '18']),
        }
        for model, (first, last, supply) in cases.items():
            with self.subTest(model=model):
                spec = g.IQR_ANALOG[model]
                self.assertEqual(spec['pins_by_channel'][0], first)
                self.assertEqual(spec['pins_by_channel'][-1], last)
                self.assertEqual(spec['power_pins'], supply)
                pins = [p for ch in spec['pins_by_channel'] for p in ch] + supply
                self.assertEqual(len(pins), len(set(pins)))
        for model in ('R60DAV8', 'R60DAI8'):
            self.assertNotIn('FG', g.IQR_ANALOG[model]['power'])
        for model in ('R60DA4', 'R60DAH4'):
            self.assertEqual(g.IQR_ANALOG[model]['unconnected_pins'], ['4', '8', '12'])

    def test_compensation_is_not_external_supply(self):
        for model, expected in {
            'R60TD8-G': [('B19', 'RTD+'), ('B20', 'RTD-'), ('A20', 'RTDG')],
            'R60TRD4-G': [('TB1', 'RTD+')],
        }.items():
            with self.subTest(model=model):
                spec = g.IQR_ANALOG[model]
                self.assertEqual([(t['pin'], t['signal']) for t in spec['auxiliary_terminals']], expected)
                self.assertFalse(any(s.startswith('RTD') for s in spec['power']))
                self.assertTrue(all(t['group'] == '冷接点補償' for t in spec['auxiliary_terminals']))

    def test_hart_has_position_labels_instead_of_invented_tb_numbers(self):
        spec = g.IQR_ANALOG['R60ADI8-HA']
        self.assertEqual(spec['pin_label_basis'], 'physical_position')
        self.assertEqual(spec['pins_by_channel'][0], ['左1段', '左2段', '右1段', '右2段'])
        self.assertEqual(spec['power_pins'], ['左17段', '右17段', '左18段', '右18段', '左20段'])
        self.assertFalse(any(p.startswith('TB') for ch in spec['pins_by_channel'] for p in ch))

    def test_cc_link_terminal_order_and_cpu_sd_capability(self):
        spec = g.IQR_COMM['RJ61BT11']
        self.assertEqual(list(zip(spec['port_pins'], spec['ports'])),
                         [('3', 'DA'), ('4', 'SLD'), ('5', 'DB'), ('6', 'FG'), ('7', 'DG')])
        self.assertEqual(spec['unconnected_pins'], ['1', '2'])
        self.assertTrue(spec['shield_ground_connected'])
        self.assertFalse(g.IQR_CPU['R00CPU']['sd_card_supported'])
        self.assertTrue(g.IQR_CPU['R01CPU']['sd_card_supported'])
        self.assertTrue(g.IQR_CPU['R02CPU']['sd_card_supported'])

    def test_numbers_and_compensation_reach_generated_diagrams(self):
        models = ['R60AD4', 'R60DA4', 'R60ADI8-HA', 'R60TD8-G', 'R60TRD4-G']
        config = json.loads((Path(__file__).parent / 'fixtures' / 'project.json').read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            for model in models:
                with self.subTest(model=model):
                    config['pages'] = [{'kind': 'iqranalog', 'model': model}]
                    (folder / 'project.json').write_text(json.dumps(config, ensure_ascii=False), encoding='utf-8')
                    with contextlib.redirect_stdout(io.StringIO()):
                        g.main(str(folder / 'project.json'), str(folder / 'result.qet'))
                    values = [e.text for e in ET.parse(folder / 'result.qet').findall('.//diagram//elementInformation')]
                    spec = g.IQR_ANALOG[model]
                    expected = [pin for ch in spec['pins_by_channel'] for pin in ch] + spec['power_pins']
                    expected += [t['pin'] for t in spec.get('auxiliary_terminals', [])]
                    for pin in expected:
                        self.assertIn(pin, values)
                    if model == 'R60ADI8-HA':
                        self.assertNotIn('TB1', values)

    def test_cc_link_pin_numbers_and_missing_sd_slot_are_displayed(self):
        page = g.build_q_comm_page({'kind': 'iqrcomm', 'left_model': 'RJ61BT11'}, g.build_symbols())
        labels = [info.text for kind, element, _, _ in page.placed if kind == 'module_pin'
                  for info in element.findall('./elementInformations/elementInformation')
                  if info.get('name') == 'label']
        self.assertEqual(labels, ['3  DA', '4  SLD', '5  DB', '6  FG', '7  DG'])
        self.assertIn('SLD・FG 内部接続', [text.get('text') for text in page.texts])
        config = json.loads((Path(__file__).parent / 'fixtures' / 'project.json').read_text(encoding='utf-8'))
        config['pages'] = [{'kind': 'iqrbody', 'model': 'R00CPU', 'power_model': 'R61P',
                            'base_model': 'R35B', 'modules': []}]
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / 'project.json').write_text(json.dumps(config, ensure_ascii=False), encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()):
                g.main(str(folder / 'project.json'), str(folder / 'result.qet'))
            inputs = ET.parse(folder / 'result.qet').findall('.//diagram/inputs/input')
            self.assertIn('搭載不可', [text.get('text') for text in inputs])

    def test_isolated_current_input_has_voltage_current_jumper(self):
        config = json.loads((Path(__file__).parent / 'fixtures' / 'project.json').read_text(encoding='utf-8'))
        for model, voltage_pin, current_pin in [('R60AD8-G', 'A1', 'A2'), ('R60AD16-G', '1A1', '1A2')]:
            with self.subTest(model=model):
                page = g.build_fx_analog_page({'kind': 'iqranalog', 'model': model}, config,
                                             g.build_symbols(), [{'CH': '1', '方式': '電流'}])
                # ピン番号は auxiliary1(表の「端子」欄)
                elements = {info.text: element.get('uuid') for _, element, _, _ in page.placed
                            for info in element.findall('./elementInformations/elementInformation')
                            if info.get('name') == 'auxiliary1'}
                endpoints = {elements[voltage_pin], elements[current_pin]}
                self.assertTrue(any({wire.get('element1'), wire.get('element2')} == endpoints
                                    for wire in page.conductors))


if __name__ == '__main__':
    unittest.main()
