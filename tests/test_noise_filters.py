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


class NoiseFiltersTest(unittest.TestCase):
    def test_cosel_line_paths_do_not_inherit_tdk_output_numbers(self):
        models = [f'NAC-{amps:02}-472' for amps in (4, 6, 10)]
        for model, amps in zip(models, (4, 6, 10)):
            spec = gen.STANDARD_DEVICES[model]
            self.assertIn(model, gui_core.part_catalog('standard_model', '')['cosel']['nac'])
            self.assertNotIn('error', Api().part_options(model))
            self.assertEqual(spec['ratings']['rated_current_a'], amps)
            self.assertEqual(spec['ratings']['rated_voltage_vdc'], 250)
            self.assertEqual(spec['ratings']['leakage_current_ma_max']['at_250vac_60hz'], 1.0)
            self.assertEqual(spec['line_paths'], [['1', '3'], ['2', '4']])
            self.assertEqual(spec['temperature']['derating_start_c'], 55)
            self.assertEqual(spec['physical_wiring_terminals'], 6)
            self.assertEqual(sum(map(len, spec['terminal_groups'].values())), 6)
            with tempfile.TemporaryDirectory() as folder:
                paths = standard.export_model(model, spec, folder)
                root = ET.parse(paths[0]).getroot()
                terminals = root.findall('./description/terminal')
                self.assertEqual({(float(t.get('x')), float(t.get('y'))): t.get('name') for t in terminals},
                                 {(-10, -25): '1', (10, -25): '2', (-10, 25): '3', (10, 25): '4', (25, 0): 'PE/PE'})
                self.assertEqual(len({t.get('uuid') for t in terminals}), 5)
                self.assertEqual(root.findtext("./elementInformations/elementInformation[@name='manufacturer']"), 'COSEL')
        with tempfile.TemporaryDirectory() as folder, patch.object(qet_collection, 'user_collection_dir', return_value=Path(folder)):
            result = qet_collection.register_all_parts(models=models)
            self.assertTrue(result['ok'], result['errors'])
            self.assertEqual((result['models'], result['parts']), (3, 3))
            self.assertTrue((Path(folder) / 'qet-io-builder/cosel/nac/NAC-06-472/filter.elmt').is_file())

    def test_rsen_ratings_and_six_physical_terminals_are_preserved(self):
        self.assertEqual(GROUP_NAMES['noise_filter'], 'ノイズフィルタ')
        for amps in (3, 6, 10):
            model = f'RSEN-{2000 + amps}'
            with self.subTest(model=model), tempfile.TemporaryDirectory() as folder:
                spec = gen.STANDARD_DEVICES[model]
                self.assertIn(model, gui_core.part_catalog('standard_model', '')['tdk_lambda']['rsen'])
                self.assertNotIn('error', Api().part_options(model))
                self.assertEqual(spec['ratings']['rated_voltage_vac'], 250)
                self.assertEqual(spec['ratings']['rated_current_a'], amps)
                self.assertEqual(spec['line_paths'], [['1', '4'], ['2', '3']])
                self.assertEqual(spec['temperature']['derating_start_c'], 55)
                self.assertEqual(spec['electrical_nodes'], 5)
                self.assertEqual(spec['physical_wiring_terminals'], 6)
                self.assertEqual(sum(map(len, spec['terminal_groups'].values())), 6)
                paths = standard.export_model(model, spec, folder)
                root = ET.parse(paths[0]).getroot()
                pins = {(float(t.get('x')), float(t.get('y'))): t.get('name')
                        for t in root.findall('./description/terminal')}
                self.assertEqual(pins, {(-10, -25): '1', (10, -25): '2',
                                        (-10, 25): '4', (10, 25): '3', (25, 0): 'FG/FG'})
                infos = {i.get('name'): i.text for i in root.findall('./elementInformations/elementInformation')}
                self.assertEqual(infos['manufacturer'], 'TDK-Lambda')
                self.assertEqual(infos['designation'], '単相ノイズフィルタ')
                self.assertNotIn('Almeto', infos.values())
                texts = root.findall('./description/dynamic_text')
                for info in ('label', 'manufacturer_reference', 'comment'):
                    text = next(t for t in texts if t.findtext('info_name') == info)
                    # 右向きFGの配線経路 y=0 をタグ・形名・定格で塞がない。
                    self.assertLess(float(text.get('y')) + 14, 0)
                user_texts = [t.findtext('text') for t in texts if t.get('text_from') == 'UserText']
                self.assertEqual(sorted(user_texts), ['1', '2', '3', '4', 'FG/FG'])
                fg = next(t for t in texts if t.findtext('text') == 'FG/FG')
                self.assertLess(float(fg.get('y')) + 14, 0)

    def test_three_filters_register_in_the_manufacturer_series_folder(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(
                qet_collection, 'user_collection_dir', return_value=Path(folder)):
            result = qet_collection.register_all_parts(models=['RSEN-2003', 'RSEN-2006', 'RSEN-2010'])
            self.assertTrue(result['ok'], result['errors'])
            self.assertEqual((result['models'], result['parts']), (3, 3))
            self.assertTrue((Path(folder) / 'qet-io-builder/tdk_lambda/rsen/RSEN-2010/filter.elmt').exists())


if __name__ == '__main__':
    unittest.main()
