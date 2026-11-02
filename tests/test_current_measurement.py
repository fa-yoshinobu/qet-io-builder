import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

import gen_io_page as gen
import gui_core
from renderers import standard
from tools import qet_collection
from webgui.api import Api, GROUP_NAMES


class CurrentMeasurementTest(unittest.TestCase):
    def test_meter_input_and_ct_ratios_match_without_inventing_terminal_numbers(self):
        spec = gen.STANDARD_DEVICES['YS-8NAA']
        self.assertFalse(spec['auxiliary_supply_required'])
        self.assertEqual(spec['meter_burden_va'], 1)
        choices = {o['id']: o for o in spec['configuration_options']}
        self.assertEqual(choices['direct_10a']['input_current_a'], 10)
        self.assertIsNone(choices['direct_10a']['ct_primary_a'])
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, '動作構成'):
                standard.export_model('YS-8NAA', spec, folder)
            ids = []
            for choice, option in choices.items():
                path, = standard.export_model('YS-8NAA', spec, folder, configuration=choice)
                root = ET.parse(path).getroot()
                ids.append(root.find('uuid').get('uuid'))
                terminals = {(float(t.get('x')), float(t.get('y'))): t.get('name')
                             for t in root.findall('./description/terminal')}
                self.assertEqual(terminals, {(-20, 0): '背面左', (20, 0): '背面右'})
                self.assertTrue(spec['terminal_labels_are_explanatory'])
                self.assertIn(option['label'], root.findtext("./names/name[@lang='ja']"))
                self.assertIn('A', [t.get('text') for t in root.findall('./description/text')])
                rating = root.findtext("./elementInformations/elementInformation[@name='comment']")
                self.assertEqual(rating, option['display_ratings'])
                self.assertEqual(len(root.findall('./description/terminal')), 2)
                for info in ('label', 'manufacturer_reference', 'comment'):
                    label = next(t for t in root.findall('./description/dynamic_text') if t.findtext('info_name') == info)
                    self.assertLess(float(label.get('y')) + 14, 0)
            # 同じ端子・標準図形でもCT比が違う構成は同一UUIDにしない。
            self.assertEqual(len(set(ids)), 3)

    def test_ct_primary_direction_is_distinct_from_secondary_wiring_posts(self):
        spec = gen.STANDARD_DEVICES['CW-5L']
        self.assertEqual(spec['physical_wiring_terminals'], 2)
        self.assertEqual(spec['schematic_connection_points'], 4)
        self.assertFalse(spec['primary_terminals_are_wiring_posts'])
        self.assertTrue(spec['secondary_open_circuit_prohibited'])
        self.assertFalse(spec['secondary_shorting_switch_included'])
        self.assertEqual((spec['rated_burden_va'], spec['accuracy_class']), (5, 1))
        meter_options = {o['id']: o for o in gen.STANDARD_DEVICES['YS-8NAA']['configuration_options']}
        ct_options = {o['id']: o for o in spec['configuration_options']}
        for pair in spec['compatible_meter_configurations']:
            meter, ct = meter_options[pair['configuration']], ct_options[pair['ct_configuration']]
            self.assertEqual(meter['input_current_a'], ct['secondary_current_a'])
            self.assertEqual(meter['scale_max_a'], ct['primary_current_a'])
            self.assertEqual(ct['primary_turns'], 1)
        for choice in ct_options:
            with tempfile.TemporaryDirectory() as folder:
                path, = standard.export_model('CW-5L', spec, folder, configuration=choice)
                root = ET.parse(path).getroot()
                self.assertEqual({(float(t.get('x')), float(t.get('y'))): t.get('name')
                                  for t in root.findall('./description/terminal')},
                                 {(0, -10): 'K', (0, 20): 'L', (10, 0): 'k', (10, 10): 'l'})
                for info in ('label', 'manufacturer_reference', 'comment'):
                    label = next(t for t in root.findall('./description/dynamic_text') if t.findtext('info_name') == info)
                    self.assertLess(float(label.get('y')) + 14, 0)

    def test_gui_and_all_configurations_register_separately(self):
        picker = gui_core.part_catalog('standard_model', '')
        for model, series in [('YS-8NAA', 'y_n'), ('CW-5L', 'cw')]:
            self.assertIn(model, picker['mitsubishi'][series])
            self.assertNotIn('error', Api().part_options(model))
        self.assertEqual(GROUP_NAMES['ammeter'], '電流計')
        self.assertEqual(GROUP_NAMES['current_transformer'], 'CT（計測用変流器）')
        with tempfile.TemporaryDirectory() as folder, patch.object(qet_collection, 'user_collection_dir', return_value=Path(folder)):
            result = qet_collection.register_all_parts(models=['YS-8NAA', 'CW-5L'])
            self.assertTrue(result['ok'], result['errors'])
            self.assertEqual((result['models'], result['configurations'], result['parts']), (2, 5, 5))
            base = Path(folder) / 'qet-io-builder/mitsubishi'
            meter_ids = [ET.parse(p).getroot().find('uuid').get('uuid') for p in (base / 'y_n/YS-8NAA').rglob('*.elmt')]
            self.assertEqual(len(set(meter_ids)), 3)
            self.assertTrue((base / 'cw/CW-5L/ratio_100_5/ct.elmt').exists())


if __name__ == '__main__':
    unittest.main()
