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


A8 = 'H3CR-A8 AC24-48/DC12-48'
A8E = 'H3CR-A8E AC/DC24-48'


class OmronH3crTest(unittest.TestCase):
    def test_supply_pins_and_timed_vs_instant_contacts(self):
        for model, dc_min in ((A8, 12), (A8E, 24)):
            spec = gen.STANDARD_DEVICES[model]
            self.assertEqual(spec['ratings']['supply_vdc_range'], [dc_min, 48])
            self.assertEqual(spec['ratings']['supply_vac_range'], [24, 48])
            self.assertEqual(spec['coil']['terminals'], ['2', '7'])
            self.assertEqual(spec['coil']['polarity_by_terminal'], {'2': '− (DC)', '7': '+ (DC)'})
            self.assertEqual(spec['instantaneous_contacts'], int(model == A8E))
            self.assertEqual(spec['time']['setting_range_total'], '0.05秒～300時間')
            with tempfile.TemporaryDirectory() as folder:
                roots = {p.stem: ET.parse(p).getroot() for p in standard.export_model(model, spec, folder)}
                self.assertEqual(len(roots), 3)
                self.assertEqual(roots['timer'].get('link_type'), 'master')
                texts = [t.findtext('text') for t in roots['timer'].findall('./description/dynamic_text')]
                self.assertIn('2 − (DC)', texts)
                self.assertIn('7 + (DC)', texts)
                for part, pins, kind in (
                    ('instant_contact_1' if model == A8E else 'timed_contact_1', ('1', '3', '4'), 'simple' if model == A8E else 'delayOn'),
                    ('timed_contact_2', ('8', '6', '5'), 'delayOn'),
                ):
                    root = roots[part]
                    self.assertEqual(root.get('link_type'), 'slave')
                    self.assertEqual(root.findtext("./kindInformations/kindInformation[@name='type']"), kind)
                    if part == 'instant_contact_1':
                        self.assertIn('瞬時c接点1', root.findtext("./names/name[@lang='ja']"))
                    actual = {(float(t.get('x')), float(t.get('y'))): t.get('name') for t in root.findall('./description/terminal')}
                    self.assertEqual(actual, {(0, 20): pins[0], (0, -20): pins[1], (-20, -20): pins[2]})

    def test_socket_mapping_mode_guard_and_picker(self):
        socket = gen.STANDARD_DEVICES['P2CF-08']
        self.assertEqual(socket['electrical_terminals'], 8)
        self.assertEqual([(p['socket_marking'], p['relay_pin']) for p in socket['terminal_map']], [(str(i), str(i)) for i in range(1, 9)])
        with tempfile.TemporaryDirectory() as folder:
            paths = standard.export_model('P2CF-08', socket, folder)
            self.assertEqual(len(paths), 8)
            for path in paths:
                root = ET.parse(path).getroot()
                terminals = root.findall('./description/terminal')
                self.assertEqual(len(terminals), 2)
                self.assertEqual(len({t.get('uuid') for t in terminals}), 2)
                self.assertEqual({t.get('name') for t in terminals}, {path.stem.removeprefix('pin_')})
        picker = gui_core.part_catalog('standard_model', '')
        for model in (A8, A8E):
            self.assertIn(model, socket['compatible_timers'])
            self.assertIn(model, picker['omron']['h3cr'])
            self.assertNotIn('error', Api().part_options(model))
            spec = gen.STANDARD_DEVICES[model]
            pins = {pin for _, _, roles in standard.bindings(standard.configured_spec(spec)) for values in roles.values() for pin in values}
            self.assertEqual(pins, {str(i) for i in range(1, 9)})
            for mode in ('interval', 'flicker_on', 'flicker_off'):
                with self.assertRaisesRegex(ValueError, '動作構成'):
                    standard.configured_spec(spec, mode)

    def test_registration_of_both_timers_and_socket(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(qet_collection, 'user_collection_dir', return_value=Path(folder)):
            result = qet_collection.register_all_parts(models=[A8, A8E, 'P2CF-08'])
            self.assertTrue(result['ok'], result['errors'])
            self.assertEqual((result['models'], result['parts']), (3, 14))
            self.assertTrue(list(Path(folder).rglob('instant_contact_1.elmt')))


if __name__ == '__main__':
    unittest.main()
