import unittest
import gen_io_page as gen
from renderers import remote


class RemoteRenderingTest(unittest.TestCase):
    def test_body_header_and_notes_do_not_interrupt_power_rows(self):
        model='NZ2GF12A2-16T'
        spec=gen.remote_spec(model)
        page=remote.build_body({'model':model,'tag':'RIO1','unit_no':'5'},gen.build_symbols(),spec,
                               gen.Page,gen.Symbol,gen.page_heading)
        texts=[t.get('text','') for t in page.texts]
        for value in ('ユニットNo. 5','RIO1',model):
            self.assertIn(value,texts)
        self.assertFalse(any(text.endswith('通信・電源') for text in texts))
        footer=page.communication_footer_top
        self.assertLess(max(y for _,_,_,y in page.placed)+25,footer-8)
        boxes=[s for s in page.shapes if s.get('type')=='Rectangle' and float(s.get('y1'))==52]
        self.assertTrue(boxes)
        self.assertTrue(all(float(s.get('y2'))<=footer-8 for s in boxes))

    def test_factory_cold_junction_parts_are_visible_without_wiring_ports(self):
        page = gen.build_fx_analog_page({'kind':'remoteanalog','model':'NZ2GF2B-60TCTT4'}, {}, gen.build_symbols(), [])
        parts = [e for key,e,_,_ in page.placed if key == 'plc_in_readonly'
                 and e.findtext("./elementInformations/elementInformation[@name='label']") != 'NC']
        self.assertEqual(len(parts), 2)
        self.assertTrue(all(not e.findall('./terminals/terminal') for e in parts))
        titles = [e.get('text','') for e in page.texts]
        self.assertEqual(titles.count('NZ2GF2B-60TCTT4'), 2)
        comments=[n.text or '' for _,e,_,_ in page.placed for n in e.findall("./elementInformations/elementInformation[@name='comment']")]
        for name in ('制御OUT1','制御OUT4'):
            self.assertTrue(any(name in text for text in comments))
        self.assertFalse(any('CH5' in text or 'CH8' in text for text in titles))

    def test_connector_icon_does_not_overlap_first_terminal_row(self):
        symbols = gen.build_symbols()
        spec = {'io_connectors':[{'name':'CON1','connector_type':'m12_a_5','pins':[['1','+24V'],['2','X1'],['3','24G'],['4','X0'],['5','FG']]}]}
        page = gen.remote_connector_pages({'model':'TEST'}, symbols, spec)[0][1]
        _, symbol, _, icon_y = next((key,symbols[key],x,y) for key,_,x,y in page.placed if key.endswith('_small'))
        bottom = max(float(attrs['y']) + float(attrs['diameter']) for tag,attrs in symbol.parts if tag == 'circle') + icon_y
        first_pin = min(y for key,_,_,y in page.placed if key == 'module_pin')
        self.assertLess(bottom, first_pin - 7)
        # ピンを端子として並べるので、コネクタの絵には端子を付けない(接続点を二重にしない)
        self.assertEqual(len(symbol.terminals), 0)

    def test_three_pole_power_symbol_has_three_contact_holes(self):
        symbols = gen.build_symbols()
        key = remote.connector_symbol(symbols, gen.Symbol, 'terminal_3')
        # ねじ端子は丸(ねじ頭)で描く(共通部品 renderers/connectors.py)
        screws = [attrs for tag,attrs in symbols[key].parts if tag == 'circle']
        self.assertEqual(len(screws), 3)
