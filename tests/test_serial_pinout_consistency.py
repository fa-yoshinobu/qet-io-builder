import unittest

import gen_io_page as g
from renderers import communication, hmi
from renderers.notes import drawing_text


class SerialPinoutTest(unittest.TestCase):
    def test_all_serial_dsub_interfaces_have_nine_pin_rows(self):
        for definitions in (g.Q_COMM, g.IQR_COMM, g.FX5_COMM, g.GOT_BODY, g.GOT_OPTION):
            for model, spec in definitions.items():
                if spec.get('option_type') == 'serial_conversion_cable':
                    continue  # 変換ケーブルは内部全結線の資料がないため推測しない
                for item in spec.get('interfaces', []):
                    if not item['kind'].startswith('dsub9') or 'PROFIBUS' in spec.get('network', ''):
                        continue
                    with self.subTest(model=model, interface=item['name']):
                        rows = communication.interface_rows(item)
                        self.assertEqual({r['pin'] for r in rows}, {str(i) for i in range(1, 10)})
                        self.assertEqual(len(rows), 9)

    def test_got_shared_port_displays_selected_mode(self):
        spec = g.GOT_BODY['GT3710-XRBD']
        for mode, signal in [('RS-232', 'DR (DSR)'), ('RS-422/485', 'RDA')]:
            page = hmi.build_body(dict(model='GT3710-XRBD', serial_mode=mode), g.build_symbols(), spec, g.Page, g.Symbol, g.page_heading)
            self.assertIn(signal, [t.get('text') for t in page.texts])

    def test_nc_pin_is_not_an_extra_connection(self):
        rows = communication.interface_rows(g.GOT_OPTION['GT15-RS2-9P']['interfaces'][0])
        self.assertEqual(rows[-1]['signal'], 'NC')
        self.assertFalse(rows[-1]['connectable'])

    def test_status_is_omitted_but_wiring_notes_remain(self):
        self.assertEqual(drawing_text('配列は未確認。SLD・FGは内部接続。'), 'SLD・FGは内部接続。')
        page = g.Page({})
        page.text(0, 0, '要確認')
        self.assertFalse(page.texts)


if __name__ == '__main__':
    unittest.main()
