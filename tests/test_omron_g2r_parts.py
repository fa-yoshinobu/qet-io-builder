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


G2R = {f'G2R-{p}-{v} DC24': (p, v) for p in (1, 2) for v in ('S', 'SN', 'SND')}
G2RV = [f'G2RV-ST{s} DC24' for s in ('500', '501', '700', '701')]
SOCKETS = ['P2RF-05-PU', 'P2RF-08-PU', 'P2RFZ-05', 'P2RFZ-08', 'P2RFZ-05-E', 'P2RFZ-08-E']


class OmronG2rPartsTest(unittest.TestCase):
    def test_g2r_actual_body_pin_numbers_and_dc_polarity(self):
        for model, (poles, version) in G2R.items():
            with self.subTest(model=model), tempfile.TemporaryDirectory() as folder:
                spec = gen.STANDARD_DEVICES[model]
                self.assertIn(model, gui_core.part_catalog('standard_model', '')['omron']['g2r_s'])
                self.assertNotIn('error', Api().part_options(model))
                self.assertEqual(spec['coil']['rated_voltage'], 'DC24V')
                self.assertEqual(spec['coil']['surge'], 'diode' if version == 'SND' else 'none')
                roots = {p.stem: ET.parse(p).getroot() for p in standard.export_model(model, spec, folder)}
                self.assertEqual(len(roots), poles + 1)
                self.assertEqual(roots['coil'].get('link_type'), 'master')
                positive = '5' if poles == 1 else '8'
                self.assertEqual({t.get('name') for t in roots['coil'].findall('./description/terminal')}, {'1', positive})
                texts = [t.findtext('text') for t in roots['coil'].findall('./description/dynamic_text')]
                if version == 'S':
                    self.assertEqual(spec['coil']['polarity'], 'none')
                    self.assertNotIn('1 (-)', texts)
                else:
                    self.assertIn('1 (-)', texts)
                    self.assertIn(positive + ' (+)', texts)
                expected = [('4', '3', '2')] if poles == 1 else [('3', '4', '2'), ('6', '5', '7')]
                for i, (common, no, nc) in enumerate(expected, 1):
                    root = roots[f'contact_{i}']
                    actual = {(float(t.get('x')), float(t.get('y'))): t.get('name')
                              for t in root.findall('./description/terminal')}
                    self.assertEqual(actual, {(0, 20): common, (0, -20): no, (-20, -20): nc})

    def test_g2rv_input_is_not_the_internal_relay_coil_rating(self):
        for model in G2RV:
            with self.subTest(model=model), tempfile.TemporaryDirectory() as folder:
                spec = gen.STANDARD_DEVICES[model]
                self.assertIn(model, gui_core.part_catalog('standard_model', '')['omron']['g2rv_st'])
                self.assertNotIn('error', Api().part_options(model))
                self.assertTrue(spec['module_includes_socket'])
                self.assertEqual(spec['terminal_numbering'], 'relay_module_external_terminals')
                self.assertEqual(spec['ratings']['input_vdc'], 24)
                self.assertEqual(spec['replacement_relay']['coil_vdc'], 21)
                self.assertEqual(spec['manual_test_lever'], '501' in model or '701' in model)
                roots = {p.stem: ET.parse(p).getroot() for p in standard.export_model(model, spec, folder)}
                self.assertEqual(len(roots), 2)
                contact = roots['contact_1']
                actual = {(float(t.get('x')), float(t.get('y'))): t.get('name')
                          for t in contact.findall('./description/terminal')}
                self.assertEqual(actual, {(0, 20): '11', (0, -20): '14', (-20, -20): '12'})
                texts = [t.findtext('text') for t in roots['coil'].findall('./description/dynamic_text')]
                self.assertIn('A1 (+)', texts)
                self.assertIn('A2 (-)', texts)

    def test_sockets_match_body_pins_and_do_not_invent_iec_marking(self):
        for model in SOCKETS:
            with self.subTest(model=model), tempfile.TemporaryDirectory() as folder:
                spec = gen.STANDARD_DEVICES[model]
                self.assertIn(model, gui_core.part_catalog('standard_model', '')['omron']['p2rf'])
                self.assertNotIn('error', Api().part_options(model))
                expected = ({'1': 'A2', '2': '12', '3': '14', '4': '11', '5': 'A1'} if '05' in model else
                            {'1': 'A2', '2': '12', '3': '11', '4': '14', '5': '24', '6': '21', '7': '22', '8': 'A1'})
                actual = {t['relay_pin']: t['socket_marking'] for t in spec['terminal_map']}
                self.assertEqual(actual, {p: f'{iec}({p})' if model.endswith('-PU') else
                                         f'{p}({iec})' if model.endswith('-E') else p for p, iec in expected.items()})
                paths = standard.export_model(model, spec, folder)
                self.assertEqual(len(paths), len(expected))
                for path in paths:
                    root = ET.parse(path).getroot()
                    pin = path.stem.removeprefix('pin_')
                    self.assertEqual({t.get('name') for t in root.findall('./description/terminal')}, {pin, actual[pin]})
                for relay in spec['compatible_relays']:
                    pins = {p for _, _, roles in standard.bindings(gen.STANDARD_DEVICES[relay])
                            for names in roles.values() for p in names}
                    self.assertEqual(pins, set(expected))

    def test_register_all_sixteen_models(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(
                qet_collection, 'user_collection_dir', return_value=Path(folder)):
            result = qet_collection.register_all_parts(models=list(G2R) + G2RV + SOCKETS)
            self.assertTrue(result['ok'], result['errors'])
            self.assertEqual((result['models'], result['parts']), (16, 62))


if __name__ == '__main__':
    unittest.main()
