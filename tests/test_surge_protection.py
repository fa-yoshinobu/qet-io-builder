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


MODELS = ['LT-C12G801W', 'LT-C14G801W', 'VAL-SEC-T2-1S-350', 'VAL-SEC-T2-1S-350-FM']


class SurgeProtectionTest(unittest.TestCase):
    def test_device_terminals_and_optional_alarm_are_not_confused(self):
        picker = gui_core.part_catalog('standard_model', '')
        self.assertEqual(GROUP_NAMES['surge_protection'], 'サージ保護器（SPD）')
        for model in MODELS:
            with self.subTest(model=model), tempfile.TemporaryDirectory() as folder:
                spec = gen.STANDARD_DEVICES[model]
                maker, series = ('otowa', 'lt_c') if model.startswith('LT-') else ('phoenix_contact', 'val_sec')
                self.assertIn(model, picker[maker][series])
                self.assertNotIn('error', Api().part_options(model))
                self.assertEqual(spec['connection'], 'parallel')
                paths = standard.export_model(model, spec, folder)
                fm = model.endswith('-FM')
                self.assertEqual(len(paths), 2 if fm else 1)
                root = ET.parse(paths[0]).getroot()
                if maker == 'phoenix_contact':
                    self.assertIn('gG315A以下で25kA', root.findtext('informations'))
                    self.assertIn('gG200A以下で50kA', root.findtext('informations'))
                pins = {(float(t.get('x')), float(t.get('y'))): t.get('name')
                        for t in root.findall('./description/terminal')}
                self.assertEqual(pins, {(-11, -21): 'L3' if maker == 'otowa' else 'N',
                                        (10, -21): 'L1', (11, 17): 'E' if maker == 'otowa' else 'PE'})
                self.assertEqual(spec['remote_indication']['present'], fm)
                self.assertEqual(spec['physical_wiring_terminals'], 6 if fm else 3)
                if fm:
                    contact = ET.parse(paths[1]).getroot()
                    self.assertEqual(contact.get('link_type'), 'simple')
                    self.assertIsNone(contact.find('kindInformations'))
                    contacts = {(float(t.get('x')), float(t.get('y'))): t.get('name')
                                for t in contact.findall('./description/terminal')}
                    self.assertEqual(contacts, {(0, 20): '11', (0, -20): '14', (-20, -20): '12'})
                    rating = contact.findtext("./elementInformations/elementInformation[@name='comment']")
                    self.assertEqual(rating, 'FM 警報接点 / AC250V 1A max')
                    self.assertNotIn('350V', rating)
                    self.assertIn('350V', root.findtext("./elementInformations/elementInformation[@name='comment']"))
                    # コイルを仮設したり、健全時の接点状態を推測して確定しない。
                    self.assertNotIn('coil', [p.stem for p in paths])
                    self.assertEqual(spec['remote_indication']['normal_service_state'], '未確認')

    def test_ratings_protective_paths_and_backup_limits(self):
        low, high = [gen.STANDARD_DEVICES[m] for m in MODELS[:2]]
        self.assertEqual(low['ratings']['max_continuous_voltage_vac'], {'L-E': 275, 'L-L': 275})
        self.assertEqual(high['ratings']['max_continuous_voltage_vac'], {'L-E': 280, 'L-L': 480})
        for spec in (low, high):
            self.assertEqual(spec['ratings']['maximum_discharge_current_a'], 5000)
            self.assertEqual(spec['external_backup_protection']['status'], '未確認')
        for model, number in zip(MODELS[2:], ('2905341', '2905333')):
            spec = gen.STANDARD_DEVICES[model]
            self.assertEqual(spec['article_number'], number)
            self.assertEqual(spec['internal_connections'], [])
            self.assertEqual(spec['protective_paths'], [
                {'terminals': ['L1', 'N'], 'element': 'varistor'},
                {'terminals': ['N', 'PE'], 'element': 'gas_discharge'}])
            self.assertEqual(spec['ratings']['max_continuous_voltage_vac']['N-PE'], 264)
            self.assertEqual(spec['external_backup_protection']['branch_max_gg_a'], 315)
            self.assertEqual(spec['external_backup_protection']['v_through_max_gg_a'], [40, 63])
            self.assertEqual(spec['external_backup_protection']['short_circuit_conditions'], [
                {'backup_fuse_type': 'gG', 'backup_fuse_max_a': 315, 'short_circuit_rating_ka': 25},
                {'backup_fuse_type': 'gG', 'backup_fuse_max_a': 200, 'short_circuit_rating_ka': 50}])

    def test_registration_has_four_models_and_five_parts(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(qet_collection, 'user_collection_dir', return_value=Path(folder)):
            result = qet_collection.register_all_parts(models=MODELS)
            self.assertTrue(result['ok'], result['errors'])
            self.assertEqual((result['models'], result['parts']), (4, 5))
            self.assertTrue((Path(folder) / 'qet-io-builder/phoenix_contact/val_sec/VAL-SEC-T2-1S-350-FM/alarm_contact_1.elmt').exists())


if __name__ == '__main__':
    unittest.main()
