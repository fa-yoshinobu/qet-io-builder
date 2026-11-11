from tests.qet_support import requires_qet
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

import gen_io_page as gen
import gui_core
from renderers import standard
from tools import qet_collection
from webgui.api import Api


class IdecRuSuTest(unittest.TestCase):
    @requires_qet
    def test_four_poles_and_fixed_voltage(self):
        for model, lever in [('RU4S-D24', True), ('RU4S-C-D24', False)]:
            with self.subTest(model=model), tempfile.TemporaryDirectory() as folder:
                spec = gen.STANDARD_DEVICES[model]
                self.assertEqual(spec['manual_test_lever'], lever)
                self.assertEqual(spec['coil']['rated_voltage'], 'DC24V')
                self.assertEqual(spec['coil']['polarity'], 'none')
                self.assertEqual(spec['ratings']['adjacent_pole_total_current_a'], 6)
                self.assertIn(model, gui_core.part_catalog('standard_model', '')['idec']['ru'])
                self.assertNotIn('error', Api().part_options(model))
                roots = {p.stem: ET.parse(p).getroot()
                         for p in standard.export_model(model, spec, folder)}
                self.assertEqual(len(roots), 5)
                self.assertEqual(roots['coil'].get('link_type'), 'master')
                for i in range(1, 5):
                    root = roots[f'contact_{i}']
                    self.assertEqual(root.get('link_type'), 'slave')
                    pins = {(float(t.get('x')), float(t.get('y'))): t.get('name')
                            for t in root.findall('./description/terminal')}
                    self.assertEqual(pins, {(0, 20): str(i + 8), (0, -20): str(i + 4), (-20, -20): str(i)})

    @requires_qet
    def test_sockets_have_electrical_pins_not_double_the_wire_entries(self):
        for model, poles in [('SU2S-21L', 2), ('SU4S-21L', 4)]:
            with self.subTest(model=model), tempfile.TemporaryDirectory() as folder:
                spec = gen.STANDARD_DEVICES[model]
                self.assertIn(model, gui_core.part_catalog('standard_model', '')['idec']['su'])
                self.assertNotIn('error', Api().part_options(model))
                self.assertEqual(spec['electrical_terminals'], 8 if poles == 2 else 14)
                mapping = {t['relay_pin']: t for t in spec['terminal_map']}
                expected = {'1': '12', '4': '42', '5': '14', '8': '44',
                            '9': '11', '12': '41', '13': 'A1', '14': 'A2'}
                if poles == 4:
                    expected.update({'2': '22', '3': '32', '6': '24', '7': '34', '10': '21', '11': '31'})
                self.assertEqual({p: t['socket_marking'] for p, t in mapping.items()},
                                 {p: f'{p}({iec})' for p, iec in expected.items()})
                self.assertTrue(all(t['wire_entries'] == 2 for t in mapping.values()))
                paths = standard.export_model(model, spec, folder)
                self.assertEqual(len(paths), len(expected))
                for path in paths:
                    root = ET.parse(path).getroot()
                    pin = path.stem.removeprefix('pin_')
                    self.assertEqual({t.get('name') for t in root.findall('./description/terminal')},
                                     {pin, f'{pin}({expected[pin]})'})
                for relay in spec['compatible_relays']:
                    pins = {p for _, _, roles in standard.bindings(gen.STANDARD_DEVICES[relay])
                            for labels in roles.values() for p in labels}
                    self.assertEqual(pins, set(expected))

    @requires_qet
    def test_register_all_four_models(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(
                qet_collection, 'user_collection_dir', return_value=Path(folder)):
            result = qet_collection.register_all_parts(
                models=['RU4S-D24', 'RU4S-C-D24', 'SU2S-21L', 'SU4S-21L'])
            self.assertTrue(result['ok'], result['errors'])
            self.assertEqual((result['models'], result['parts']), (4, 32))

    @requires_qet
    def test_timers_export_only_the_verified_on_delay_mode(self):
        for model, poles in [('GT5Y-2SN1D24', 2), ('GT5Y-4SN1D24', 4)]:
            with self.subTest(model=model), tempfile.TemporaryDirectory() as folder:
                spec = gen.STANDARD_DEVICES[model]
                self.assertIn(model, gui_core.part_catalog('standard_model', '')['idec']['gt5y'])
                self.assertNotIn('error', Api().part_options(model))
                self.assertEqual(spec['instantaneous_contacts'], 0)
                self.assertEqual([c['id'] for c in spec['configuration_options']], ['on_delay'])
                configured = standard.configured_spec(spec)
                with self.assertRaises(ValueError):
                    standard.configured_spec(spec, 'flicker')
                assignments = list(standard.bindings(configured))
                self.assertEqual(assignments[0][1], 'timer_on_delay')
                self.assertTrue(all(t == 'timer_changeover_on_delay' for _, t, _ in assignments[1:]))
                roots = {p.stem: ET.parse(p).getroot() for p in standard.export_model(model, spec, folder)}
                self.assertEqual(len(roots), poles + 1)
                texts = [t.findtext('text') for t in roots['timer'].findall('./description/dynamic_text')]
                self.assertIn('13 (-)', texts)
                self.assertIn('14 (+)', texts)
                for n, pin in enumerate([1, 4] if poles == 2 else [1, 2, 3, 4], 1):
                    root = roots[f'timed_contact_{n}']
                    actual = {(float(t.get('x')), float(t.get('y'))): t.get('name')
                              for t in root.findall('./description/terminal')}
                    self.assertEqual(actual, {(0, 20): str(pin + 8), (0, -20): str(pin + 4),
                                              (-20, -20): str(pin)})
                socket = gen.STANDARD_DEVICES[spec['socket_candidates'][0]]
                self.assertIn(model, socket['compatible_timers'])
                self.assertEqual({t['relay_pin'] for t in socket['terminal_map']},
                                 {pin for _, _, roles in assignments for pins in roles.values() for pin in pins})


if __name__ == '__main__':
    unittest.main()
