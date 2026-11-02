import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET

from tools import qet_collection
from webgui.api import Api


class QetRegistrationTest(unittest.TestCase):
    @unittest.skipUnless(os.name == 'nt', 'WindowsのQET設定を確認するテスト')
    def test_windows_custom_and_default_collection_paths(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, APPDATA=folder):
            custom = Path(folder) / 'custom'
            custom.mkdir()
            with patch('winreg.QueryValueEx', return_value=(str(custom), 1)):
                self.assertEqual(qet_collection.user_collection_dir(), custom)
            with patch('winreg.QueryValueEx', return_value=('default', 1)):
                modern = Path(folder) / 'QElectroTech' / 'QElectroTech' / 'elements'
                legacy = Path(folder) / 'qet' / 'elements'
                self.assertEqual(qet_collection.user_collection_dir(), modern)
                legacy.mkdir(parents=True)
                self.assertEqual(qet_collection.user_collection_dir(), legacy)
                modern.mkdir(parents=True)
                self.assertEqual(qet_collection.user_collection_dir(), modern)

    def test_idec_registration_is_repeatable_without_a_folder_dialog(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(qet_collection, 'user_collection_dir', return_value=Path(folder)):
            existing = Path(folder) / 'my_part.elmt'
            existing.write_bytes(b'user data')
            api = Api()
            with patch.object(api, '_ask', side_effect=AssertionError('登録で保存先を尋ねない')):
                result = api.register_part('HW1B-M110R')
                self.assertNotIn('error', result)
                paths = [Path(p) for p in result['paths']]
                self.assertTrue(paths)
                before = [p.read_bytes() for p in paths]
                second = api.register_part('HW1B-M110R')
                self.assertNotIn('error', second)
                self.assertEqual(before, [p.read_bytes() for p in paths])
            for path in paths:
                self.assertIn(Path(folder) / 'qet-io-builder' / 'idec' / 'hw', path.parents)
                self.assertEqual(ET.parse(path).getroot().tag, 'definition')
            self.assertEqual(existing.read_bytes(), b'user data')
            self.assertEqual(ET.parse(Path(folder) / 'qet-io-builder' / 'qet_directory').getroot().tag, 'qet-directory')

    def test_power_supply_uses_the_same_registration_flow(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(qet_collection, 'user_collection_dir', return_value=Path(folder)):
            result = Api().register_part('S8VK-G01524')
            self.assertNotIn('error', result)
            self.assertTrue(all(Path(p).exists() for p in result['paths']))

    def test_unsupported_model_does_not_create_a_collection(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(qet_collection, 'user_collection_dir', return_value=Path(folder)):
            self.assertIn('error', Api().register_part('NOT-A-PART'))
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_bulk_registration_covers_all_catalog_models_and_configurations(self):
        import gen_io_page as gen
        with tempfile.TemporaryDirectory() as folder, patch.object(qet_collection, 'user_collection_dir', return_value=Path(folder)):
            result = Api().register_all_parts()
            self.assertEqual(result.get('errors'), [])
            self.assertTrue(result['ok'])
            self.assertEqual(result['models'], len(qet_collection._identities()))
            definitions = gen.read_unit_definitions()
            expected = sum(max(1, len(spec.get('auxiliary_options', []))) * max(1, len(spec.get('configuration_options', [])))
                           for group in ('standard_device', 'power_supply') for spec in definitions[group].values())
            self.assertEqual(result['configurations'], expected)
            paths = list(Path(folder).rglob('*.elmt'))
            self.assertEqual(len(paths), result['parts'])
            self.assertTrue(paths)
            self.assertTrue(all(ET.parse(p).getroot().tag == 'definition' for p in paths))

    def test_bulk_registration_reports_a_failure_and_continues(self):
        import gui_core as core
        export = core.export_part
        def write(model, *args, **kwargs):
            if model == 'HW1B-M110R':
                raise PermissionError('書込拒否')
            return export(model, *args, **kwargs)
        with tempfile.TemporaryDirectory() as folder, patch.object(qet_collection, 'user_collection_dir', return_value=Path(folder)), patch.object(core, 'export_part', side_effect=write):
            result = qet_collection.register_all_parts(['HW1B-M110R', 'S8VK-G01524'])
            self.assertFalse(result['ok'])
            self.assertEqual(result['models'], 1)
            self.assertEqual(result['errors'][0]['model'], 'HW1B-M110R')
            self.assertTrue(list(Path(folder).rglob('unit.elmt')))
