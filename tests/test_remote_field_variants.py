"""SH-082239-L/081636-E/081916-E/081760-Eの追加形式回帰確認。"""
import contextlib
import csv
import io
import json
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

import gen_io_page as g
import gui


ROOT = Path(__file__).resolve().parents[1]
MODELS = (
    'NZ2GN2S1-16D', 'NZ2GN2S1-32D', 'NZ2GN2B1-16D', 'NZ2GN2B1-32D',
    'NZ2GNCF1-32D', 'NZ2GNCE3-32D', 'NZ2GN12A4-16D', 'NZ2GN12A4-16DE',
    'NZ2GN2S1-16T', 'NZ2GN2S1-32T', 'NZ2GN2B1-16T', 'NZ2GN2B1-32T',
    'NZ2GNCF1-32T', 'NZ2GN12A2-16T', 'NZ2GN2S1-16TE', 'NZ2GN2S1-32TE',
    'NZ2GN2B1-16TE', 'NZ2GN2B1-32TE', 'NZ2GN12A2-16TE',
    'NZ2GN2S1-32DT', 'NZ2GN2B1-32DT', 'NZ2GNCE3-32DT', 'NZ2GN12A42-16DT',
    'NZ2GN2S1-32DTE', 'NZ2GN2B1-32DTE', 'NZ2GN12A42-16DTE',
    'NZ2GF12A4-16D', 'NZ2GF12A4-16DE', 'NZ2GF12A2-16T', 'NZ2GF12A2-16TE',
    'NZ2GF12A42-16DT', 'NZ2GF12A42-16DTE', 'NZ2GF2S-60IOLD8', 'NZ2GF12A-60IOLH8',
)


def definitions():
    units = g.read_unit_definitions()
    return {m: (category, units[category][m])
            for category in ('remote_io', 'remote_mixed', 'remote_iolink')
            for m in MODELS if m in units[category]}


class RemoteFieldVariantsTest(unittest.TestCase):
    def test_inventory_and_pin_reference_integrity(self):
        units = definitions()
        self.assertEqual(set(units), set(MODELS))
        for model, (category, spec) in units.items():
            with self.subTest(model=model):
                self.assertEqual(spec['network'], 'CC-Link IE Field')
                for connector in spec['power_connectors'] + spec['io_connectors']:
                    pins = [pin for pin, _ in connector['pins']]
                    self.assertEqual(len(pins), len(set(pins)))
                    self.assertTrue(set(connector.get('no_connect_pins', [])) <= set(pins))
                directions = ('input', 'output') if category == 'remote_mixed' else (None,)
                if category == 'remote_iolink':
                    self.assertEqual(len(spec['channels']), 8)
                    self.assertNotIn('io', spec)
                    continue
                for direction in directions:
                    signal = spec[direction] if direction else spec
                    self.assertEqual(len(signal['pins']), signal['points'])
                    self.assertEqual(len(signal['pins']), len(set(signal['pins'])))

    def test_waterproof_generation_power_and_pin_five_differences(self):
        units = definitions()
        new = units['NZ2GN12A4-16D'][1]
        old = units['NZ2GF12A4-16D'][1]
        self.assertEqual(new['power_connectors'][0]['connector_type'], 'm12_l_5')
        self.assertEqual(old['power_connectors'][0]['connector_type'], '7_8_5')
        self.assertEqual(dict(new['power_connectors'][0]['pins'])['3'], '24G(UNIT)')
        self.assertEqual(dict(old['power_connectors'][0]['pins'])['3'], 'FG')
        self.assertEqual(dict(new['power_connectors'][0]['pins'])['FE'], 'FG')
        for model, (_, spec) in units.items():
            if not model.startswith(('NZ2GN12', 'NZ2GF12A4', 'NZ2GF12A2')):
                continue
            with self.subTest(model=model):
                for connector in spec['io_connectors']:
                    self.assertEqual(dict(connector['pins'])['5'], 'アキ' if model.startswith('NZ2GN') else 'FG')
        for spec in (new, old):
            self.assertEqual(spec['pins'][:2], ['X0/X1-4', 'X0/X1-2'])

    def test_mixed_address_offsets_and_fcn_control_pins(self):
        units = definitions()
        for model, (category, spec) in units.items():
            if category != 'remote_mixed':
                continue
            with self.subTest(model=model):
                self.assertEqual(spec['input']['start_offset'], 0)
                self.assertEqual(spec['output']['start_offset'], spec['input']['points'])
                if model.startswith(('NZ2GN12', 'NZ2GF12')):
                    self.assertEqual(spec['output']['pins'][0], 'Y8/Y9-4')
                elif 'CE3' not in model:
                    self.assertEqual(spec['output']['pins'][0], 'TB17')
                    self.assertEqual(spec['output']['vplus'], 'TB33')
                    self.assertEqual(spec['output']['com'], 'TB34')
        fcn = units['NZ2GNCF1-32D'][1]
        self.assertEqual(fcn['common'], ['B1', 'B2'])
        self.assertTrue({'A1', 'A2', 'A3', 'A4', 'B3', 'B4'} <= set(fcn['io_connectors'][0]['no_connect_pins']))
        self.assertEqual(fcn['pins'][:2], ['B20', 'B19'])
        self.assertEqual(fcn['pins'][16:18], ['A20', 'A19'])

    def test_unconfirmed_source_pin_and_internal_nc_are_blocked(self):
        units = definitions()
        spec = units['NZ2GN12A2-16TE'][1]
        self.assertEqual(spec['vplus'], '')
        self.assertEqual(spec['com'], '')
        self.assertFalse(spec['confirmed'])
        for connector in spec['io_connectors']:
            self.assertEqual(dict(connector['pins'])['3'], '未確認')
            self.assertIn('3', connector['no_connect_pins'])
            self.assertIn('3', connector['unconfirmed_pins'])
        mixed = units['NZ2GNCE3-32DT'][1]
        for connector in mixed['io_connectors'][16:]:
            self.assertEqual(dict(connector['pins'])['2'], 'NC')
            self.assertIn('2', connector['no_connect_pins'])

    def test_iolink_is_separate_and_has_real_power_and_channel_pins(self):
        units = definitions()
        category, spec = units['NZ2GF2S-60IOLD8']
        self.assertEqual(category, 'remote_iolink')
        self.assertNotIn('NZ2GF2S-60IOLD8', g.IO_UNITS)
        pins = dict(spec['io_connectors'][0]['pins'])
        self.assertEqual([pins[str(i)] for i in (9, 10, 11, 12)], ['L1+', 'L1-', 'CQ1', 'DI1'])
        self.assertEqual([pins[str(i)] for i in (37, 38, 39, 40)], ['L8+', 'L8-', 'CQ8', 'DI8'])
        self.assertEqual(dict(spec['power_connectors'][0]['pins']), {'1': '+24V', '2': '24G', '3': 'FG'})
        waterproof = units['NZ2GF12A-60IOLH8'][1]
        self.assertEqual(dict(waterproof['io_connectors'][0]['pins']),
                         {'1': 'L+', '2': 'Q', '3': 'L-', '4': 'CQ', '5': 'FG'})
        self.assertEqual(dict(waterproof['power_connectors'][0]['pins'])['1'], '24G(UA)')

    def test_unknown_and_nc_pins_do_not_create_wiring_terminals(self):
        units = definitions()
        for model, expected_count in [('NZ2GN12A2-16TE', 16), ('NZ2GNCE3-32DT', 112)]:
            with self.subTest(model=model):
                pages = g.remote_connector_pages({'model': model}, g.build_symbols(), units[model][1])
                pins = [element for _, page in pages for kind, element, _, _ in page.placed
                        if kind == 'module_pin']
                self.assertEqual(len(pins), expected_count)
                self.assertTrue(all(not page.conductors for _, page in pages))
                if model == 'NZ2GN12A2-16TE':
                    labels = [info.text for element in pins
                              for info in element.findall('./elementInformations/elementInformation')
                              if info.get('name') == 'label']
                    self.assertNotIn('3', labels)
                    self.assertEqual(set(labels), {'2', '4'})

    def test_all_models_generate_and_are_in_the_correct_picker(self):
        config = json.loads((ROOT / 'tests/fixtures/project.json').read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            for model, (category, spec) in definitions().items():
                with self.subTest(model=model):
                    pages = [{'kind': 'remotebody', 'model': model}]
                    if category == 'remote_iolink':
                        kind = 'remoteiolink'
                        pages = [{'kind': kind, 'model': model}]
                    elif category == 'remote_mixed':
                        kind = 'remotemixed'
                        for direction, prefix in [('input', 'X'), ('output', 'Y')]:
                            signal = spec[direction]
                            with (folder / (direction + '.csv')).open('w', encoding='utf-8-sig', newline='') as stream:
                                writer = csv.writer(stream)
                                writer.writerow(['アドレス', '機器番号', '信号名'])
                                writer.writerows([[f'{prefix}{i + signal["start_offset"]:X}', '', '予備']
                                                  for i in range(signal['points'])])
                        pages.append({'kind': kind, 'model': model, 'input_csv': 'input.csv', 'output_csv': 'output.csv'})
                    else:
                        kind = 'input' if spec['io'] == 'in' else 'output'
                        prefix = 'X' if kind == 'input' else 'Y'
                        with (folder / 'io.csv').open('w', encoding='utf-8-sig', newline='') as stream:
                            writer = csv.writer(stream)
                            writer.writerow(['アドレス', '機器番号', '信号名'])
                            writer.writerows([[f'{prefix}{i:X}', '', '予備'] for i in range(spec['points'])])
                        pages.append({'kind': kind, 'model': model, 'csv': 'io.csv'})
                    config['pages'] = pages
                    (folder / 'project.json').write_text(json.dumps(config, ensure_ascii=False), encoding='utf-8')
                    with contextlib.redirect_stdout(io.StringIO()):
                        g.main(str(folder / 'project.json'), str(folder / 'result.qet'))
                    diagrams = ET.parse(folder / 'result.qet').findall('.//diagram')
                    self.assertGreater(len(diagrams), 1)
                    self.assertIn(model, gui.part_catalog('model', kind)['mitsubishi']['cclink_ie'])
                    text = ET.tostring(ET.parse(folder / 'result.qet').getroot(), encoding='unicode')
                    for connector in spec['io_connectors']:
                        for pin, signal in connector['pins']:
                            self.assertIn(signal, text)


if __name__ == '__main__':
    unittest.main()
