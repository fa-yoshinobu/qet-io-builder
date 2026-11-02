import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET
import gen_io_page as gen


def info(element, name):
    return next((x.text for x in element.findall('./elementInformations/elementInformation') if x.get('name') == name), '')


class ManualRenderingTest(unittest.TestCase):
    def assert_round_terminal_attachment(self, symbol, name, frame_edge):
        _, orient, tx, ty = symbol.terminals[name]
        circles = [a for tag, a in symbol.parts if tag == 'circle' and a['diameter'] == 8
                   and a['y'] + 4 == ty and (a['x'] if orient == 'w' else a['x'] + 8) == frame_edge]
        self.assertEqual(len(circles), 1, name)
        self.assertEqual(tx,frame_edge,name)
        self.assertFalse(any(tag=='line' and a['y1']==a['y2']==ty and
                             (min(a['x1'],a['x2'])<frame_edge if orient=='w' else max(a['x1'],a['x2'])>frame_edge)
                             for tag,a in symbol.parts),name)

    def test_fx5_round_terminals_touch_frame_without_crossing(self):
        for board in (None, gen.FX5_BOARDS['FX5-3A-BD'], gen.FX5_BOARDS['FX5-485-BD']):
            symbol = gen.fx5_body_symbol('check', True, True, True, True, service_pairs=2, board_spec=board)
            for name in symbol.terminals:
                if name == 'RJ-45':
                    continue
                self.assert_round_terminal_attachment(symbol, name, 330 if name.startswith('board:') else -20)
            pin_labels = [a for tag, a in symbol.parts if tag == 'text' and a['text'] in ('L', 'N', 'RDA', 'V1+')]
            self.assertTrue(all(a['x'] == -6 or a['x'] + gen.text_w(a['text'], 8) == 316 for a in pin_labels))

    def test_iqr_q_power_and_shared_module_pin_use_same_clearance(self):
        for supply in ('AC', 'DC'):
            for service in (False, True):
                symbol = gen.iqr_power_symbol('check', supply, service)
                for name in symbol.terminals:
                    self.assert_round_terminal_attachment(symbol, name, -10)
                labels = [a for tag, a in symbol.parts if tag == 'text']
                self.assertTrue(all(a['x'] == 4 for a in labels))
        root = self.generate([{'kind': 'qcomm', 'left_model': 'QJ71C24N-R4'},
                              {'kind': 'iqrcomm', 'left_model': 'RJ61BT11'}])
        pins = [e for e in root.findall('./diagram/elements/element') if e.get('type').endswith('/module_pin.elmt')]
        self.assertTrue(pins)
        self.assertTrue(all(float(t.get('x')) == 14 for e in pins for t in e.findall('./dynamic_texts/dynamic_elmt_text')
                            if t.findtext('info_name') == 'label'))

    def test_dual_io_rounds_are_inside_rows_and_internal_links_stay_outside(self):
        pg = {'kind': 'fx5u', 'model': 'FX5UC-32MR/DS-TS'}
        for direction in ('in', 'out'):
            page = gen.Page(gen.build_symbols())
            symbol = page.sym[gen.fx_signal_symbol(page, pg, direction)]
            circles = [a for tag, a in symbol.parts if tag == 'circle']
            self.assertEqual(len(circles), 2)
            edge = 4 if direction == 'in' else -4
            self.assertTrue(all((a['x'] if direction == 'in' else a['x'] + 6) == edge for a in circles))
            for circle in circles:
                cy, cx = circle['y'] + 3, circle['x'] + 3
                for tag, a in symbol.parts:
                    if tag == 'line' and a['y1'] == a['y2'] == cy:
                        self.assertFalse(min(a['x1'], a['x2']) < cx < max(a['x1'], a['x2']))

    def generate(self, pages):
        cfg = json.loads((Path(__file__).parent / 'fixtures/project.json').read_text(encoding='utf-8'))
        cfg['pages'] = pages
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p/'p.json').write_text(json.dumps(cfg, ensure_ascii=False), encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()):
                gen.main(str(p/'p.json'), str(p/'p.qet'))
            return ET.parse(p/'p.qet').getroot()

    def test_uc_physical_contacts_and_independent_input_common_names(self):
        cfg = json.loads((Path(__file__).parent / 'fixtures/project.json').read_text(encoding='utf-8'))
        pg = {'kind': 'fx5u', 'model': 'FX5UC-32MR/DS-TS'}
        spec = gen.fx_spec(pg)
        rows = lambda addresses: [dict(アドレス=a, 機器番号='', 信号名='') for a in addresses]
        pages = gen.build_fx5u_pages(pg, cfg, gen.build_symbols(), rows(spec['inputs']), rows([a for _, aa in spec['groups'] for a in aa]))
        placed = [x for _, page in pages for x in page.placed]
        for name in ['S/S0', 'S/S1', 'COM0', 'COM1']:
            self.assertEqual(sum(info(e, 'label') == name for _, e, _, _ in placed), 2)
            self.assertTrue(all(info(e, 'comment') == 'コモン' for _, e, _, _ in placed if info(e, 'label') == name))
        signals = [(k, e) for k, e, _, _ in placed if k.endswith('_dual')]
        self.assertEqual(len(signals), 32)
        self.assertTrue(all(len(e.findall('./terminals/terminal')) == 2 for _, e in signals))
        self.assertLessEqual(max(y for k, _, _, y in placed if k.startswith(('fx_in', 'fx_out'))), gen.FX_YMAX)

    def test_q_two_slot_reserves_next_slot_without_double_counting(self):
        pg = {'kind': 'qbody', 'model': 'Q03UDVCPU', 'power_model': 'Q61P', 'base_model': 'Q35B',
              'modules': ['QJ71GP21S-SX', '', 'QX40']}
        root = self.generate([pg])
        texts = [x.get('text') for x in root.findall('.//diagram/inputs/input')]
        self.assertIn('外部供給電源', texts)
        self.assertIn('X030〜', texts)
        self.assertIn('X03F', texts)
        pg['modules'] = ['QJ71GP21S-SX', 'QX40']
        with self.assertRaises(SystemExit):
            self.generate([pg])

    def test_compensation_and_shield_pins_remain_connectable(self):
        root = self.generate([{'kind': 'qanalog', 'model': 'Q64DAH'}, {'kind': 'iqranalog', 'model': 'R60TD8-G'}])
        diagrams = root.findall('./diagram')
        e = diagrams[0].findall('./elements/element')
        self.assertEqual({info(x, 'auxiliary1') for x in e if info(x, 'label') == 'SLD'}, {'4', '8', '12'})
        e = diagrams[1].findall('./elements/element')
        self.assertTrue(any(info(x, 'auxiliary1') == 'B19' and info(x, 'label') == 'RTD+' for x in e))

    def test_comm_physical_number_and_no_sd_slot(self):
        root = self.generate([{'kind': 'iqrcomm', 'left_model': 'RJ61BT11'},
                              {'kind': 'iqrbody', 'model': 'R00CPU', 'power_model': 'R61P', 'base_model': 'R35B', 'modules': []}])
        labels = [info(x, 'label') for x in root.findall('./diagram/elements/element')]
        self.assertIn('3  DA', labels)
        self.assertIn('4  SLD', labels)
        texts = [x.get('text') for x in root.findall('.//diagram/inputs/input')]
        self.assertIn('搭載不可', texts)
