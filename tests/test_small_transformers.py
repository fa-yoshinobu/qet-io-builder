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


class SmallTransformersTest(unittest.TestCase):
    def test_all_taps_and_separate_windings_are_exported(self):
        self.assertEqual(GROUP_NAMES['transformer'], 'トランス')
        for va in (50, 100, 200):
            model = f'SC21-{va}'
            with self.subTest(model=model), tempfile.TemporaryDirectory() as folder:
                spec = gen.STANDARD_DEVICES[model]
                self.assertIn(model, gui_core.part_catalog('standard_model', '')['swallow']['sc21'])
                self.assertNotIn('error', Api().part_options(model))
                self.assertEqual(spec['ratings']['capacity_va'], va)
                self.assertEqual(spec['ratings']['primary_vac'], [200, 220])
                self.assertEqual(spec['ratings']['secondary_vac'], [100, 110])
                self.assertTrue(spec['galvanic_isolation'])
                self.assertFalse(spec['electrostatic_shield'])
                self.assertEqual(spec['physical_wiring_terminals'], 6)
                root = ET.parse(standard.export_model(model, spec, folder)[0]).getroot()
                pins = root.findall('./description/terminal')
                self.assertEqual(len(pins), 6)
                self.assertEqual(len({t.get('uuid') for t in pins}), 6)
                actual = {(float(t.get('x')), float(t.get('y'))): t.get('name') for t in pins}
                self.assertEqual(actual, {(0, -20): '0', (20, -20): '200V', (40, -20): '220V',
                                          (0, 10): '0', (20, 10): '100V', (40, 10): '110V'})
                zeros = [t for t in pins if t.get('name') == '0']
                self.assertEqual(len(zeros), 2)
                self.assertNotEqual(zeros[0].get('uuid'), zeros[1].get('uuid'))
                texts = [t for t in root.findall('./description/dynamic_text')
                         if t.get('text_from') == 'UserText']
                self.assertEqual(len(texts), 6)
                self.assertTrue(all(t.get('rotation') == '270' for t in texts))
                self.assertEqual({float(t.get('y')) for t in texts}, {-26, 38})
                self.assertFalse({'230V', '400V', '12V', '24V'} & {t.findtext('text') for t in texts})

    def test_only_the_known_duplicate_terminal_is_removed(self):
        record = standard.catalog()['transformer_1p_tapped']
        source = ET.parse(standard.collection_root() / record['path']).getroot()
        duplicate_id, = record['duplicate_terminal_uuids']
        duplicate = next(t for t in source.findall('./description/terminal') if t.get('uuid') == duplicate_id)
        self.assertEqual((duplicate.get('x'), duplicate.get('y'), duplicate.get('orientation')), ('20', '10', 's'))
        self.assertEqual(sum(t.get('x') == '20' and t.get('y') == '10'
                             for t in source.findall('./description/terminal')), 2)
        spec = gen.STANDARD_DEVICES['SC21-100']
        part, template, labels = next(standard.bindings(spec))
        root = standard.bind_definition('SC21-100', spec, part, template, labels)
        geometry = lambda r: [ET.tostring(t) for t in r.find('description')
                              if t.tag not in ('terminal', 'text', 'dynamic_text')]
        self.assertEqual(geometry(root), geometry(source))
        self.assertEqual(sum(t.get('x') == '20' and t.get('y') == '10'
                             for t in root.findall('./description/terminal')), 1)

    def test_registration(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(
                qet_collection, 'user_collection_dir', return_value=Path(folder)):
            result = qet_collection.register_all_parts(models=['SC21-50', 'SC21-100', 'SC21-200'])
            self.assertTrue(result['ok'], result['errors'])
            self.assertEqual((result['models'], result['parts']), (3, 3))
            self.assertTrue((Path(folder) / 'qet-io-builder/swallow/sc21/SC21-100/transformer.elmt').exists())


if __name__ == '__main__':
    unittest.main()
