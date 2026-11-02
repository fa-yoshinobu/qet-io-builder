import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from xml.etree import ElementTree as ET

import gen_io_page as gen
import gui_core as core
from renderers import settings
from renderers.inverter import build_body
from webgui.api import Api


def terminals(model, side=None):
    spec = gen.INVERTERS[model]
    return [signal for key in ([side] if side else ('left', 'right'))
            for group in spec['terminal_groups'][key] for signal, _ in group['terminals']]


class InverterTest(unittest.TestCase):
    def test_port_labels_are_left_of_right_aligned_connector_drawings(self):
        spec = gen.INVERTERS['FR-E820-0.75K-EPA']
        page = build_body(dict(kind='inverter', model='FR-E820-0.75K-EPA'), spec, gen.build_symbols())
        ports = [item for item in page.placed if item[0].startswith('conn_') and item[0].endswith('_right')]
        self.assertEqual(len(ports), len(spec['ports']))
        for (key, _, x, _), port in zip(ports, spec['ports']):
            self.assertEqual(x, 830)
            text = next(t for t in page.texts if t.get('text') == port['name'])
            self.assertLess(float(text.get('x')), x)
            self.assertEqual(next(iter(page.sym[key].terminals.values()))[1], 'e')

    def test_narrow_box_wraps_long_purpose_without_changing_font_or_terminal_count(self):
        spec = copy.deepcopy(gen.INVERTERS['FR-D820-0.75K-042'])
        meaning = '試験用の長い用途を二行に折り返す'
        spec['terminal_groups']['left'][0]['terminals'][0][1] = meaning
        page = build_body(dict(kind='inverter', model='FR-D820-0.75K-042'), spec, gen.build_symbols())
        body = next(s for s in page.shapes if s.get('type') == 'Rectangle' and s.get('y1') == '52')
        self.assertEqual(float(body.get('x2')) - float(body.get('x1')), 440)
        lines = [t for t in page.texts if t.get('x') == '476' and 100 < float(t.get('y')) < 140]
        self.assertEqual(''.join(t.get('text') for t in lines), meaning)
        self.assertEqual(len(lines), 2)
        for line in lines:
            self.assertEqual(line.get('font').split(',')[1], '8')
            self.assertLessEqual(float(line.get('x')) + gen.text_w(line.get('text'), 8), 608)
        terminal = page.placed[0]
        center = (float(lines[0].get('y')) + float(lines[1].get('y'))) / 2 + 7
        self.assertEqual(terminal[3], center)

    def test_family_ranges_and_gui_selection(self):
        catalog = core.part_catalog('model', 'inverter')['mitsubishi']
        self.assertEqual(len(catalog['e800']), 204)
        self.assertEqual(len(catalog['d800']), 30)
        self.assertEqual(core.series_kinds('mitsubishi', 'e800', core.part_catalog('series', '')), ['inverter'])
        for model in ('FR-E820-22K-EPA', 'FR-E840-22K-EPC', 'FR-E810W-0.1K-4', 'FR-D820-15K-580', 'FR-D820S-2.2K-100'):
            api = Api(); api._data['pages'] = [dict(kind='inverter', model=model, tag='INV1')]
            page = api.page(0)
            self.assertNotIn('error', page)
            self.assertIn('tag', page['visible'])
            self.assertIn('unit_no', page['visible'])
            self.assertNotIn('slot', page['visible'])

    def test_standard_ethernet_and_monitor_terminals_follow_actual_hardware(self):
        fm = terminals('FR-E820-0.75K-1')
        am = terminals('FR-E820-0.75K-5')
        ethernet = terminals('FR-E820-0.75K-EPA')
        self.assertIn('STF', fm); self.assertIn('FM', fm); self.assertNotIn('AM', fm)
        self.assertEqual(fm.count('SD'), 3)
        self.assertIn('AM', am); self.assertNotIn('FM', am)
        self.assertEqual(am.count('5'), 2)
        self.assertEqual(am.count('SD'), 2)
        self.assertIn('DI0', ethernet); self.assertIn('DI1', ethernet)
        for absent in ('STF', 'STR', 'RH', 'RUN', 'FU', 'FM', 'AM'):
            self.assertNotIn(absent, ethernet)
        d = terminals('FR-D820-0.75K-042')
        self.assertIn('R+/FU', d); self.assertIn('R-/SD', d)
        self.assertNotIn('FU', d); self.assertNotIn('R+', d)
        self.assertEqual(d.count('PC'), 2)
        self.assertEqual(d.count('5'), 2)

    def test_supply_and_accessory_terminal_differences(self):
        self.assertIn('T/L3', terminals('FR-E820-0.75K-1'))
        for model in ('FR-E820S-0.75K-1', 'FR-D820S-0.75K-042'):
            self.assertNotIn('T/L3', terminals(model))
            self.assertIn('P1', terminals(model))
        for model in ('FR-E810W-0.1K-1', 'FR-D810W-0.1K-008'):
            self.assertNotIn('T/L3', terminals(model)); self.assertNotIn('P1', terminals(model))
            self.assertIn('PR', terminals(model))
            self.assertFalse(gen.INVERTERS[model]['brake_resistor_supported'])

    def test_settings_are_model_specific_and_ethercat_does_not_offer_ip(self):
        self.assertIn('ip', settings.profile('FR-E820-0.75K-EPA')['default'])
        for model in ('FR-E820-0.75K-EPC', 'FR-D820-0.75K-042'):
            self.assertNotIn('ip', settings.profile(model)['available'])
        api = Api(); api._data['pages'] = [dict(kind='inverter', model='FR-E820-0.75K-EPA', ip='192.168.1.20')]
        self.assertIn('ip', api.page(0)['visible'])
        self.assertNotIn('error', api.set_setting_visibility(0, 'ip', False))
        self.assertEqual(api._data['pages'][0]['ip'], '192.168.1.20')

    def test_all_definitions_generate_with_connectable_terminals_and_no_leads(self):
        cfg = json.loads((Path(__file__).parent / 'fixtures/project.json').read_text(encoding='utf-8'))
        cfg['pages'] = [dict(kind='inverter', model=m, tag='INV1') for m in gen.INVERTERS]
        with tempfile.TemporaryDirectory() as folder:
            source, target = Path(folder) / 'project.json', Path(folder) / 'all.qet'
            source.write_text(json.dumps(cfg, ensure_ascii=False), encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()):
                gen.main(str(source), str(target))
            diagrams = ET.parse(target).getroot().findall('./diagram')
            self.assertEqual(len(diagrams), len(gen.INVERTERS))
            for diagram, spec in zip(diagrams, gen.INVERTERS.values()):
                expected = sum(len(g['terminals']) for groups in spec['terminal_groups'].values() for g in groups) + len(spec['ports'])
                self.assertEqual(len(diagram.findall('./elements/element')), expected)
                wires = diagram.findall('./conductors/conductor')
                self.assertEqual(len(wires), len(spec['factory_jumpers']))
                self.assertTrue(all(w.get('num') == '短絡片' for w in wires))
                visible = [w for w in wires if w.get('displaytext') == '1']
                groups = {(j['side'], j['group']) for j in spec['factory_jumpers']}
                self.assertEqual(len(visible), len(groups))
                self.assertTrue(all(330 < float(w.get('userx')) < 400 or 840 < float(w.get('userx')) < 870 for w in visible))
                elements = {e.get('uuid'): e for e in diagram.findall('./elements/element')}
                for wire in visible:
                    if float(wire.get('userx')) > 840:
                        top_pin = min(float(elements[wire.get(key)].get('y')) for key in ('element1', 'element2'))
                        self.assertLess(float(wire.get('usery')) + 8 * gen.PX_PER_PT + 2 * gen.TEXT_MARGIN, top_pin)
        symbols = gen.build_symbols()
        build_body(cfg['pages'][0], gen.INVERTERS[cfg['pages'][0]['model']], symbols)
        for name in ('module_pin', 'inverter_pin_right'):
            self.assertEqual(len(symbols[name].terminals), 1)
            self.assertFalse([part for part in symbols[name].parts if part[0] == 'line'])


if __name__ == '__main__':
    unittest.main()
