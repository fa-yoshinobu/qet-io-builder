import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

import gen_io_page as g
import gui
from renderers import hmi


class GotGenerationTest(unittest.TestCase):
    def test_accessories_are_right_aligned_with_names_on_left(self):
        model = 'GT3708-XRBD'
        page = hmi.build_body({'model': model}, g.build_symbols(), g.GOT_BODY[model], g.Page, g.Symbol, g.page_heading)
        accessories = [item for item in page.placed if item[0].endswith('_right')]
        self.assertEqual(len(accessories), 3)
        for key, _, x, _ in accessories:
            self.assertEqual(x, 765)
            self.assertEqual(next(iter(page.sym[key].terminals.values()))[1], 'e')
        for item in g.GOT_BODY[model]['interfaces']:
            if item['kind'].startswith('usb') or item['kind'] == 'hdmi':
                label = next(t for t in page.texts if t.get('text') == item.get('connector_label', item['kind']))
                self.assertEqual(float(label.get('x')), 537)
        ethernet = [item for item in page.placed if 'rj45' in item[0]]
        self.assertTrue(all(item[2] == 275 for item in ethernet))

    def test_ethernet_connectors_clear_dividers_and_bottom_border(self):
        for model,spec in g.GOT_BODY.items():
            with self.subTest(model=model):
                page=hmi.build_body({'model':model},g.build_symbols(),spec,g.Page,g.Symbol,g.page_heading)
                dividers=[float(s.get('y1')) for s in page.shapes
                          if s.get('type')=='Line' and s.get('x1')=='285' and s.get('x2')=='515'
                          and s.get('y1')==s.get('y2')]
                frame=next(s for s in page.shapes if s.get('type')=='Rectangle' and s.get('y1')=='52')
                bottom=float(frame.get('y2'))
                self.assertLess(bottom,page.communication_footer_top-8)
                for key,_,x,y in page.placed:
                    if x!=275 or 'rj45' not in key:
                        continue
                    symbol=page.sym[key]
                    outline=next(a for tag,a in symbol.parts if tag=='rect' and float(a.get('height',0))==40)
                    top=y+float(outline['y']);end=top+40
                    self.assertTrue(all(not top<=line<=end for line in dividers))
                    after=[line for line in dividers if line>end]
                    self.assertGreaterEqual(min(after+[bottom])-end,10)

    def test_body_and_options_have_individual_unit_headers_and_footer_notes(self):
        page=hmi.build_body({'model':'GT2715-XTBD','tag':'HMI1','unit_no':'2'},g.build_symbols(),
                            g.GOT_BODY['GT2715-XTBD'],g.Page,g.Symbol,g.page_heading)
        texts=[t.get('text','') for t in page.texts]
        for value in ('ユニットNo. 2','HMI1','GT2715-XTBD'):
            self.assertIn(value,texts)
        note=next(t for t in page.texts if t.get('text')=='※コネクタはケーブル単位。接続先・結線は手動で記入')
        self.assertGreaterEqual(float(note.get('y')),page.communication_footer_top)
        self.assertGreater(float(note.get('x')),325)
        page=hmi.build_options({'left_model':'GT15-RS4-TE','left_tag':'UNIT1','left_unit_no':'3',
                                'right_model':'GT15-RS2-9P','right_tag':'UNIT2','right_unit_no':'4'},
                               g.build_symbols(),g.GOT_OPTION,g.Page,g.Symbol,g.page_heading)
        texts=[t.get('text','') for t in page.texts]
        for value in ('ユニットNo. 3','UNIT1','GT15-RS4-TE','ユニットNo. 4','UNIT2','GT15-RS2-9P'):
            self.assertIn(value,texts)
        self.assertFalse(any(text.endswith(' GOTオプション') for text in texts))

    def test_all_models_are_selectable_and_generate(self):
        bodies = gui.part_catalog('model', 'gotbody')['mitsubishi']
        options = gui.part_catalog('left_model', 'gotoption')['mitsubishi']['got_options']
        self.assertEqual(len(bodies['got2000']), 56)
        self.assertEqual(len(bodies['got3000']), 10)
        self.assertEqual(len(options), 24)
        cfg = json.loads(Path('tests/fixtures/project.json').read_text(encoding='utf-8'))
        cfg['pages'] = [{'kind': 'gotbody', 'model': m} for m in g.GOT_BODY]
        cfg['pages'] += [{'kind': 'gotoption', 'right_model': m, 'right_ip': '192.168.1.2'} for m in g.GOT_OPTION]
        with tempfile.TemporaryDirectory() as folder:
            source, target = Path(folder) / 'project.json', Path(folder) / 'got.qet'
            source.write_text(json.dumps(cfg), encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()):
                g.main(str(source), str(target))
            self.assertEqual(len(ET.parse(target).findall('diagram')), len(g.GOT_BODY) + len(g.GOT_OPTION))

    def test_terminal_mode_preserves_nc_positions_without_connection(self):
        spec = g.GOT_BODY['GT2104-RTBD']
        page = hmi.build_body({'model': 'GT2104-RTBD', 'serial_mode': 'RS-232'}, g.build_symbols(), spec, g.Page, g.Symbol, g.page_heading)
        labels = [t.get('text', '') for t in page.texts]
        self.assertEqual(labels.count('NC（配線不可）'), 2)
        pins = [(x, y) for key, _, x, y in page.placed if key == 'module_pin']
        self.assertEqual(len(pins), 3 + 7)
        # NC の2行を空けてから端子が並ぶ
        nc_top = min(float(t.get('y')) for t in page.texts if t.get('text') == 'NC（配線不可）')
        serial = sorted(y for x, y in pins[3:])
        self.assertEqual(serial[0], nc_top + 7 + 2 * 24)

    def test_fixed_body_frame_and_repeated_ground_terminals(self):
        for model in ('GT2715-XTBD', 'GT2103-PMBLS', 'GT3715-FHCBD'):
            with self.subTest(model=model):
                page = hmi.build_body({'model': model}, g.build_symbols(), g.GOT_BODY[model], g.Page, g.Symbol, g.page_heading)
                self.assertTrue(all(80 < y < 810 for _, _, _, y in page.placed))
                ports = g.GOT_BODY[model]['power']['ports']
                pins = [e for key, e, _, _ in page.placed if key == 'module_pin']
                labels = [next(v.text for v in e.findall('./elementInformations/elementInformation') if v.get('name') == 'label') for e in pins[:len(ports)]]
                # 接地端子は LG・FG(2つのとき左から LG、FG。1つなら FG)
                grounds = [label for label, port in zip(labels, ports) if port == '⏚']
                self.assertEqual(grounds, ['LG', 'FG'] if len(grounds) == 2 else ['FG'] * len(grounds))
                ground_lines = [s for s in page.shapes if s.get('type') == 'Line' and s.get('x1') == s.get('x2') == '319']
                self.assertEqual(len(ground_lines), ports.count('⏚'))
                texts = [t.get('text', '') for t in page.texts]
                resolution = g.GOT_BODY[model].get('resolution', '') or g.GOT_BODY[model].get('display', {}).get('resolution', '')
                self.assertTrue(any(resolution in text for text in texts))
        self.assertNotIn('battery', gui.property_fields('gotbody', 'GT2103-PMBLS'))
        self.assertNotIn('sd_card', gui.property_fields('gotbody', 'GT2103-PMBLS'))
        self.assertIn('serial_mode', gui.property_fields('gotbody', 'GT2104-RTBD'))

    def test_option_panels_fit_drawing_height(self):
        for model in g.GOT_OPTION:
            with self.subTest(model=model):
                page = hmi.build_options({'left_model': model}, g.build_symbols(), g.GOT_OPTION, g.Page, g.Symbol, g.page_heading)
                self.assertTrue(all(y < 800 for _, _, _, y in page.placed))
                self.assertTrue(all(float(t.get('y', 0)) < 810 for t in page.texts))


if __name__ == '__main__':
    unittest.main()
