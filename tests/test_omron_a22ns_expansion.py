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


MODELS = [f'A22NS-{position}BM-NBA-{terminal}{code}-NN'
          for position, code in [('2', '102'), ('3', '101')]
          for terminal in ['G', 'P']]


class OmronA22nsExpansionTest(unittest.TestCase):
    def test_two_position_no_nc_follow_position_one_and_three(self):
        for terminal in ['G', 'P']:
            model = f'A22NS-2BM-NBA-{terminal}102-NN'
            spec = gen.STANDARD_DEVICES[model]
            self.assertEqual(spec['position_contact_table'], {
                '1': {'no': 'open', 'nc': 'closed'},
                '2': {'no': 'closed', 'nc': 'open'}})
            self.assertEqual(spec['contact_block_positions'], {'selector': '1', 'nc': '3'})
            with tempfile.TemporaryDirectory() as folder:
                roots = {p.stem: ET.parse(p).getroot() for p in standard.export_model(model, spec, folder)}
                self.assertEqual(roots['selector'].get('link_type'), 'master')
                self.assertEqual(roots['nc'].get('link_type'), 'slave')
                self.assertEqual({t.get('name') for t in roots['selector'].findall('./description/terminal')}, {'3', '4'})
                self.assertEqual({t.get('name') for t in roots['nc'].findall('./description/terminal')}, {'1', '2'})
                self.assertEqual({t.get('text') for t in roots['selector'].findall('./description/text')}, {'1', '2'})

    def test_three_position_center_off_has_four_independent_terminals(self):
        all_ids = []
        for terminal in ['G', 'P']:
            model = f'A22NS-3BM-NBA-{terminal}101-NN'
            spec = gen.STANDARD_DEVICES[model]
            self.assertEqual(spec['operation'], 'maintained')
            self.assertEqual(spec['operation_angle_deg'], 45)
            self.assertEqual(spec['contact_block_positions'], {'contact_1': '1', 'contact_2': '3'})
            self.assertEqual(spec['position_contact_table'], {
                '1': {'contact_1': 'closed', 'contact_2': 'open'},
                '0': {'contact_1': 'open', 'contact_2': 'open'},
                '2': {'contact_1': 'open', 'contact_2': 'closed'}})
            part, template, labels = next(iter(standard.bindings(spec)))
            root = standard.bind_definition(model, spec, part, template, labels)
            terminals = root.findall('./description/terminal')
            self.assertEqual({(float(t.get('x')), float(t.get('y'))): t.get('name') for t in terminals},
                             {(0, -21): '3', (0, 21): '4', (50, -21): '3', (50, 21): '4'})
            self.assertEqual(root.get('link_type'), 'simple')
            self.assertEqual({t.get('text') for t in root.findall('./description/text')}, {'1', '0', '2'})
            all_ids.extend(t.get('uuid') for t in terminals)
        self.assertEqual(len(set(all_ids)), 8)

    def test_picker_export_and_registration(self):
        picker = gui_core.part_catalog('standard_model', '')
        for model in MODELS:
            self.assertIn(model, picker['omron']['a22n'])
            self.assertNotIn('error', Api().part_options(model))
        with tempfile.TemporaryDirectory() as folder, patch.object(qet_collection, 'user_collection_dir', return_value=Path(folder)):
            result = qet_collection.register_all_parts(models=MODELS)
            self.assertTrue(result['ok'], result['errors'])
            self.assertEqual((result['models'], result['parts']), (4, 6))


if __name__ == '__main__':
    unittest.main()
