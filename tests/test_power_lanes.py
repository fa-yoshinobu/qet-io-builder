import unittest

import gen_io_page as g
from renderers import fx5


class PowerLaneTest(unittest.TestCase):
    def test_only_registered_unused_lanes_are_removed(self):
        page = g.Page(g.build_symbols())
        page.text(100, 100, 'P24')  # 通常の文字・配線は削除対象にしない。
        page.power_lane_label(45, 'P24')
        page.place('junction', 45, g.LANE_TOP_Y)
        page.place('junction', 72, g.LANE_TOP_Y)
        terminal = page.place('module_pin', 275, 140)
        page.extend_lanes([45, 72])
        page.finish()
        self.assertEqual([t.get('text') for t in page.texts], ['P24'])
        self.assertFalse(any(x == 45 for _, _, x, _ in page.placed))
        self.assertEqual(sum(x == 72 for _, _, x, _ in page.placed), 2)
        self.assertIn(terminal[0], [e.get('uuid') for e in page.elements])
        self.assertEqual(len(page.conductors), 1)

    def test_connected_lane_keeps_terminal_and_all_wires(self):
        page = g.Page(g.build_symbols())
        page.power_lane_label(45, 'P12')
        top = page.place('junction', 45, g.LANE_TOP_Y)
        middle = page.place('junction', 45, 140)
        terminal = page.place('module_pin', 275, 140)
        page.wire(top, 's', middle, 'n')
        page.wire(middle, 'e', terminal, 't', num='P12', show=True)
        page.extend_lanes([45])
        elements = [e.get('uuid') for e in page.elements]
        endpoints = [(w.get('element1'), w.get('element2')) for w in page.conductors]
        page.finish()
        self.assertEqual([e.get('uuid') for e in page.elements], elements)
        self.assertEqual([(w.get('element1'), w.get('element2')) for w in page.conductors], endpoints)
        self.assertEqual([t.get('text') for t in page.texts], ['P12'])

    def test_blank_lane_label_does_not_capture_another_text(self):
        for previous in (False, True):
            with self.subTest(previous=previous):
                page = g.Page(g.build_symbols())
                if previous:
                    page.text(100, 100, '残す見出し')
                page.power_lane_label(45, '')
                page.place('junction', 45, g.LANE_TOP_Y)
                page.extend_lanes([45])
                page.finish()
                self.assertEqual([t.get('text') for t in page.texts], ['残す見出し'] if previous else [])
                self.assertFalse(page.elements)

    def test_source_input_without_repeated_ss_keeps_only_signal_supply(self):
        # source選択・S/S省略という非既定条件でも極の意味を取り違えない。
        for show_ss in (False, True):
            with self.subTest(show_ss=show_ss):
                page = g.Page(g.build_symbols())
                rows = [{'アドレス': 'X0', '機器番号': '', '信号名': ''}]
                fx5.fx_input_half(page, 0, rows, {'kind': 'fx5cpu', 'model': 'FX5U-32MR/ES'},
                                  {'power': {}}, show_ss, 'source')
                page.finish()
                labels = [t.get('text') for t in page.texts]
                self.assertIn('P24', labels)
                self.assertEqual('N24' in labels, show_ss)
                self.assertTrue(any(e.findtext("./elementInformations/elementInformation[@name='label']") == 'X0'
                                    for e in page.elements))

    def test_rack_keeps_power_terminals_without_empty_rails(self):
        pg = {'kind': 'iqrbody', 'model': 'R04CPU', 'power_model': 'R62P', 'base_model': 'R35B',
              'modules': [], 'extensions': [{'base_model': 'R65B', 'power_model': 'R61P', 'modules': []}]}
        project, _ = g.build_project({'front_pages': False}, [(pg, None)])
        pages = project.findall('diagram')
        labels = [t.get('text') for d in pages for t in d.findall('./inputs/input')]
        self.assertNotIn('P24', labels)
        self.assertNotIn('N24', labels)
        powers = [e for d in pages for e in d.findall('./elements/element')
                  if e.findtext("./elementInformations/elementInformation[@name='label']") in ('R62P', 'R61P')]
        self.assertEqual(len(powers), 2)
        self.assertTrue(all(e.findall('./terminals/terminal') for e in powers))


if __name__ == '__main__':
    unittest.main()
