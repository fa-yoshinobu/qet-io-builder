import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from xml.etree import ElementTree as ET

import gen_io_page as gen
from renderers.controllers import expansion_items, build_body
from renderers.terminal_pages import build_pages, terminal_rows
from webgui.api import Api


class MxfDetailsTest(unittest.TestCase):
    def api(self):
        api = Api()
        api._data['pages'] = [dict(kind='mxbody', model='MXF100-16-P32', tag='PLC1', unit_no='1')]
        return api

    def test_model_specs_and_body_texts_follow_manuals(self):
        for model, spec in gen.MX_CPU.items():
            self.assertEqual(spec['inputs'], 16)
            self.assertEqual(spec['outputs'], 16)
            self.assertEqual(spec['max_axes'], 8 if '-8-' in model else 16)
            self.assertEqual(spec['output_type'], 'ソース' if '-P32' in model else 'シンク')
            self.assertEqual(spec['ports'][1]['name'], 'P2 Ethernet' if model.endswith('-EC') else 'P2 Ethernet / TSN')
            p = build_body(dict(kind='mxbody', model=model), spec, gen.build_symbols())
            texts = [t.get('text') for t in p.texts]
            self.assertIn(f"MX-F {spec['max_axes']}軸 / 30MB", texts)
            self.assertIn('出力16点 ' + spec['output_type'] + ' DC5～30V', texts)

    def test_terminal_marking_stays_fixed_when_plc_address_changes(self):
        rows = terminal_rows(dict(x_start='30', y_start='40'), gen.MX_IO['MXF100-H32P'])
        self.assertEqual((rows[0]['terminal'], rows[0]['signal']), ('X00', 'X30'))
        self.assertEqual((rows[18]['terminal'], rows[18]['signal']), ('Y00', 'Y40'))
        self.assertEqual(sum(r['terminal'] == '+V0' for r in rows), 2)
        with self.assertRaisesRegex(ValueError, '固定'):
            terminal_rows(dict(x_start='10'), gen.MX_CPU['MXF100-16-N32'])
        pages = build_pages(dict(kind='mxio', model='MXF100-H32P'), gen.MX_IO['MXF100-H32P'], gen.build_symbols())
        p = pages[0][1]
        symbol = p.sym['plc_in_mx']
        self.assertEqual(symbol.height, 38)
        self.assertEqual(p.placed[1][3] - p.placed[0][3], symbol.height)
        self.assertEqual(next(a for tag, a in symbol.parts if tag == 'rect')['height'], 38)

    def test_selection_limits_and_invalid_change_roll_back(self):
        api = self.api()
        self.assertEqual(len(api.catalog('modules', 0)['rows']), 13)
        for i, model in enumerate(('FX5-485ADP', 'FX5-232ADP')):
            self.assertNotIn('error', api.set_module(0, 0, i, model))
        before = json.dumps(api._data)
        self.assertIn('error', api.set_module(0, 0, 2, 'FX5-485ADP'))
        self.assertEqual(json.dumps(api._data), before)
        self.assertIn('error', api.set_module(0, 0, 2, 'FX5-485-BD'))
        with self.assertRaisesRegex(ValueError, '12台'):
            expansion_items(dict(model='MXF100-16-P32', modules=['MXF100-X32'] * 13))

    def test_generated_pages_share_tags_and_use_separate_hex_io_counters(self):
        api = self.api()
        for index, model in enumerate(('FX5-485ADP', 'MXF100-X32', 'MXF100-H32P')):
            api.set_module(0, 0, index, model)
            api.set_module_tag(0, 0, index, ('COM1', 'DI1', 'IO1')[index])
        cpu_page = api.create_cpu_io_page(0)['index']
        self.assertEqual(api._data['pages'][cpu_page]['tag'], 'PLC1')
        self.assertEqual(api.create_cpu_io_page(0)['index'], cpu_page)
        self.assertNotIn('error', api.create_all_unit_pages(0))
        mixed = next(p for p in api._data['pages'] if p.get('kind') == 'mxio' and p.get('model') == 'MXF100-H32P')
        self.assertEqual((mixed['x_start'], mixed['y_start'], mixed['tag'], mixed['unit_no']), ('30', '10', 'IO1', '3'))
        order = [item['id'] for item in api.page(0)['rack']['stages'][0]['items']]
        self.assertLess(order.index('0:0'), order.index('cpu'))
        self.assertGreater(order.index('0:1'), order.index('cpu'))
        api._data['pages'][cpu_page]['tag'] = 'OLD'
        differences = api.detail_differences()
        row = next(r for r in differences['rows'] if r['page'] == cpu_page)
        self.assertEqual(row['expected']['tag'], 'PLC1')

    def test_all_mxf_models_and_selected_composition_generate(self):
        cfg = json.loads(Path('tests/fixtures/project.json').read_text(encoding='utf-8'))
        cfg['pages'] = [dict(kind='mxbody', model=m, modules=['FX5-4AD-ADP', 'MXF100-H32N']) for m in gen.MX_CPU]
        cfg['pages'] += [dict(kind='mxio', model=m) for m in gen.MX_IO]
        with tempfile.TemporaryDirectory() as folder:
            source, target = Path(folder) / 'project.json', Path(folder) / 'all.qet'
            source.write_text(json.dumps(cfg, ensure_ascii=False), encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()):
                gen.main(str(source), str(target))
            diagrams = ET.parse(target).getroot().findall('./diagram')
            self.assertEqual(len(diagrams), 18)
            for diagram in diagrams:
                self.assertTrue(all(float(t.get('y')) <= 800 for t in diagram.findall('./inputs/input')))


if __name__ == '__main__':
    unittest.main()
