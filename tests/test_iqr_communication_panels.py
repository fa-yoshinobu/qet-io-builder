import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

import gen_io_page as g
import gui_core as gui
from renderers import communication


class CommunicationPanelsTest(unittest.TestCase):
    def test_unconnected_terminal_and_connector_pin_rows_are_readonly(self):
        terminal=g.IQR_COMM['RJ71CN91']['interfaces'][0]
        rows=communication.interface_rows(terminal)
        self.assertEqual(rows[0]['signal'],'NC')
        self.assertFalse(rows[0]['connectable'])
        symbols=g.build_symbols();page=g.Page(symbols)
        communication.draw_panel(page,symbols,g.IQR_COMM['RJ71CN91'],275,g.Symbol,{},'left')
        pins=[e for key,e,_,_ in page.placed if key=='module_pin']
        self.assertEqual(len(pins),len(terminal['ports']))
        self.assertIn('NC',[t.get('text') for t in page.texts])
        connector=g.IQR_COMM['RJ71PB91V']['interfaces'][0]
        rows=communication.interface_rows(connector)
        self.assertEqual([row['pin'] for row in rows],[str(i) for i in range(1,10)])
        self.assertEqual([row['pin'] for row in rows if not row['connectable']],['1','2','4','7','9'])
        symbols=g.build_symbols();page=g.Page(symbols)
        communication.draw_panel(page,symbols,g.IQR_COMM['RJ71PB91V'],275,g.Symbol,{},'left')
        self.assertFalse(any(key=='module_pin' for key,_,_,_ in page.placed))
        self.assertIn('ピンNo.', [t.get('text') for t in page.texts])
        nc_rows={t.get('y') for t in page.texts if t.get('text')=='NC'}
        for pin in ('1','2','4','7','9'):
            text=next(t for t in page.texts if t.get('text')==pin)
            self.assertGreaterEqual(float(text.get('x')),275+communication.connector_label_x('dsub9'))
            self.assertIn(text.get('y'), nc_rows)

    def test_function_is_first_inside_box_and_notes_are_footer_texts(self):
        for side,x in (('left',275),('right',895)):
            with self.subTest(side=side):
                symbols=g.build_symbols()
                page=g.Page(symbols)
                spec=g.IQR_COMM['RD81OPC96']
                right=communication.draw_panel(page,symbols,spec,x,g.Symbol,{},side)
                self.assertEqual(right,x+g.UNIT_BOX_W)
                function=[t for t in page.texts if t.get('text')==spec['network']]
                self.assertEqual(len(function),1)
                self.assertEqual(float(function[0].get('y')),60)
                self.assertGreater(min(y for _,_,_,y in page.placed),84)
                notes=[line for note in spec['diagram_notes'] for line in communication.wrap(note,g.UNIT_BOX_W-24,8)]
                for note in notes:
                    text=next(t for t in page.texts if t.get('text')==note)
                    self.assertGreaterEqual(float(text.get('y')),768)
                    self.assertEqual(float(text.get('x')),x+12)
                self.assertEqual(page.communication_footer_top,768)
                self.assertEqual([t.get('text') for t in page.texts].count('※接続先・配線方式はQETで記入'),1)

    def test_footer_notes_deduplicate_wrap_and_keep_each_panel_column(self):
        page=g.Page(g.build_symbols())
        note='注意書き'*30
        expected=communication.wrap(note,g.UNIT_BOX_W-24,8)
        top=communication.draw_notes(page,895,g.UNIT_BOX_W,[note,note])
        self.assertEqual([t.get('text') for t in page.texts],expected)
        self.assertEqual(float(page.texts[-1].get('y')),800)
        self.assertEqual(top,800-(len(expected)-1)*16)
        self.assertTrue(all(float(t.get('x'))==907 for t in page.texts))

    def test_long_function_wraps_before_interfaces(self):
        symbols=g.build_symbols(); page=g.Page(symbols)
        spec={'network':'機能名'*15,'interfaces':[{'name':'LAN','kind':'rj45'}]}
        communication.draw_panel(page,symbols,spec,275,g.Symbol,{},'left')
        lines=communication.wrap(spec['network'],g.UNIT_BOX_W-24,9)
        self.assertGreater(len(lines),1)
        function_bottom=52+max(32,12+len(lines)*14)
        self.assertGreater(min(y for _,_,_,y in page.placed),function_bottom)
        self.assertTrue(all(communication.text_width(line,9)<=g.UNIT_BOX_W-24 for line in lines))

    def test_interface_does_not_repeat_the_function_name(self):
        for model,spec in g.IQR_COMM.items():
            if not spec.get('panel_interfaces'):
                continue
            with self.subTest(model=model):
                symbols=g.build_symbols(); page=g.Page(symbols)
                communication.draw_panel(page,symbols,spec,275,g.Symbol,{},'left')
                self.assertEqual([t.get('text') for t in page.texts].count(spec['network']),1)

    def test_head_occupies_cpu_position_and_not_io_slot(self):
        head = 'RJ72GF15-T2'
        self.assertIn(head, gui.part_catalog('model', 'iqrbody')['mitsubishi']['iq_r'])
        self.assertNotIn(head, gui.part_catalog('modules', 'iqrbody')['mitsubishi']['iq_r'])
        page = {'kind': 'iqrbody', 'model': head, 'power_model': 'R61P', 'base_model': 'R35B', 'modules': ['RX40C7']}
        with tempfile.TemporaryDirectory() as tmp:
            source, target = Path(tmp) / 'project.json', Path(tmp) / 'head.qet'
            source.write_text(json.dumps({**json.loads(Path('tests/fixtures/project.json').read_text(encoding='utf-8')), 'pages': [page]}), encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()):
                g.main(str(source), str(target))
            self.assertEqual(len(ET.parse(target).findall('diagram')), 1)
            page['model'] = 'R04CPU'; page['modules'] = [head]
            source.write_text(json.dumps({**json.loads(Path('tests/fixtures/project.json').read_text(encoding='utf-8')), 'pages': [page]}), encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
                g.main(str(source), str(target))

    def test_settings_stay_within_panel_and_sd_has_no_connection(self):
        for model in ('RJ71GN11-EIP', 'RD81MES96N', 'RJ72GF15-T2'):
            with self.subTest(model=model):
                symbols = g.build_symbols()
                p = g.build_q_comm_page({'kind': 'iqrcomm', 'left_model': model, 'left_ip': '192.168.1.2', 'settings_visibility': {'left_ip': True}}, symbols)
                texts = [e.get('text', '') for e in p.texts]
                self.assertIn('192.168.1.2', texts)
                self.assertTrue(all(y < 800 for _, _, _, y in p.placed))
                if 'comm_sd' in symbols:
                    self.assertEqual(symbols['comm_sd'].terminals, {})


if __name__ == '__main__':
    unittest.main()
