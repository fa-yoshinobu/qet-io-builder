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


class FujiHhTpTest(unittest.TestCase):
    RELAYS = {'HH52P': (2, False), 'HH52P-L': (2, True),
              'HH54P': (4, False), 'HH54P-L': (4, True)}
    SOCKETS = {'TP58X1': 8, 'TP58X2': 8, 'TP514X1': 14, 'TP514X2': 14}

    @requires_qet
    def test_relay_body_pins_and_led_polarity(self):
        catalog = gui_core.part_catalog('standard_model', '')
        for model, (poles, led) in self.RELAYS.items():
            with self.subTest(model=model), tempfile.TemporaryDirectory() as folder:
                self.assertIn(model, catalog['fuji']['hh'])
                self.assertNotIn('error', Api().part_options(model))
                spec = gen.STANDARD_DEVICES[model]
                self.assertEqual(spec['coil']['voltages'], {'dc_v': ['24']})
                self.assertFalse(spec['coil']['voltage_selection_required'])
                roots = {p.stem: ET.parse(p).getroot()
                         for p in standard.export_model(model, spec, folder)}
                self.assertEqual(len(roots), poles + 1)
                coil = roots['coil']
                self.assertEqual(coil.get('link_type'), 'master')
                self.assertEqual({t.get('name') for t in coil.findall('./description/terminal')}, {'13', '14'})
                texts = [t.findtext('text') for t in coil.findall('./description/dynamic_text')]
                if led:
                    self.assertIn('13 (-)', texts)
                    self.assertIn('14 (+)', texts)
                else:
                    self.assertNotIn('14 (+)', texts)
                for part, pin in enumerate([1, 4] if poles == 2 else [1, 2, 3, 4], 1):
                    contact = roots[f'contact_{part}']
                    self.assertEqual(contact.get('link_type'), 'slave')
                    actual = {(float(t.get('x')), float(t.get('y'))): t.get('name')
                              for t in contact.findall('./description/terminal')}
                    self.assertEqual(actual, {(0, 20): str(pin + 8), (0, -20): str(pin + 4),
                                              (-20, -20): str(pin)})

    @requires_qet
    def test_socket_maps_each_external_terminal_to_the_same_relay_pin(self):
        for model, count in self.SOCKETS.items():
            with self.subTest(model=model), tempfile.TemporaryDirectory() as folder:
                spec = gen.STANDARD_DEVICES[model]
                self.assertIn(model, gui_core.part_catalog('standard_model', '')['fuji']['tp'])
                self.assertNotIn('error', Api().part_options(model))
                expected = {'1', '4', '5', '8', '9', '12', '13', '14'} if count == 8 else set(map(str, range(1, 15)))
                self.assertEqual({t['socket_marking'] for t in spec['terminal_map']}, expected)
                paths = standard.export_model(model, spec, folder)
                self.assertEqual(len(paths), count)
                for path in paths:
                    root = ET.parse(path).getroot()
                    self.assertEqual(root.get('link_type'), 'terminal')
                    self.assertEqual([t.get('name') for t in root.findall('./description/terminal')],
                                     [path.stem.removeprefix('pin_')] * 2)
                for relay in spec['compatible_relays']:
                    actual_pins = {p for _, _, roles in standard.bindings(gen.STANDARD_DEVICES[relay])
                                   for pins in roles.values() for p in pins}
                    self.assertEqual(actual_pins, expected)

    @requires_qet
    def test_bulk_registration(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(
                qet_collection, 'user_collection_dir', return_value=Path(folder)):
            result = qet_collection.register_all_parts(models=list(self.RELAYS) + list(self.SOCKETS))
            self.assertTrue(result['ok'], result['errors'])
            self.assertEqual((result['models'], result['parts']), (8, 60))


if __name__ == '__main__':
    unittest.main()
