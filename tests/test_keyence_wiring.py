import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import gen_io_page as gen
from renderers.keyence import build_pages
from webgui.api import Api


class KeyenceWiringTest(unittest.TestCase):
    def test_all_unit_io_terminals_are_wired_and_nc_has_no_drawing_row(self):
        for model, spec in gen.KV_IO.items():
            with self.subTest(model=model):
                pages = build_pages(dict(kind='kv_io', model=model), spec, gen.build_symbols())
                for _, page in pages[1:] if spec.get('body') else pages:
                    connected = {c.get(key) for c in page.conductors for key in ('element1', 'element2')}
                    for key, element, _, _ in page.placed:
                        if not key.startswith(('plc_in_kv', 'plc_out_kv')):
                            continue
                        signal = element.findtext("elementInformations/elementInformation[@name='label']")
                        self.assertNotEqual(signal, 'NC')
                        if not spec.get('analog'):
                            self.assertIn(element.get('uuid'), connected)
                    diagonals = [s for s in page.shapes if s.get('type') == 'Line'
                                 and s.get('x1') != s.get('x2') and s.get('y1') != s.get('y2')]
                    self.assertEqual(len(diagonals), 0)

    def test_sixteen_point_unit_stays_in_one_column_with_commons(self):
        page = build_pages(dict(kind='kv_io', model='KV-B16XC'), gen.KV_IO['KV-B16XC'], gen.build_symbols())[0][1]
        terminals = [(x, y) for key, _, x, y in page.placed if key == 'plc_in_kv']
        self.assertEqual(len(terminals), 18)
        self.assertEqual(len({x for x, _ in terminals}), 1)
        self.assertLessEqual(max(y for _, y in terminals) + gen.ROW_PITCH / 2, 790)

    def test_body_power_labels_align_at_unit_terminal_and_nc_has_no_terminal(self):
        page = build_pages(dict(kind='kv_io', model='KV-N14DR'), gen.KV_IO['KV-N14DR'], gen.build_symbols())[0][1]
        wires = [c for c in page.conductors if c.get('num') in ('P24', 'N24')]
        self.assertEqual(len(wires), 2)
        self.assertEqual(wires[0].get('userx'), wires[1].get('userx'))
        self.assertGreater(float(wires[0].get('userx')), 230)
        cpu = next(symbol for key, _, _, _ in page.placed if key.startswith('plc_in_kv_nano_body')
                   for symbol in [page.sym[key]])
        self.assertFalse(any(key.startswith('service:') for key in cpu.terminals))
        self.assertEqual(sum(kind == 'circle' for kind, _ in cpu.parts), 3)
        self.assertFalse(any(kind == 'text' and 'NC' in attrs['text'] for kind, attrs in cpu.parts))

    def test_failed_save_keeps_existing_drawing(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'existing.qet'
            target.write_text('existing drawing', encoding='utf-8')
            with patch.object(gen.ET.ElementTree, 'write', side_effect=OSError('write failed')):
                result = Api().generate_kv('KV Nano', 'KV-N14DR', '', '', str(target))
            self.assertIn('error', result)
            self.assertEqual(target.read_text(encoding='utf-8'), 'existing drawing')

    def test_analog_preserves_physical_pin_identity_without_external_wiring(self):
        for model, spec in gen.KV_IO.items():
            if not spec.get('analog'):
                continue
            with self.subTest(model=model):
                page = build_pages(dict(kind='kv_io', model=model), spec, gen.build_symbols())[0][1]
                pins = [(e.findtext("elementInformations/elementInformation[@name='auxiliary1']"),
                         e.findtext("elementInformations/elementInformation[@name='label']"))
                        for key, e, _, _ in page.placed if key == 'plc_in_kv']
                self.assertEqual(pins, [(r['pin'], r['signal']) for r in spec['analog']['terminals']])
                self.assertEqual(len({pin for pin, _ in pins}), len(pins))
                self.assertTrue(all(y + 20 <= 755 for key, _, _, y in page.placed if key == 'plc_in_kv'))
                connected = {c.get(key) for c in page.conductors for key in ('element1', 'element2')}
                self.assertTrue(all(e.get('uuid') not in connected for key, e, _, _ in page.placed if key == 'plc_in_kv'))

    def test_serial_modes_preserve_selected_terminal_signals_and_reject_unknown_mode(self):
        spec = gen.KV_IO['KV-NC20L']
        for mode, interfaces in spec['module']['modes'].items():
            page = build_pages(dict(kind='kv_io', model='KV-NC20L', communication_mode=mode), spec, gen.build_symbols())[0][1]
            texts = [t.get('text') for t in page.texts]
            for row in interfaces[1]['pinout']:
                self.assertIn(row['signal'], texts)
            pins = [e for key, e, _, _ in page.placed if key == 'module_pin']
            self.assertEqual(len(pins), len(interfaces[1]['pinout']))
        with self.assertRaises(ValueError):
            build_pages(dict(kind='kv_io', model='KV-NC20L', communication_mode='invalid'), spec, gen.build_symbols())

    def test_european_two_terminal_blocks_preserve_unambiguous_pin_ids(self):
        for model in ('KV-NC32EXE', 'KV-NC32ETE', 'KV-NC16EXTE'):
            spec = gen.KV_IO[model]
            page = build_pages(dict(kind='kv_io', model=model), spec, gen.build_symbols())[0][1]
            terminals = [(key, e, y) for key, e, _, y in page.placed if key in ('plc_in_kv', 'plc_out_kv')]
            pins = [e.findtext("elementInformations/elementInformation[@name='auxiliary1']") for _, e, _ in terminals]
            self.assertEqual(len(pins), len(set(pins)))
            self.assertEqual(set(pin[:1] for pin in pins), {'上', '下'})
            self.assertTrue(all(y + gen.ROW_PITCH / 2 <= 790 for _, _, y in terminals))
            if model == 'KV-NC16EXTE':
                for key, e, _ in terminals:
                    signal = e.findtext("elementInformations/elementInformation[@name='label']")
                    self.assertEqual(key == 'plc_in_kv', signal.startswith('0') or signal == 'COM0')

    def test_remote_adapter_has_two_lan_ports_and_functional_power_without_pin_numbers(self):
        spec = gen.KV_IO['KV-EP02']
        page = build_pages(dict(kind='kv_io', model='KV-EP02'), spec, gen.build_symbols())[0][1]
        power = [e for key, e, _, _ in page.placed if key == 'module_pin']
        labels = [e.findtext("elementInformations/elementInformation[@name='label']") for e in power]
        self.assertEqual(labels, [r['signal'] for r in spec['module']['power']])
        self.assertTrue(all(e.findtext("elementInformations/elementInformation[@name='auxiliary1']") in (None, '') for e in power))
        wired = {c.get(k) for c in page.conductors for k in ('element1', 'element2')}
        self.assertTrue(all(e.get('uuid') in wired for e in power[:2]))
        self.assertNotIn(power[2].get('uuid'), wired)
        self.assertEqual(sum(key == 'conn_rj45' for key, _, _, _ in page.placed), 2)
        self.assertEqual({c.get('num') for c in page.conductors if c.get('num')}, {'P24', 'N24'})
        setting = next(t for t in page.texts if t.get('text') == 'IP設定')
        self.assertGreater(float(setting.get('x')), gen.FX_IN_X['inner'])

    def test_sir32xt_output_fits_one_page_without_losing_terminals(self):
        pages = build_pages(dict(kind='kv_io', model='KV-SIR32XT'), gen.KV_IO['KV-SIR32XT'], gen.build_symbols())
        self.assertEqual(len(pages), 2)
        page = pages[1][1]
        terminals = [(key, element, y) for key, element, _, y in page.placed if key.startswith('plc_out_kv')]
        signals = [e.findtext("elementInformations/elementInformation[@name='label']") for _, e, _ in terminals]
        self.assertEqual(sum(signal.isdecimal() for signal in signals), 32)
        self.assertNotIn('NC', signals)
        self.assertEqual(signals.count('COM2'), 2)
        self.assertEqual(signals.count('COM3'), 2)
        self.assertTrue(any('NCピン33・34・35・36は接続しない' in text.get('text', '') for text in page.texts))
        for key, _, y in terminals:
            self.assertNotIn('_short', key)
            self.assertLessEqual(y + 20, 790)

    def test_independent_relay_keeps_each_common_with_its_output(self):
        page = build_pages(dict(kind='kv_io', model='KV-N8ER'), gen.KV_IO['KV-N8ER'], gen.build_symbols())[0][1]
        signals = [element.findtext("elementInformations/elementInformation[@name='label']")
                   for key, element, _, _ in page.placed if key == 'plc_out_kv']
        self.assertEqual(signals, [signal for i in range(8) for signal in (f'C{i}', f'{i:03}')])
        groups = [shape for shape in page.shapes if shape.get('type') == 'Rectangle'
                  and float(shape.get('x2')) - float(shape.get('x1')) == 100]
        self.assertEqual(len(groups), 8)
        self.assertTrue(all(float(shape.get('y2')) - float(shape.get('y1')) == 80 for shape in groups))


if __name__ == '__main__':
    unittest.main()
