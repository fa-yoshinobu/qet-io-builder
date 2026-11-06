import tempfile
import unittest
from collections import Counter
from pathlib import Path

import gen_io_page as gen
from renderers import connectors
from renderers.touchpanels import _right
from renderers.unit_diagrams import build_pages
from webgui.api import Api


class TouchpanelTest(unittest.TestCase):
    def test_all_real_ports_remain_with_correct_wiring_side(self):
        for model, spec in gen.UNIT_DIAGRAMS.items():
            if spec['function'] != 'タッチパネル':
                continue
            with self.subTest(model=model):
                symbols = gen.build_symbols()
                pages = build_pages({'model': model}, spec, symbols)
                expected = Counter()
                for section in spec['sections']:
                    connection = section.get('connector')
                    if not connection:
                        continue
                    expanded = section.get('expand') or len(section.get('terminals', [])) > 12
                    key = connectors.symbol(symbols, gen.Symbol, connection['kind'], connection.get('gender', ''),
                                            wired=not expanded, terminal_side='right' if _right(section) else 'left')
                    expected[key] += 1
                actual = Counter(key for _, page in pages for key, _, _, _ in page.placed if key.startswith('conn_'))
                self.assertEqual(actual, expected)
                for _, page in pages:
                    for key, _, x, _ in page.placed:
                        if key.startswith(('conn_usb', 'conn_vga', 'conn_dvi', 'conn_audio', 'conn_sd')):
                            self.assertGreater(x, 585)
                            self.assertTrue(all(t[1] == 'e' for t in symbols[key].terminals.values()))
                        elif key.startswith('conn_rj45'):
                            self.assertLess(x, 585)
                            self.assertTrue(all(t[1] == 'w' for t in symbols[key].terminals.values()))

    def test_only_real_dc_input_is_automatically_wired(self):
        for model in ['VT5-X15', 'NA5-15W101S-V1', 'VT3-X15']:
            with self.subTest(model=model):
                pages = build_pages({'model': model}, gen.UNIT_DIAGRAMS[model], gen.build_symbols())
                power = []
                for _, page in pages:
                    connected = {wire.get(k) for wire in page.conductors for k in ['element1', 'element2']}
                    for key, element, _, _ in page.placed:
                        if key == 'module_pin' and element.get('uuid') in connected:
                            power.append(element.findtext("elementInformations/elementInformation[@name='label']"))
                self.assertEqual(len(power), 0 if model == 'VT3-X15' else 2)
                self.assertFalse(any(label in ['FG', 'PE', 'DC5V'] for label in power))

    def test_omron_ethernet_panels_keep_ip_field(self):
        for model, spec in gen.UNIT_DIAGRAMS.items():
            if spec['function'] != 'タッチパネル' or spec['manufacturer'] != 'omron':
                continue
            pages = build_pages({'model': model}, spec, gen.build_symbols())
            self.assertTrue(any(text.get('text') == 'IP設定' for _, page in pages for text in page.texts), model)

    def test_gui_api_generates_both_panel_families(self):
        api = Api()
        with tempfile.TemporaryDirectory() as folder:
            vt = Path(folder) / 'vt.qet'
            na = Path(folder) / 'na.qet'
            self.assertTrue(api.generate_kv('VT5', 'VT5-X15', '1', 'TP1', str(vt))['ok'])
            self.assertTrue(api.generate_nx('NA5-15W101S-V1', '2', 'TP2', str(na))['ok'])
            for target in [vt, na]:
                self.assertTrue(gen.ET.parse(target).getroot().findall('diagram'))
            self.assertIn('error', api.generate_kv('VT5', 'NA5-15W101S-V1', '', '', str(vt)))


if __name__ == '__main__':
    unittest.main()
