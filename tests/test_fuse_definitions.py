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


class FuseDefinitionsTest(unittest.TestCase):
    @requires_qet
    def test_current_and_response_are_part_of_the_selected_fuse(self):
        catalog = gui_core.part_catalog('standard_model', '')
        for series, response in [(217, 'fast_acting'), (218, 'time_lag')]:
            entries = catalog['littelfuse'][f'fuse_{series}']
            self.assertEqual(len(entries), 6)
            for code, current, breaking in [('.500', .5, 35), ('001.', 1, 35),
                    ('002.', 2, 35), ('3.15', 3.15, 35), ('005.', 5, 50), ('06.3', 6.3, 63)]:
                model = f'0{series}{code}MXP'
                with self.subTest(model=model), tempfile.TemporaryDirectory() as folder:
                    self.assertIn(model, entries)
                    self.assertNotIn('error', Api().part_options(model))
                    spec = gen.STANDARD_DEVICES[model]
                    self.assertEqual(spec['device_type'], 'fuse')
                    self.assertEqual(spec['response_time'], response)
                    self.assertEqual(spec['ratings']['rated_current_a'], current)
                    self.assertEqual(spec['ratings']['rated_voltage_vac'], 250)
                    self.assertEqual(spec['ratings']['interrupting_current_a_at_250vac'], breaking)
                    self.assertEqual(spec['ratings']['nominal_size_mm'], [5, 20])
                    self.assertNotIn('holder_rated_current_a', spec['ratings'])
                    self.assertFalse(spec['fuse_selection_required'])
                    paths = standard.export_model(model, spec, folder)
                    self.assertEqual(len(paths), 1)
                    root = ET.parse(paths[0]).getroot()
                    self.assertEqual({t.get('name') for t in root.findall('./description/terminal')},
                                     {'端部1', '端部2'})
                    comment = root.findtext("./elementInformations/elementInformation[@name='comment']")
                    self.assertIn('速断' if series == 217 else 'タイムラグ', comment)

    @requires_qet
    def test_holder_iec_rating_and_power_loss_are_not_fuse_capacity(self):
        holder = gen.STANDARD_DEVICES['2002-1611']
        self.assertEqual(holder['ratings']['holder_rated_current_a'], 6.3)
        self.assertEqual(holder['ratings']['holder_rated_voltage_v'], 250)
        self.assertEqual(holder['ratings']['max_fuse_power_loss_w'], 1.6)
        self.assertIsNone(holder['ratings']['selected_fuse_current_a'])
        self.assertTrue(holder['fuse_selection_required'])
        self.assertFalse(holder['fuse_included'])
        # 呼称寸法が同じでも、許容損失を超えるヒューズを適合扱いにしない。
        high_loss = gen.STANDARD_DEVICES['02173.15MXP']
        self.assertGreater(high_loss['ratings']['max_power_dissipation_w_at_1_5_in'],
                           holder['ratings']['max_fuse_power_loss_w'])
        self.assertFalse(holder.get('compatible_fuses'))
        with tempfile.TemporaryDirectory() as folder:
            root = ET.parse(standard.export_model('2002-1611', holder, folder)[0]).getroot()
            self.assertEqual(len(root.findall('./description/terminal')), 2)
            self.assertIn('ヒューズ未選択', root.findtext(
                "./elementInformations/elementInformation[@name='comment']"))

    @requires_qet
    def test_bulk_registration_includes_bodies_and_holder(self):
        catalog = gui_core.part_catalog('standard_model', '')
        models = [m for entries in catalog['littelfuse'].values() for m in entries] + ['2002-1611']
        with tempfile.TemporaryDirectory() as folder, patch.object(
                qet_collection, 'user_collection_dir', return_value=Path(folder)):
            result = qet_collection.register_all_parts(models=models)
            self.assertTrue(result['ok'], result['errors'])
            self.assertEqual(result['models'], 13)
            self.assertEqual(result['parts'], 13)


if __name__ == '__main__':
    unittest.main()
