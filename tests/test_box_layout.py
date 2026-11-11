import unittest

import gen_io_page as g
from renderers.box_layout import PowerRails, finish_box, single_units


class BoxLayoutTest(unittest.TestCase):
    def test_only_connected_power_poles_are_drawn(self):
        page = g.Page(g.build_symbols())
        records = [(None, {'lane': 'P'}), (None, {'lane': 'N'})]
        rails = PowerRails(page, records)
        self.assertFalse(page.placed)
        target = page.place('module_pin', 275, 140)
        rails.connect(records[0][1], target)
        rails.finish(300)
        self.assertEqual(set(rails), {('main', 'P')})
        labels = [text.get('text') for text in page.texts]
        self.assertIn('P24', labels)
        self.assertNotIn('N24', labels)
        self.assertFalse(any(x == g.FX_IN_X['inner'] for _, _, x, _ in page.placed))

    def test_settings_align_with_box_below_right_connections(self):
        symbols = g.build_symbols()
        pin = g.Symbol('test_right', '', 10, 10, 0, 0)
        pin.terminal('t', 'e', 0, 0)
        symbols[pin.name] = pin
        page = g.Page(symbols)
        page.place(pin.name, 585, 200)
        bottom = finish_box(page, 275, 585, 220, [('IP設定', 'ip')], {'ip': '192.168.1.1'})
        frame, field = page.shapes
        self.assertEqual(float(frame.get('y2')), float(field.get('y2')))
        self.assertEqual(bottom, float(field.get('y2')))
        self.assertGreater(float(field.get('x1')), 585)
        self.assertGreaterEqual(float(field.get('y1')), 216)

    def test_split_keeps_each_unit_values_and_visibility(self):
        pg = {'kind': 'iqrcomm', 'left_model': 'RJ71EN71', 'left_tag': 'NET1',
              'right_model': 'RJ71EN71', 'right_tag': 'NET2',
              'left_ip': '192.168.1.1', 'right_ip': '192.168.1.2',
              'settings_visibility': {'left_ip': True, 'right_ip': False}}
        left, right = single_units(pg)
        self.assertEqual(right['left_tag'], 'NET2')
        self.assertEqual(right['left_ip'], '192.168.1.2')
        self.assertFalse(right['settings_visibility']['left_ip'])
        self.assertTrue(left['settings_visibility']['left_ip'])
        project, _ = g.build_project({'front_pages': False}, [(pg, None)])
        pages = project.findall('diagram')
        self.assertEqual(len(pages), 2)
        texts = [[item.get('text', '') for item in page.findall('./inputs/input')] for page in pages]
        self.assertIn('NET1', texts[0])
        self.assertIn('NET2', texts[1])
        self.assertIn('192.168.1.1', texts[0])
        self.assertNotIn('192.168.1.2', texts[1])
        self.assertEqual(pg['right_tag'], 'NET2')

    def test_rack_references_point_to_each_split_communication_page(self):
        rack = {'kind': 'iqrbody', 'model': 'R04CPU', 'power_model': 'R61P', 'base_model': 'R35B',
                'modules': ['RJ71EN71', 'RJ71EN71'], 'module_tags': ['NET1', 'NET2']}
        communication = {'kind': 'iqrcomm', 'left_model': 'RJ71EN71', 'left_tag': 'NET1',
                         'right_model': 'RJ71EN71', 'right_tag': 'NET2'}
        project, _ = g.build_project({'front_pages': False}, [(rack, None), (communication, None)])
        pages = project.findall('diagram')
        references = [item for item in pages[0].findall('./inputs/input') if item.get('text', '').startswith('→ ')]
        references.sort(key=lambda item: float(item.get('x')))
        self.assertEqual([item.get('text') for item in references], ['→ 2頁', '→ 3頁'])
        self.assertIn('NET1', [item.get('text') for item in pages[1].findall('./inputs/input')])
        self.assertIn('NET2', [item.get('text') for item in pages[2].findall('./inputs/input')])


if __name__ == '__main__':
    unittest.main()
