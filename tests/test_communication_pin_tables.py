import copy
import unittest

import gen_io_page as g
from renderers import communication


class CommunicationPinTableTest(unittest.TestCase):
    def panel(self, spec, x=895):
        symbols = g.build_symbols()
        page = g.Page(symbols)
        communication.draw_panel(page, symbols, spec, x, g.Symbol, {}, 'right')
        return page

    def test_profibus_pin_table_includes_nc_without_extra_connections(self):
        page = self.panel(g.IQR_COMM['RJ71PB91V'])
        texts = [t.get('text') for t in page.texts]
        for heading in ('ピンNo.', '信号', '用途'):
            self.assertEqual(texts.count(heading), 1)
        for pin in range(1, 10):
            self.assertEqual(texts.count(str(pin)), 1)
        self.assertEqual(texts.count('NC'), 5)
        self.assertEqual(texts.count('未使用'), 5)
        self.assertIn("B/B'", texts)
        self.assertIn("A/A'", texts)
        self.assertEqual(len(page.placed), 1)
        key = page.placed[0][0]
        self.assertEqual(len(page.sym[key].terminals), 1)

    def test_table_centers_two_line_signal_in_its_cell(self):
        page = g.Page({})
        rows = [{'pin': 'B1', 'signal': 'I+/\nCHK+', 'description': '電流入力'}]
        columns, cells = communication.pin_table_layout(rows, 190)
        communication.draw_pin_table(page, 100, 200, columns, cells)
        data_top = 222
        row_center = data_top + cells[1][1] / 2
        signal_center = 100 + columns[0] + columns[1] / 2
        signal = [t for t in page.texts if t.get('text') in ('I+/', 'CHK+')]
        self.assertEqual(len(signal), 2)
        for text in signal:
            actual_center = float(text.get('x')) + g.TEXT_MARGIN + g.text_w(text.get('text'), 8) / 2
            self.assertAlmostEqual(actual_center, signal_center, delta=0.1)
        text_center = sum(float(t.get('y')) for t in signal) / 2 + g.TEXT_MARGIN + 8 * g.PX_PER_PT / 2
        self.assertAlmostEqual(text_center, row_center, delta=0.1)

    def test_known_connector_pin_tables_fit_right_half(self):
        definitions = [g.IQR_COMM['RJ71GB91'], g.IQR_COMM['RJ71PB91V'],
                       dict(g.GOT_OPTION['GT15-RS2-9P'], panel_compact=True),
                       dict(g.GOT_OPTION['GT15-RS4-9S'], panel_compact=True)]
        for spec in definitions:
            with self.subTest(spec=spec['interfaces'][0]['name']):
                page = self.panel(spec)
                if spec['interfaces'][0]['kind'] == 'gpib':
                    self.assertIn('Logic GND', [t.get('text') for t in page.texts])
                frame = next(s for s in page.shapes if s.get('type') == 'Rectangle' and s.get('y1') == '52')
                bottom = float(frame.get('y2'))
                self.assertLessEqual(bottom, page.communication_footer_top - 8)
                for shape in page.shapes:
                    self.assertGreaterEqual(float(shape.get('x1')), 895)
                    self.assertLessEqual(float(shape.get('x2')), 1205)
                for text in page.texts:
                    if float(text.get('y')) >= page.communication_footer_top:
                        continue
                    self.assertGreaterEqual(float(text.get('x')), 895)
                    self.assertLess(float(text.get('y')) + 8 * g.PX_PER_PT + 8, bottom + 0.1)

    def test_compact_two_ports_keep_distinct_tables_and_connections(self):
        spec = copy.deepcopy(g.GOT_OPTION['GT15-RS4-9S'])
        spec['interfaces'] *= 2
        spec['interfaces'] = [dict(item, name='CH' + str(i + 1)) for i, item in enumerate(spec['interfaces'])]
        spec['panel_compact'] = True
        spec['diagram_notes'] = ['注意事項' * 35]
        page = self.panel(spec)
        self.assertEqual([t.get('text') for t in page.texts].count('ピンNo.'), 2)
        self.assertEqual(len(page.placed), 2)
        frame = next(s for s in page.shapes if s.get('type') == 'Rectangle' and s.get('y1') == '52')
        self.assertLessEqual(float(frame.get('y2')), page.communication_footer_top - 8)
        tables = [s for s in page.shapes if s.get('type') == 'Rectangle' and s is not frame]
        self.assertLess(float(tables[0].get('y2')), float(tables[1].get('y1')))

    def test_many_pins_and_long_footer_keep_readable_text_clear(self):
        spec = copy.deepcopy(g.IQR_COMM['RJ71GB91'])
        spec['diagram_notes'] = ['注意事項' * 55]
        page = self.panel(spec)
        frame = next(s for s in page.shapes if s.get('type') == 'Rectangle' and s.get('y1') == '52')
        self.assertLessEqual(float(frame.get('y2')), page.communication_footer_top - 8)
        self.assertIn('24', [t.get('text') for t in page.texts])
        self.assertTrue(all(float(t.get('font').split(',')[1]) >= 7 for t in page.texts))

    def test_missing_pin_information_does_not_invent_table_or_pins(self):
        spec = {'network': 'Ethernet', 'interfaces': [{'name': 'LAN', 'kind': 'rj45'}]}
        page = self.panel(spec)
        self.assertNotIn('ピンNo.', [t.get('text') for t in page.texts])
        self.assertIn('RJ-45', [t.get('text') for t in page.texts])
        self.assertEqual(len(page.placed), 1)
        self.assertEqual(page.placed[0][3], 84 + 59)


if __name__ == '__main__':
    unittest.main()
