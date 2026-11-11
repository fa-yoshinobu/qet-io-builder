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


TIMERS = ['MS4SA-CE', 'MS4SC-CE', 'ST7P-2 DC24V 10S', 'ST7P-4 DC24V 10S']
SOCKETS = ['TP48X', 'TP88X1', 'TP814X1']


class FujiTimersTest(unittest.TestCase):
    @requires_qet
    def test_terminal_maps_contact_timing_and_ratings(self):
        for model in TIMERS:
            spec = gen.STANDARD_DEVICES[model]
            ms = model.startswith('MS')
            poles = 4 if model.startswith('ST7P-4') else 2
            expected = [('1', '3', '4'), ('8', '6', '5')] if ms else [('9', '5', '1'), ('12', '8', '4')] if poles == 2 else [(str(i+8), str(i+4), str(i)) for i in range(1, 5)]
            self.assertEqual(spec['coil']['terminals'], ['2', '7'] if ms else ['13', '14'])
            self.assertFalse(spec['coil']['voltage_selection_required'])
            rating = spec['ratings']['resistive_contact_rating']
            self.assertEqual((rating['voltage_v_ac'], rating['current_a']), (250, 5) if ms else (240, 3))
            self.assertEqual(spec['instantaneous_contacts'], int(model == 'MS4SC-CE'))
            with self.subTest(model=model), tempfile.TemporaryDirectory() as folder:
                roots = {p.stem: ET.parse(p).getroot() for p in standard.export_model(model, spec, folder)}
                self.assertEqual(len(roots), poles + 1)
                texts = [t.findtext('text') for t in roots['timer'].findall('./description/dynamic_text')]
                for text in (('2 - (DC)', '7 + (DC)') if ms else ('13 (-)', '14 (+)')):
                    self.assertIn(text, texts)
                for i, pins in enumerate(expected, 1):
                    instant = model == 'MS4SC-CE' and i == 1
                    root = roots['instant_contact_1' if instant else f'timed_contact_{i}']
                    actual = {(float(t.get('x')), float(t.get('y'))): t.get('name') for t in root.findall('./description/terminal')}
                    self.assertEqual(actual, {(0, 20): pins[0], (0, -20): pins[1], (-20, -20): pins[2]})
                    self.assertEqual(root.findtext("./kindInformations/kindInformation[@name='type']"), 'simple' if instant else 'delayOn')

    @requires_qet
    def test_time_ranges_socket_compatibility_and_mode_guard(self):
        for model in TIMERS:
            spec = gen.STANDARD_DEVICES[model]
            if model.startswith('ST'):
                self.assertEqual(spec['time']['setting_range_total'], '1～10秒')
                self.assertEqual(spec['time']['range_code'], '10S')
            else:
                self.assertEqual(spec['time']['range_count'], 16)
                self.assertEqual(spec['time']['setting_range_total'], '0.05秒～60時間')
            socket = gen.STANDARD_DEVICES[spec['socket_candidates'][0]]
            self.assertIn(model, socket['compatible_timers'])
            pins = {p for _, _, labels in standard.bindings(standard.configured_spec(spec)) for values in labels.values() for p in values}
            self.assertEqual(pins, {t['relay_pin'] for t in socket['terminal_map']})
            self.assertEqual(socket['internal_connections'], [])
            self.assertTrue(all(t['socket_marking'] == t['relay_pin'] for t in socket['terminal_map']))
            with self.assertRaisesRegex(ValueError, '動作構成'):
                standard.configured_spec(spec, 'off_delay')
        for model, count in zip(SOCKETS, (8, 8, 14)):
            spec = gen.STANDARD_DEVICES[model]
            with tempfile.TemporaryDirectory() as folder:
                paths = standard.export_model(model, spec, folder)
                self.assertEqual(len(paths), count)
                for path in paths:
                    terminals = ET.parse(path).findall('./description/terminal')
                    self.assertEqual({t.get('name') for t in terminals}, {path.stem.removeprefix('pin_')})
                    self.assertEqual(len({t.get('uuid') for t in terminals}), 2)

    @requires_qet
    def test_gui_and_registration(self):
        picker = gui_core.part_catalog('standard_model', '')
        for model in TIMERS:
            self.assertIn(model, picker['fuji']['ms4s' if model.startswith('MS') else 'st7p'])
            self.assertNotIn('error', Api().part_options(model))
        with tempfile.TemporaryDirectory() as folder, patch.object(qet_collection, 'user_collection_dir', return_value=Path(folder)):
            result = qet_collection.register_all_parts(models=TIMERS + SOCKETS)
            self.assertTrue(result['ok'], result['errors'])
            self.assertEqual((result['models'], result['parts']), (7, 44))


if __name__ == '__main__':
    unittest.main()
