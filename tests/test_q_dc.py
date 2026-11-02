import unittest
import csv
import contextlib
import io
import json
import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET
import gen_io_page as gen


class QDcTest(unittest.TestCase):
    def rows(self, prefix):
        return [{'アドレス': f'{prefix}{i:X}', '機器番号': f'D{i}', '信号名': ''} for i in range(16)]

    def info(self, element, name):
        return element.find(f"./elementInformations/elementInformation[@name='{name}']").text

    def test_negative_common_input_uses_positive_contact_rail(self):
        page = gen.Page(gen.build_symbols())
        gen.iqr_input_half(page, 0, {'model': 'QX80'}, self.rows('X'), 0, 0)
        com = next(e for k, e, _, _ in page.placed if k == 'plc_in' and self.info(e, 'label') == 'COM')
        self.assertEqual(self.info(com, 'comment'), 'コモン')
        contact = next(e for k, e, _, _ in page.placed if k.startswith('contact'))
        wire = next(c for c in page.conductors if c.get('element2') == contact.get('uuid'))
        origin = next((x, y) for _, e, x, y in page.placed if e.get('uuid') == wire.get('element1'))
        self.assertEqual(origin[0], gen.IN_X['P'])

    def test_source_output_has_correct_power_and_load_rails(self):
        page = gen.Page(gen.build_symbols())
        gen.iqr_output_half(page, 0, {'model': 'QY80'}, self.rows('Y'), 0, 0)
        terminals = {self.info(e, 'label'): e for k, e, _, _ in page.placed if k == 'plc_out'}
        self.assertEqual(self.info(terminals['COM'], 'auxiliary1'), 'TB17')
        self.assertEqual(self.info(terminals['COM'], 'comment'), 'コモン')
        self.assertEqual(self.info(terminals['0V'], 'auxiliary1'), 'TB18')
        self.assertEqual(self.info(terminals['0V'], 'comment'), '外部電源')
        load = next(e for k, e, _, _ in page.placed if k == 'load_coil')
        wire = next(c for c in page.conductors if c.get('element1') == load.get('uuid') and
                    any(e.get('uuid') == c.get('element2') and k == 'junction' for k, e, _, _ in page.placed))
        rail_x = next(x for _, e, x, _ in page.placed if e.get('uuid') == wire.get('element2'))
        self.assertEqual(rail_x, gen.OUT_X['P'])
        self.assertTrue(any(t.get('text') == gen.LANE['N'] for t in page.texts))

    def test_64_point_units_split_and_preserve_connector_numbers(self):
        config = json.loads((Path(__file__).parent / 'fixtures' / 'project.json').read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)
            for model in ('QX42', 'QX42-S1', 'QX82', 'QX82-S1', 'QY42P', 'QY82P', 'RX42C4', 'RY42NT2P', 'RY42PT1P'):
                with self.subTest(model=model):
                    unit = gen.IO_UNITS[model]
                    prefix = 'X' if unit['io'] == 'in' else 'Y'
                    rows = self.rows(prefix) + [{'アドレス': f'{prefix}{i:X}', '機器番号': f'D{i}', '信号名': ''} for i in range(16, 64)]
                    with (path/'io.csv').open('w', encoding='utf-8', newline='') as f:
                        writer = csv.DictWriter(f, fieldnames=['アドレス', '機器番号', '信号名'])
                        writer.writeheader(); writer.writerows(rows)
                    config['pages'] = [{'kind': 'input' if prefix == 'X' else 'output', 'model': model,
                                        'csv': 'io.csv', 'title': model}]
                    (path/'input.json').write_text(json.dumps(config, ensure_ascii=False), encoding='utf-8')
                    with contextlib.redirect_stdout(io.StringIO()):
                        gen.main(str(path/'input.json'), str(path/'result.qet'))
                    diagrams = ET.parse(path/'result.qet').getroot().findall('.//diagram')
                    self.assertEqual(len(diagrams), 2)
                    for diagram, connector in zip(diagrams, ('1', '2')):
                        info = [x.text for x in diagram.findall('.//elementInformation')]
                        self.assertIn(connector + 'B20', info)
                        self.assertIn(connector + 'A5', info)
                        self.assertTrue(any(value and connector + 'B1' in value for value in info))
                        if prefix == 'Y': self.assertTrue(any(value and connector + 'A1' in value for value in info))

    def test_independent_relay_has_two_separate_terminals_per_channel(self):
        page = gen.Page(gen.build_symbols())
        gen.iqr_output_half(page, 0, {'model': 'QY18A'}, self.rows('Y')[:8], 0, 0)
        endpoints = [e for k, e, _, _ in page.placed if k == 'plc_out']
        self.assertEqual(len(endpoints), 16)
        for i in range(8):
            self.assertEqual(self.info(endpoints[2*i], 'comment'), '外部電源')
            self.assertEqual(self.info(endpoints[2*i], 'auxiliary1'), f'TB{2*i+1}')
            self.assertEqual(self.info(endpoints[2*i+1], 'auxiliary1'), f'TB{2*i+2}')
            self.assertEqual(self.info(endpoints[2*i], 'label'), self.info(endpoints[2*i+1], 'label'))

    def test_iqr_spring_terminal_layout(self):
        for model in ('RX40C7-TS', 'RY10R2-TS', 'RY40NT5P-TS', 'RY40PT5P-TS'):
            with self.subTest(model=model):
                unit = gen.IO_UNITS[model]
                self.assertEqual(unit['pins'][7:10], ['TB8', 'TB10', 'TB11'])
                self.assertEqual(unit['pins'][-1], 'TB17')
        self.assertEqual(gen.IO_UNITS['RX40C7-TS']['common'], ['TB9'])
        self.assertEqual(gen.IO_UNITS['RY10R2-TS']['com'], 'TB9')
        self.assertEqual(gen.IO_UNITS['RY40NT5P-TS']['vplus'], 'TB9')
        self.assertEqual(gen.IO_UNITS['RY40PT5P-TS']['vplus'], 'TB9')

    def test_iqr_independent_relay_terminal_pairs(self):
        page = gen.Page(gen.build_symbols())
        gen.iqr_output_half(page, 0, {'model': 'RY18R2A'}, self.rows('Y')[:8], 0, 0)
        endpoints = [e for k, e, _, _ in page.placed if k == 'plc_out']
        self.assertEqual([self.info(e, 'auxiliary1') for e in endpoints[:4]], ['TB2', 'TB1', 'TB4', 'TB3'])

    def test_32_point_spring_terminal_common_and_signals(self):
        expected = [f'TB{i}' for i in list(range(1, 17)) + list(range(18, 34))]
        for model in ('RX41C4-TS', 'RY41NT2P-TS', 'RY41PT1P-TS'):
            with self.subTest(model=model): self.assertEqual(gen.IO_UNITS[model]['pins'], expected)
        page = gen.Page(gen.build_symbols())
        rows = self.rows('X') + [{'アドレス': f'X{i:X}', '機器番号': f'D{i}', '信号名': ''} for i in range(16,32)]
        gen.iqr_input_half(page, 0, {'model': 'RX41C4-TS'}, rows[:16], 0, 0)
        gen.iqr_input_half(page, gen.HALF_W, {'model': 'RX41C4-TS'}, rows[16:], 1, 16)
        commons = [e for k,e,_,_ in page.placed if k == 'plc_in' and self.info(e,'label') == 'COM']
        self.assertEqual(len(commons), 1)
        self.assertEqual(self.info(commons[0], 'auxiliary1'), 'TB17')

    def test_diagnostic_input_and_output_supply_polarity(self):
        inp = gen.Page(gen.build_symbols())
        gen.iqr_input_half(inp, 0, {'model':'RX40NC6B'}, self.rows('X'), 0, 0)
        terms = {self.info(e,'label'):e for k,e,_,_ in inp.placed if k == 'plc_in' and self.info(e,'label') in ('COM','V+')}
        self.assertEqual(self.info(terms['COM'],'auxiliary1'),'TB18')
        self.assertEqual(self.info(terms['COM'],'comment'),'コモン')
        self.assertEqual(self.info(terms['V+'],'auxiliary1'),'TB17')
        self.assertEqual(self.info(terms['V+'],'comment'),'外部電源')
        out = gen.Page(gen.build_symbols())
        gen.iqr_output_half(out, 0, {'model':'RY40PT5B'}, self.rows('Y'), 0, 0)
        terms = {self.info(e,'label'):e for k,e,_,_ in out.placed if k == 'plc_out' and self.info(e,'label') in ('COM','0V')}
        self.assertEqual(self.info(terms['COM'],'auxiliary1'),'TB17')
        self.assertEqual(self.info(terms['0V'],'auxiliary1'),'TB18')

    def test_multi_pin_commons_have_separate_connectable_rows(self):
        rows = self.rows('Y')
        for model in ('QY41P', 'QY42P', 'RY41PT1P', 'RY42NT2P'):
            unit = gen.IO_UNITS[model]
            for half in range(unit['points'] // 16):
                with self.subTest(model=model, half=half):
                    page = gen.Page(gen.build_symbols())
                    gen.iqr_output_half(page, 0, {'model':model}, rows, half, half * 16)
                    terminals = [(e, y) for k,e,_,y in page.placed if k == 'plc_out' and self.info(e,'label') in ('COM','V+','0V')]
                    self.assertEqual(len(terminals), 2)
                    self.assertNotEqual(terminals[0][1], terminals[1][1])
                    for e, _ in terminals:
                        self.assertNotIn('/', self.info(e,'auxiliary1'))
                        self.assertTrue(any(e.get('uuid') in (wire.get('element1'),wire.get('element2')) for wire in page.conductors))

    def test_high_speed_outputs_have_no_external_power_terminal(self):
        rows = self.rows('Y')
        for model, common in (('RY41NT2H', 'A1/A2'), ('RY41PT2H', 'B1/B2')):
            with self.subTest(model=model):
                page = gen.Page(gen.build_symbols())
                gen.iqr_output_half(page, 0, {'model': model}, rows, 0, 0)
                gen.iqr_output_half(page, gen.HALF_W, {'model': model}, rows, 1, 16)
                terminals = [e for k,e,_,_ in page.placed if k == 'plc_out' and self.info(e,'label') in ('COM','V+','0V')]
                self.assertEqual([self.info(e, 'auxiliary1') for e in terminals], common.split('/'))


if __name__ == '__main__':
    unittest.main()
