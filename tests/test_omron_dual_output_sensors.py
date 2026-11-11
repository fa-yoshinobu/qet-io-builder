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


MODELS = ['E2E-X2C312 2M', 'E2E-X2B3D12 2M']


class OmronDualOutputSensorsTest(unittest.TestCase):
    def test_sio_configuration_must_be_explicit_for_iolink_model(self):
        spec = gen.STANDARD_DEVICES[MODELS[1]]
        with self.assertRaises(ValueError):
            standard.configured_spec(spec)
        self.assertEqual([c['id'] for c in spec['configuration_options']], ['sio_no_nc'])
        self.assertNotIn('default_configuration', spec)

    @requires_qet
    def test_four_leads_two_outputs_and_100ma_rating(self):
        for model, output in zip(MODELS, ['NPN', 'PNP']):
            spec = standard.configured_spec(gen.STANDARD_DEVICES[model], 'sio_no_nc' if output == 'PNP' else None)
            self.assertEqual(spec['wire_count'], 4)
            self.assertEqual(spec['operation'], 'NO+NC')
            self.assertEqual(spec['output_type'], output + ' open collector')
            self.assertEqual(spec['ratings']['load_current_ma_max'], 100)
            self.assertEqual(spec['ratings']['current_consumption_ma_max'], 20)
            self.assertEqual([(p['wire_color'], p['signal']) for p in spec['pins']],
                             [('茶', '+V'), ('青', '0V'), ('黒', 'NO'), ('白', 'NC')])
            part, template, labels = next(iter(standard.bindings(spec)))
            self.assertEqual(template, 'inductive_sensor_2output')
            root = standard.bind_definition(model, spec, part, template, labels)
            terminals = root.findall('./description/terminal')
            self.assertEqual({(float(t.get('x')), float(t.get('y'))): t.get('name') for t in terminals},
                             {(-10, -30): '茶 +V', (-10, 15): '青 0V', (13, -8): '黒 NO', (-32, -8): '白 NC'})
            self.assertEqual(len({t.get('uuid') for t in terminals}), 4)
            self.assertEqual(root.get('link_type'), 'simple')
            self.assertEqual(root.findall('./description/text'), [])
            for text in root.findall('./description/dynamic_text'):
                if text.findtext('info_name') in ['label', 'manufacturer_reference', 'comment']:
                    self.assertLess(float(text.get('y')) + 14, -8)

    @requires_qet
    def test_picker_and_model_registration(self):
        picker = gui_core.part_catalog('standard_model', '')
        for model in MODELS:
            self.assertIn(model, picker['omron']['e2e_next'])
            self.assertNotIn('error', Api().part_options(model))
        with tempfile.TemporaryDirectory() as folder, patch.object(qet_collection, 'user_collection_dir', return_value=Path(folder)):
            result = qet_collection.register_all_parts(models=MODELS)
            self.assertTrue(result['ok'], result['errors'])
            self.assertEqual((result['models'], result['parts']), (2, 2))


if __name__ == '__main__':
    unittest.main()
