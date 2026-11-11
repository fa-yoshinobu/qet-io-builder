import copy
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

import gen_io_page as g
import gui_core as gui
from renderers.standard import export_model


class EthernetSwitchExportTest(unittest.TestCase):
    def test_all_switches_export_exact_terminals_and_common_frame(self):
        switches = {m: s for m, s in g.STANDARD_DEVICES.items() if s.get('device_type') == 'ethernet_switch'}
        self.assertEqual(len(switches), 10)
        frames = set()
        for model, spec in switches.items():
            with self.subTest(model=model), tempfile.TemporaryDirectory() as folder:
                paths = export_model(model, spec, folder, elements=Path(folder) / 'no_collection')
                xml = ET.parse(paths[0]).getroot()
                terms = xml.findall('./description/terminal')
                desc = xml.find('description')
                for terminal in terms:
                    if terminal.get('name').startswith('PORT '):
                        continue
                    y = float(terminal.get('y'))
                    self.assertTrue(any(float(c.get('x')) == 0 and float(c.get('y')) + 4 == y
                                        for c in desc.findall('circle')))
                    self.assertEqual(float(terminal.get('x')), 0)
                    self.assertFalse(any(float(line.get('y1')) == y and float(line.get('y2')) == y
                                         and min(float(line.get('x1')),float(line.get('x2'))) < 0
                                         for line in desc.findall('line')))
                expected = [t['label'] for t in spec['power']['terminals']]
                if spec.get('ground'):
                    expected.append(spec['ground']['label'])
                expected += [t['label'] for t in spec.get('alarm', {}).get('terminals', [])]
                expected += ['PORT ' + p['label'] for p in spec['ports']]
                self.assertEqual([t.get('name') for t in terms], expected)
                self.assertEqual(len({t.get('uuid') for t in terms}), len(terms))
                self.assertTrue(all(t.get('orientation') == 'w' and float(t.get('x')) ==
                                    (14 if t.get('name').startswith('PORT ') else 0) for t in terms))
                self.assertTrue(all(0 < float(t.get('y')) < 750 for t in terms))
                frames.add(tuple(xml.find('./description/rect').get(k) for k in ('x', 'y', 'width', 'height')))
                self.assertIn(spec['power']['voltage'], xml.findtext('informations'))
                self.assertIn(''.join(spec['power']['voltage'].split()),
                              ''.join(''.join(n.get('text', '').split()) for n in xml.findall('./description/text')))
                self.assertIn(spec['source'], xml.findtext('informations'))
                texts = [n.findtext('text', '') for n in xml.findall('./description/dynamic_text') if n.get('text_from') == 'UserText']
                self.assertEqual(bool(texts), bool(spec.get('dip_switches')))
                if texts:
                    self.assertIn('（記入）', texts[0])
                if spec.get('alarm'):
                    self.assertIn(spec['alarm']['note'], xml.findtext('informations'))
                    self.assertIn(spec['alarm']['display_note'], [n.get('text') for n in xml.findall('./description/text')])
                # 再生成時に接続点IDが変わらず、既存配線を識別できる。
                second = ET.parse(export_model(model, spec, folder)[0]).getroot()
                self.assertEqual([t.attrib for t in terms], [t.attrib for t in second.findall('./description/terminal')])
        self.assertEqual(frames, {('0', '0', '260', h) for h in ('540', '600', '750')})

    def test_five_port_boxes_shrink_without_crowding_connectors(self):
        from renderers.ethernet_switch import definition
        switches = {m: s for m, s in g.STANDARD_DEVICES.items() if s.get('device_type') == 'ethernet_switch'}
        small = 0
        for model, spec in switches.items():
            desc = definition(model, spec).find('description')
            height = float(desc.find('./rect[@y="0"]').get('height'))
            if len(spec['ports']) == 5:
                small += 1
                self.assertEqual(height, 600 if model == 'IESH-MB205G-R' else 540)
            else:
                self.assertEqual(height, 750)
            ports = [t for t in desc.findall('terminal') if t.get('name').startswith('PORT ')]
            ys = [float(t.get('y')) for t in ports]
            self.assertTrue(all(b-a == 50 for a, b in zip(ys, ys[1:])))
            footer = max(float(line.get('y1')) for line in desc.findall('line')
                         if line.get('x1') == '0' and line.get('x2') == '260')
            self.assertGreaterEqual(footer - (ys[-1]+20), 10)
            self.assertTrue(all(float(t.get('y')) < height for t in desc.findall('text')))
            for text in desc.findall("./dynamic_text[@text_from='UserText']"):
                self.assertLess(float(text.get('y')) + len(text.findtext('text').splitlines())*12, height)
        self.assertEqual(small, 5)

    def test_invalid_connector_or_terminal_count_does_not_write(self):
        original = g.STANDARD_DEVICES['IESH-MB205-R']
        for change in ('optical', 'too_many_ports', 'too_many_terminals'):
            spec = copy.deepcopy(original)
            if change == 'optical':
                spec['ports'][0]['type'] = 'optical'
            elif change == 'too_many_ports':
                spec['ports'] = [{'label': str(n), 'type': 'rj45', 'speed': 'test'} for n in range(9)]
            else:
                spec['power']['terminals'] *= 4
            with self.subTest(change=change), tempfile.TemporaryDirectory() as folder:
                target = Path(folder) / 'not_written'
                with self.assertRaises(ValueError):
                    export_model('TEST', spec, target)
                self.assertFalse(target.exists())

    def test_gui_can_select_both_misumi_series(self):
        picker = gui.part_catalog('standard_model', '')
        self.assertEqual(len(picker['misumi']['iesh']), 6)
        self.assertEqual(len(picker['misumi']['industrial_switch']), 4)
        self.assertEqual(gui.MAKER_NAMES['misumi'], 'MISUMI')


if __name__ == '__main__':
    unittest.main()
