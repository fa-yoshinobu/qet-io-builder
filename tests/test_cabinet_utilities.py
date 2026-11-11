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
from webgui.api import Api, GROUP_NAMES


LIGHTS = {'LF1B-NA3P-2THWW2-1M': (134, 1.5),
          'LF1B-NC3P-2THWW2-1M': (330, 4.4),
          'LF1B-ND3P-2THWW2-1M': (580, 8.7)}


class CabinetUtilitiesTest(unittest.TestCase):
    @requires_qet
    def test_lighting_is_separate_from_indicator_and_has_the_verified_polarity(self):
        self.assertEqual(GROUP_NAMES['lighting'], '盤内LED照明')
        self.assertNotEqual(GROUP_NAMES['lighting'], GROUP_NAMES['lamp'])
        for model, (length, power) in LIGHTS.items():
            with self.subTest(model=model), tempfile.TemporaryDirectory() as folder:
                spec = gen.STANDARD_DEVICES[model]
                self.assertIn(model, gui_core.part_catalog('standard_model', '')['idec']['lf1b_n'])
                self.assertNotIn('error', Api().part_options(model))
                self.assertEqual(spec['device_type'], 'lighting')
                self.assertEqual(spec['light_source'], 'LED')
                self.assertEqual(spec['dimensions_mm']['length'], length)
                self.assertEqual(spec['ratings']['power_w_typ'], power)
                self.assertEqual(spec['ratings']['supply_vdc'], 24)
                self.assertFalse(spec['built_in_switch'])
                self.assertFalse(spec['protective_earth_terminal'])
                paths = standard.export_model(model, spec, folder)
                self.assertEqual(len(paths), 1)
                root = ET.parse(paths[0]).getroot()
                pins = {(float(t.get('x')), float(t.get('y'))): t.get('name')
                        for t in root.findall('./description/terminal')}
                self.assertEqual(pins, {(0, -20): '茶 (+)', (0, 20): '青 (-)'})
                self.assertIn('盤内LED照明', root.findtext('./names/name[@lang="ja"]'))

    @requires_qet
    def test_outlet_neutral_is_not_protective_earth_and_feedthrough_is_common(self):
        for model, outlets in [('WK3001W', 1), ('WK3004W', 2)]:
            with self.subTest(model=model), tempfile.TemporaryDirectory() as folder:
                spec = gen.STANDARD_DEVICES[model]
                self.assertIn(model, gui_core.part_catalog('standard_model', '')['panasonic']['wk'])
                self.assertNotIn('error', Api().part_options(model))
                self.assertEqual(spec['ratings'], {'rated_voltage_vac': 125, 'rated_current_a': 15})
                self.assertEqual(spec['receptacles'], outlets)
                self.assertEqual(spec['electrical_nodes'], 3)
                self.assertEqual(spec['physical_wiring_terminals'], 3 if outlets == 1 else 5)
                adapter = spec['mounting_adapters'][0]
                self.assertEqual(adapter['model'], 'S-21-3C')
                self.assertFalse(adapter['included'])
                self.assertEqual(adapter['electrical_connections'], 0)
                paths = standard.export_model(model, spec, folder)
                self.assertEqual(len(paths), 1)
                root = ET.parse(paths[0]).getroot()
                pins = {(float(t.get('x')), float(t.get('y'))): t.get('name')
                        for t in root.findall('./description/terminal')}
                self.assertEqual(pins, {(-6, -17): '電圧側' if outlets == 1 else '電圧側1/電圧側2',
                                       (6, -17): 'W' if outlets == 1 else 'W1/W2', (0, 17): '接地'})
                # 並列の巻締端子を一つの電位へまとめても、物理端子の記録を落とさない。
                self.assertEqual(sum(map(len, spec['terminal_groups'].values())), spec['physical_wiring_terminals'])

    @requires_qet
    def test_all_five_parts_register_in_manufacturer_series_folders(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(
                qet_collection, 'user_collection_dir', return_value=Path(folder)):
            result = qet_collection.register_all_parts(models=list(LIGHTS) + ['WK3001W', 'WK3004W'])
            self.assertTrue(result['ok'], result['errors'])
            self.assertEqual((result['models'], result['parts']), (5, 5))
            self.assertTrue((Path(folder) / 'qet-io-builder/panasonic/wk/WK3004W/outlet.elmt').exists())


if __name__ == '__main__':
    unittest.main()
