import json
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

import gen_io_page as g
from tools.export_power_supply_elements import definition


ROOT = Path(__file__).resolve().parents[1] / 'parts/power_supply/omron'


class PowerSupplyElementsTest(unittest.TestCase):
    def test_twenty_components_load_without_a_page(self):
        specs = g.read_unit_definitions()['power_supply']
        self.assertEqual(sum(model.startswith('S8VK-') for model in specs), 20)
        self.assertTrue(all(s['output']['voltage_v'] == 24 for s in specs.values()))

    def test_each_physical_terminal_has_an_independent_connection(self):
        expected = {'S8VK-G01524': 7, 'S8VK-G48024': 8,
                    'S8VK-S03024': 10, 'S8VK-S24024': 12,
                    'S8VK-X12024A-EIP': 11}
        for model, count in expected.items():
            path = next(ROOT.glob('*/elements/' + model + '.elmt'))
            element = ET.parse(path).getroot()
            self.assertEqual(element.tag, 'definition')
            terminals = element.findall('./description/terminal')
            self.assertEqual(len(terminals), count)
            self.assertEqual(len({t.get('uuid') for t in terminals}), count)
            self.assertTrue(any(t.get('orientation') == 'w' for t in terminals))
            self.assertTrue(any(t.get('orientation') == 'e' for t in terminals))

    def test_export_is_stable_and_within_component_bounds(self):
        for path in ROOT.glob('*/power_supply/*.json'):
            data = json.loads(path.read_text(encoding='utf-8'))
            model, spec = data['model'], data['definition']
            a, b = definition(model, spec), definition(model, spec)
            self.assertEqual(ET.tostring(a), ET.tostring(b))
            frame = a.find('./description/rect[@y="0"]')
            width, height = float(frame.get('width')), float(frame.get('height'))
            for terminal in a.findall('./description/terminal'):
                self.assertTrue(0 <= float(terminal.get('x')) <= width)
                self.assertTrue(0 <= float(terminal.get('y')) <= height)
            saved = ET.parse(path.parent.parent / 'elements' / (model + '.elmt')).getroot()
            self.assertEqual(len(saved.findall('./description/terminal')), len(a.findall('./description/terminal')))

    def test_round_terminals_touch_frame_without_external_leads(self):
        for model, spec in g.read_unit_definitions()['power_supply'].items():
            desc = definition(model, spec).find('description')
            width = float(desc.find('./rect[@y="0"]').get('width'))
            for terminal in desc.findall('terminal'):
                if terminal.get('name') in [p['name'] for p in spec.get('interfaces', [])]:
                    continue
                y = float(terminal.get('y'))
                left = terminal.get('orientation') == 'w'
                circle_x = 0 if left else width-8
                self.assertTrue(any(float(c.get('x')) == circle_x and float(c.get('y')) + 4 == y
                                    for c in desc.findall('circle')), model)
                self.assertEqual(float(terminal.get('x')), 0 if left else width, model)
                self.assertFalse(any(float(line.get('y1')) == y and float(line.get('y2')) == y
                                     and (min(float(line.get('x1')),float(line.get('x2'))) < 0 or
                                          max(float(line.get('x1')),float(line.get('x2'))) > width)
                                     for line in desc.findall('line')), model)
            output_labels = [t for t in desc.findall('text') if t.get('text') in ('+', '-', '+V1', '-V1', 'DC LOW1')]
            self.assertTrue(all(float(t.get('x')) > 180 for t in output_labels), model)

    def test_sparse_boxes_are_half_height_and_dense_boxes_keep_their_format(self):
        specs = g.read_unit_definitions()['power_supply']
        small = ([m for m in specs if m.startswith('S8FS-G')] +
                 [m for m in specs if m.startswith('S8VK-G')] +
                 ['S8VK-S03024', 'S8VK-S06024', 'S8VK-S12024'])
        self.assertEqual(len(small), 18)
        for model, spec in specs.items():
            with self.subTest(model=model):
                root = definition(model, spec)
                desc = root.find('description')
                frame = desc.find('./rect[@y="0"]')
                expected_height = 150 if model in small else 700 if model.startswith('S8AS2-') else 300
                self.assertEqual(float(frame.get('height')), expected_height)
                if model in small:
                    self.assertEqual(float(frame.get('width')), 240)
                    pins = desc.findall('terminal')
                    self.assertTrue(all(76 <= float(p.get('y')) <= 132 for p in pins))
                    # コンパクト枠でも文字サイズは縮小しすぎず、入力電圧を端子列の上へ移す。
                    supply = next(t for t in desc.findall('text') if t.get('text') == spec['input']['voltage'])
                    self.assertEqual(float(supply.get('y')), 37)
                    self.assertTrue(all(float(t.get('y')) < 150 for t in desc.findall('text')))
                elif not model.startswith('S8AS2-'):
                    self.assertTrue(all(float(p.get('y')) >= 90 for p in desc.findall('terminal')))

    def test_all_output_terminal_labels_are_right_aligned(self):
        for model, spec in g.read_unit_definitions()['power_supply'].items():
            root = definition(model, spec)
            labels = root.findall("./description/dynamic_text[@text_from='UserText']")
            output_pins = [p for p in root.findall('./description/terminal')
                           if p.get('orientation') == 'e' and p.get('name') not in
                           {port['name'] for port in spec.get('interfaces', [])}]
            self.assertEqual(len(labels), len(output_pins), model)
            self.assertTrue(all(n.get('Halignment') == 'AlignRight' for n in labels), model)
            expected = 246 if model.startswith('S8AS2-') else 226
            self.assertEqual({float(n.get('x')) + float(n.get('text_width')) for n in labels}, {expected}, model)

    def test_network_connections_touch_the_connector_without_a_lead(self):
        for model, spec in g.read_unit_definitions()['power_supply'].items():
            if not spec.get('interfaces'):
                continue
            desc = definition(model, spec).find('description')
            names = {port['name'] for port in spec['interfaces']}
            terminals = [t for t in desc.findall('terminal') if t.get('name') in names]
            self.assertTrue(terminals, model)
            for terminal in terminals:
                x, y = float(terminal.get('x')), float(terminal.get('y'))
                self.assertEqual(x, 230, model)
                self.assertFalse(any(float(line.get('y1')) == y == float(line.get('y2'))
                                     and max(float(line.get('x1')), float(line.get('x2'))) > x
                                     for line in desc.findall('line')), model)


if __name__ == '__main__':
    unittest.main()
