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


MODELS = ['AR22F0R-10G', 'AR22F0R-01R', 'AR22F0R-11G', 'AR22F0L-11E3G',
          'AR22PR-211B', 'AR22V0R-01R', 'DR22D0L-E3G']


class FujiAr22Dr22Test(unittest.TestCase):
    def test_contact_numbers_are_manufacturer_block_markings(self):
        for model in MODELS:
            spec = gen.STANDARD_DEVICES[model]
            with self.subTest(model=model), tempfile.TemporaryDirectory() as folder:
                paths = standard.export_model(model, spec, folder)
                for path in paths:
                    root = ET.parse(path).getroot()
                    if root.get('link_type') == 'master':
                        fields = {t.findtext('info_name'): float(t.get('y')) for t in root.findall('./description/dynamic_text') if t.findtext('info_name')}
                        self.assertLess(fields['manufacturer_reference'], fields['comment'])
                        self.assertLess(fields['comment'], fields['label'])
                    pins = {t.get('name') for t in root.findall('./description/terminal')}
                    if path.stem == 'lamp':
                        self.assertEqual(pins, {'X1', 'X2'})
                        texts = [t.findtext('text') for t in root.findall('./description/dynamic_text')]
                        self.assertIn('X1 + (DC)', texts)
                        self.assertIn('X2 − (DC)', texts)
                        self.assertEqual(root.get('link_type'), 'simple')
                        self.assertEqual(spec['lamp']['rated_voltage'], 'AC/DC24V')
                    elif path.stem == 'nc' or model in ('AR22F0R-01R', 'AR22V0R-01R'):
                        self.assertEqual(pins, {'1', '2'})
                    else:
                        self.assertEqual(pins, {'3', '4'})

    def test_mechanical_operation_and_isolated_lamp(self):
        s = gen.STANDARD_DEVICES['AR22PR-211B']
        self.assertEqual(s['position_contact_table'], {'1': {'no': 'open', 'nc': 'closed'}, '2': {'no': 'closed', 'nc': 'open'}})
        self.assertEqual(s['operation'], 'maintained_2position_90deg')
        s = gen.STANDARD_DEVICES['AR22F0L-11E3G']
        self.assertEqual(s['mechanically_linked'], ['pushbutton', 'nc'])
        self.assertEqual(len(list(standard.bindings(s))), 3)
        s = gen.STANDARD_DEVICES['AR22V0R-01R']
        self.assertEqual(s['operation'], 'push_lock_turn_reset')
        self.assertFalse(s['safety_function_verified'])
        part, template, labels = next(iter(standard.bindings(s)))
        self.assertEqual(template, 'emergency_turn_reset_nc')
        root = standard.bind_definition('AR22V0R-01R', s, part, template, labels)
        self.assertEqual(root.get('link_type'), 'master')
        self.assertEqual(root.findtext("./kindInformations/kindInformation[@name='type']"), 'commutator')

    def test_picker_options_and_registration(self):
        picker = gui_core.part_catalog('standard_model', '')
        for model in MODELS:
            self.assertIn(model, picker['fuji']['dr22' if model.startswith('DR') else 'ar22'])
            self.assertNotIn('error', Api().part_options(model))
        with tempfile.TemporaryDirectory() as folder, patch.object(qet_collection, 'user_collection_dir', return_value=Path(folder)):
            result = qet_collection.register_all_parts(models=MODELS)
            self.assertTrue(result['ok'], result['errors'])
            self.assertEqual((result['models'], result['parts']), (7, 11))
            self.assertTrue(list(Path(folder).rglob('emergency.elmt')))


if __name__ == '__main__':
    unittest.main()
