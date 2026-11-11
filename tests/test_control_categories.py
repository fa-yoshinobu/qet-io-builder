from tests.qet_support import requires_qet
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET

import gen_io_page as g
import gui_core as gui
from renderers import standard


class ControlCategoriesTest(unittest.TestCase):
    def test_six_requested_categories_are_selectable(self):
        counts = Counter(s['device_type'] for s in g.STANDARD_DEVICES.values())
        for key, minimum in {'terminal': 8, 'breaker': 6, 'fuse_holder': 3,
                             'electronic_protector': 3, 'socket': 13, 'switch': 10,
                             'lamp': 6, 'thermal_relay': 6, 'timer': 4}.items():
            self.assertGreaterEqual(counts[key], minimum)
        picker = gui.part_catalog('standard_model', '')
        self.assertIn('S8V-CP0824', picker['omron']['s8v_cp'])
        self.assertIn('FHN-15', picker['toho']['fh'])

    def test_electronic_protector_has_exact_terminals_and_no_load_return(self):
        for model, count in [('S8V-CP0424', 11), ('S8V-CP0424S', 11), ('S8V-CP0824', 15)]:
            with self.subTest(model=model), tempfile.TemporaryDirectory() as folder:
                paths = standard.export_model(model, g.STANDARD_DEVICES[model], folder)
                self.assertEqual(len(paths), 1)
                xml = ET.parse(paths[0]).getroot()
                terms = xml.findall('./description/terminal')
                names = [t.get('name') for t in terms]
                self.assertEqual(len(terms), count)
                self.assertEqual(len({t.get('uuid') for t in terms}), count)
                self.assertIn('-VI1', names)
                self.assertNotIn('-VO1', names)
                self.assertIn('負荷電流を流さない', xml.findtext('informations'))
                for terminal in terms:
                    self.assertLess(float(terminal.get('y')), 410)
                    left = terminal.get('orientation') == 'w'
                    self.assertEqual(float(terminal.get('x')), 0 if left else 260)
                    y = float(terminal.get('y'))
                    circles = xml.findall('./description/circle')
                    self.assertTrue(any(float(c.get('x')) == (0 if left else 252)
                                        and float(c.get('y'))+4 == y for c in circles))
                    self.assertFalse(any(float(line.get('y1')) == y and float(line.get('y2')) == y
                                         and (min(float(line.get('x1')),float(line.get('x2'))) < 0 or
                                              max(float(line.get('x1')),float(line.get('x2'))) > 260)
                                         for line in xml.findall('./description/line')))

    @requires_qet
    def test_timer_uses_delayed_contacts_and_dc_only_polarity(self):
        for model, contact_count in [('H3Y-2', 2), ('H3Y-4', 4)]:
            with tempfile.TemporaryDirectory() as folder:
                paths = standard.export_model(model, g.STANDARD_DEVICES[model], folder)
                self.assertEqual(len(paths), contact_count + 1)
                texts = [t.findtext('text') for t in ET.parse(paths[0]).findall('./description/dynamic_text')]
                self.assertIn('13 - (DC)', texts)
                self.assertIn('14 + (DC)', texts)
                for path in paths[1:]:
                    self.assertEqual(ET.parse(path).findtext("./kindInformations/kindInformation[@name='type']"), 'delayOn')

    @requires_qet
    def test_thermal_trip_and_unselected_setting_are_preserved(self):
        model = 'TR18X3H-005'
        spec = g.STANDARD_DEVICES[model]
        self.assertIsNone(spec['ratings']['selected_current_a'])
        with tempfile.TemporaryDirectory() as folder:
            paths = standard.export_model(model, spec, folder)
            self.assertEqual(len(paths), 3)
            nc, no = ET.parse(paths[1]), ET.parse(paths[2])
            self.assertEqual({t.get('name') for t in nc.findall('./description/terminal')}, {'95', '96'})
            self.assertEqual({t.get('name') for t in no.findall('./description/terminal')}, {'97', '98'})
            comment = ET.parse(paths[0]).findtext("./elementInformations/elementInformation[@name='comment']")
            self.assertIn('整定値未指定', comment)


if __name__ == '__main__':
    unittest.main()
