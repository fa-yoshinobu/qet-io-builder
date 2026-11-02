"""コネクタの絵の共通部品(renderers/connectors.py)。"""
import tempfile
import unittest
from pathlib import Path

import gen_io_page as g
from renderers import connectors, communication, remote


class ConnectorPartsTest(unittest.TestCase):
    def test_right_side_connector_keeps_front_view_and_connects_from_right_edge(self):
        for kind in ('rj45', 'usb_minib', 'usb_c', 'usb_a', 'hdmi'):
            with self.subTest(kind=kind):
                symbols = {}
                key = connectors.symbol(symbols, g.Symbol, kind, terminal_side='right')
                symbol = symbols[key]
                _, orientation, x, y = next(iter(symbol.terminals.values()))
                self.assertEqual((orientation, x, y), ('e', 0, 0))
                expected = g.Symbol('expected', '', 100, 60, 0, 30)
                connectors.draw(expected, kind, -connectors.width(kind), 0)
                self.assertEqual(symbol.parts, expected.parts)

    def test_cable_terminal_is_on_connector_edge_without_an_external_stub(self):
        for kind in connectors.CONNECTORS:
            if kind=='sd':
                continue
            for center in (False,True):
                with self.subTest(kind=kind,center=center):
                    symbols={}
                    key=connectors.symbol(symbols,g.Symbol,kind,center=center)
                    symbol=symbols[key]
                    edge=-connectors.width(kind)/2 if center else 5
                    self.assertEqual(next(iter(symbol.terminals.values()))[2:],(edge,0))
                    self.assertFalse(any(tag=='line' and min(float(a['x1']),float(a['x2']))<edge
                                         for tag,a in symbol.parts))

    def test_every_kind_builds_with_one_cable_terminal(self):
        for kind in connectors.CONNECTORS:
            with self.subTest(kind=kind):
                symbols = {}
                key = connectors.symbol(symbols, g.Symbol, kind)
                self.assertEqual(len(symbols[key].terminals), 0 if kind == 'sd' else 1)
                # 高さは 48 以内(D-sub など基準の大きさ 40 に合わせる)
                ys = [float(a[k]) for t, a in symbols[key].parts if t != 'text' for k in ('y', 'y1', 'y2') if k in a]
                self.assertLessEqual(max(ys) - min(ys), 48)

    def test_gender_changes_pin_fill_only(self):
        male, female = {}, {}
        km = connectors.symbol(male, g.Symbol, 'dsub9', 'male')
        kf = connectors.symbol(female, g.Symbol, 'dsub9', 'female')
        fill = lambda s: sum('filling:black' in a['style'] for t, a in s.parts if t == 'circle')
        self.assertEqual(fill(male[km]) - fill(female[kf]), 9)

    def test_all_pages_share_the_same_drawing(self):
        # PLC 側の D-sub 9 と通信・GOT 側の D-sub 9 は同じ絵
        symbols = g.build_symbols()
        comm = communication.connector({}, 'dsub15', g.Symbol)
        self.assertEqual(comm, 'comm_dsub15')
        self.assertEqual(communication.connector(symbols, 'dsub9', g.Symbol), 'module_dsub_f')
        gen_parts = [t for t, _ in symbols['module_dsub_f'].parts]
        common = {}
        key = connectors.symbol(common, g.Symbol, 'dsub9', 'female')
        self.assertEqual(gen_parts, [t for t, _ in common[key].parts])
        # USB Mini-B は1種類(通信・GOT 側の 'usb' も同じ絵)
        a, b = {}, {}
        self.assertEqual(communication.connector(a, 'usb', g.Symbol), communication.connector(b, 'usb_mini_b', g.Symbol))
        # 端子台40極と FCN40極は別の絵
        c = {}
        t40 = remote.connector_symbol(c, g.Symbol, 'terminal_40')
        f40 = remote.connector_symbol(c, g.Symbol, 'fcn_40')
        self.assertNotEqual([t for t, _ in c[t40].parts], [t for t, _ in c[f40].parts])

    def test_size_and_hotspot_are_integers(self):
        # QET は大きさ・基準点が整数でない部品を読み込まない(「読み込まれなかった要素」になる)
        for kind in list(connectors.CONNECTORS) + ['terminal_34', 'mil_20']:
            for center in (False, True):
                with self.subTest(kind=kind, center=center):
                    symbols = {}
                    key = connectors.symbol(symbols, g.Symbol, kind, center=center, wired=False)
                    d = symbols[key].to_xml().find('definition')
                    for attr in ('width', 'height', 'hotspot_x', 'hotspot_y'):
                        self.assertRegex(d.get(attr), r'^-?\d+$')

    def test_export_writes_qet_elements(self):
        import tools.export_connector_elements as export
        with tempfile.TemporaryDirectory() as folder:
            paths = export.export(Path(folder))
            self.assertIn('conn_rj45.elmt', {p.name for p in paths})
            self.assertIn('conn_dsub9_male.elmt', {p.name for p in paths})
            self.assertTrue(all(p.read_text(encoding='utf-8').startswith('<?xml') for p in paths))


if __name__ == '__main__':
    unittest.main()
