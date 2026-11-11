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


MODELS = [f'H3YN-{t}-B DC24' for t in ('2', '21', '4', '41')]


class OmronH3ynTest(unittest.TestCase):
    @requires_qet
    def test_pins_polarity_contact_ratings_and_time_ranges(self):
        for model in MODELS:
            typ = model.split('-')[1]
            poles = 2 if typ.startswith('2') else 4
            spec = gen.STANDARD_DEVICES[model]
            self.assertEqual(spec['instantaneous_contacts'], 0)
            self.assertEqual(spec['coil']['rated_voltage'], 'DC24V')
            self.assertFalse(spec['coil']['voltage_selection_required'])
            self.assertEqual(spec['ratings']['resistive_contact_rating']['current_a'], 5 if poles == 2 else 3)
            self.assertEqual(spec['time']['range_options'], ['1min', '10min', '1h', '10h'] if len(typ) == 2 else ['1s', '10s', '1min', '10min'])
            assignments = list(standard.bindings(standard.configured_spec(spec)))
            pins = {pin for _, _, roles in assignments for values in roles.values() for pin in values}
            socket = gen.STANDARD_DEVICES[spec['socket_candidates'][0]]
            self.assertIn(model, socket['compatible_timers'])
            self.assertEqual(pins, {p['relay_pin'] for p in socket['terminal_map']})
            with self.subTest(model=model), tempfile.TemporaryDirectory() as folder:
                roots = {p.stem: ET.parse(p).getroot() for p in standard.export_model(model, spec, folder)}
                self.assertEqual(len(roots), poles + 1)
                texts = [t.findtext('text') for t in roots['timer'].findall('./description/dynamic_text')]
                self.assertIn('13 (-)', texts)
                self.assertIn('14 (+)', texts)
                self.assertEqual(roots['timer'].get('link_type'), 'master')
                for n, pin in enumerate((1, 4) if poles == 2 else (1, 2, 3, 4), 1):
                    root = roots[f'timed_contact_{n}']
                    self.assertEqual(root.get('link_type'), 'slave')
                    self.assertEqual(root.findtext("./kindInformations/kindInformation[@name='type']"), 'delayOn')
                    actual = {(float(t.get('x')), float(t.get('y'))): t.get('name') for t in root.findall('./description/terminal')}
                    self.assertEqual(actual, {(0, 20): str(pin + 8), (0, -20): str(pin + 4), (-20, -20): str(pin)})

    def test_only_verified_mode_is_exported_and_gui_can_select_models(self):
        picker = gui_core.part_catalog('standard_model', '')
        for model in MODELS:
            self.assertIn(model, picker['omron']['h3yn'])
            self.assertNotIn('error', Api().part_options(model))
            spec = gen.STANDARD_DEVICES[model]
            self.assertEqual([c['id'] for c in spec['configuration_options']], ['on_delay'])
            for mode in ('interval', 'flicker_on', 'flicker_off', 'pulse'):
                with self.assertRaisesRegex(ValueError, '動作構成'):
                    standard.configured_spec(spec, mode)

    @requires_qet
    def test_all_four_models_register(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(qet_collection, 'user_collection_dir', return_value=Path(folder)):
            result = qet_collection.register_all_parts(models=MODELS)
            self.assertTrue(result['ok'], result['errors'])
            self.assertEqual((result['models'], result['parts']), (4, 16))
            self.assertTrue((Path(folder) / 'qet-io-builder/omron/h3yn/H3YN-41-B DC24/on_delay/timed_contact_4.elmt').exists())


if __name__ == '__main__':
    unittest.main()
