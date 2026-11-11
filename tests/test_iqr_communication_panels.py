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
                notes=[line for note in spec['diagram_notes'] for line in communication.wrap(note,1176,8)]
                for note in notes:
                    text=next(t for t in page.texts if t.get('text')==note)
                    self.assertGreaterEqual(float(text.get('y')),768)
                    self.assertEqual(float(text.get('x')),30)
                self.assertEqual(page.communication_footer_top,768)
                self.assertEqual([t.get('text') for t in page.texts].count('※接続先・配線方式はQETで記入'),1)

    def test_footer_notes_merge_panels_without_duplicate_text_and_keep_guide_last(self):
        page=g.Page(g.build_symbols())
        note='注意書き'*30
        expected=communication.wrap(note,1176,8)
        guide='※接続先・配線方式はQETで記入'
        communication.draw_notes(page,275,g.UNIT_BOX_W,[guide,note])
        old=list(page.texts)
        top=communication.draw_notes(page,895,g.UNIT_BOX_W,[note,'右機器の注意',guide])
        expected += ['右機器の注意',guide]
        self.assertEqual([t.get('text') for t in page.texts],expected)
        self.assertFalse(set(map(id,old)) & set(map(id,page.texts)))
        self.assertEqual(float(page.texts[-1].get('y')),800)
        self.assertEqual(top,800-(len(expected)-1)*16)
        self.assertTrue(all(float(t.get('x'))==30 for t in page.texts))

    def test_cable_footer_reserves_connection_rows_and_lane_extension_stops_above_notes(self):
        page=g.Page(g.build_symbols())
        page.place('junction',45,200)
        page.extend_lanes([45],bottom=812)
        communication.draw_notes(page,30,1200,['機器固有の注意'],bottom=748)
        communication.draw_notes(page,895,310,['追加注意'])
        page.finish()
        self.assertEqual(page.communication_footer_top,732)
        self.assertEqual(max(float(t.get('y')) for t in page.texts),748)
        self.assertEqual(max(y for _,_,_,y in page.placed),716)
        self.assertEqual(float(page.elements[-1].get('y')),716)

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
