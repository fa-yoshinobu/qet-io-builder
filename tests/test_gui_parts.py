import unittest
import tempfile
from xml.etree import ElementTree as ET
import gui_core as gui


class PartCatalogTest(unittest.TestCase):
    def test_unknown_kind_is_empty_and_communication_never_lists_other_devices(self):
        self.assertEqual(gui.part_catalog('model', 'unknown'), {})
        self.assertEqual(gui.part_catalog('unknown', 'qbody'), {})
        self.assertEqual(set(gui.part_catalog('model', 'fxcomm')), {'mitsubishi'})
        self.assertEqual(set(gui.part_catalog('model', 'fxcomm')['mitsubishi']), {'iq_f'})
        self.assertEqual(set(gui.part_catalog('model', 'power')['mitsubishi']), {'iq_f'})

    def test_power_and_base_models_match_the_selected_plc_series(self):
        for kind, series in [('qbody', 'q'), ('iqrbody', 'iq_r')]:
            for key in ('power_model', 'base_model'):
                catalog = gui.part_catalog(key, kind)['mitsubishi']
                self.assertEqual(set(catalog), {'iq_r', 'mx_r'} if kind == 'iqrbody' else {series})
                if kind == 'iqrbody':
                    self.assertEqual(catalog['mx_r'], catalog['iq_r'])
        self.assertNotIn('Q65B', gui.part_catalog('base_model', 'qbody')['mitsubishi']['q'])

    def test_power_supply_is_selectable_and_exports_the_actual_part(self):
        catalog = gui.part_catalog('standard_model', '')
        self.assertIn('S8VK-G01524', catalog['omron']['s8vk_g'])
        for series in ('s8vk_g', 's8vk_s', 's8vk_x'):
            self.assertIn(series, gui.SERIES_NAMES)
        with tempfile.TemporaryDirectory() as folder:
            paths = gui.export_part('S8VK-G01524', folder)
            definition = ET.parse(paths[0]).getroot()
            self.assertEqual(definition.tag, 'definition')
            self.assertIn('L', [t.get('name') for t in definition.findall('./description/terminal')])

    def test_series_and_page_kind_filter(self):
        catalog = gui.part_catalog('model', 'qanalog')
        self.assertEqual(set(catalog), {'mitsubishi'})
        self.assertEqual(set(catalog['mitsubishi']), {'q'})
        self.assertIn('Q64AD', catalog['mitsubishi']['q'])
        self.assertNotIn('QX41', catalog['mitsubishi']['q'])

    def test_input_output_and_communication_fields(self):
        inputs = gui.part_catalog('model', 'input')['mitsubishi']['q']
        outputs = gui.part_catalog('model', 'output')['mitsubishi']['q']
        communication = gui.part_catalog('left_model', 'qcomm')['mitsubishi']['q']
        self.assertIn('QX41', inputs)
        self.assertNotIn('QY41P', inputs)
        self.assertIn('QY41P', outputs)
        self.assertIn('QJ61BT11N', communication)
        self.assertNotIn('QX41', communication)

    def test_configuration_modules_are_limited_to_series(self):
        q = gui.part_catalog('modules', 'qbody')['mitsubishi']
        r = gui.part_catalog('modules', 'iqrbody')['mitsubishi']
        self.assertEqual(set(q), {'q'})
        self.assertEqual(set(r), {'iq_r', 'mx_r'})
        self.assertTrue(set(r['mx_r']) <= set(r['iq_r']))
        self.assertIn('RX41C4', r['mx_r'])
        self.assertIn('QX41', q['q'])
        self.assertIn('QJ61BT11N', q['q'])
        self.assertNotIn('Q03UDVCPU', q['q'])
        self.assertIn('RX41C4', r['iq_r'])
        self.assertIn('RJ71C24', r['iq_r'])
        self.assertIn('RJ71GF11-T2', gui.part_catalog('left_model', 'iqrcomm')['mitsubishi']['iq_r'])
        self.assertIn('FX5-485ADP', gui.part_catalog('modules', 'fx5body')['mitsubishi']['iq_f'])
        self.assertIn('FX5-422-BD-GOT', gui.part_catalog('left_model', 'fxcomm')['mitsubishi']['iq_f'])

if __name__ == '__main__':
    unittest.main()
