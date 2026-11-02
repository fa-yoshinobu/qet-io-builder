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


MODELS = ['HW1L-M110Q4G', 'HW1L-M101Q4R', 'HW1S-3T20', 'HW1B-V401R', 'HW1B-V402R']


class IdecHwExpansionTest(unittest.TestCase):
    def test_illuminated_contacts_remain_separate_from_lamp(self):
        for model, pins, template in [('HW1L-M110Q4G', {'3', '4'}, 'pushbutton_no'), ('HW1L-M101Q4R', {'1', '2'}, 'pushbutton_nc')]:
            spec = gen.STANDARD_DEVICES[model]
            assignments = list(standard.bindings(spec))
            self.assertEqual([t for _, t, _ in assignments], [template, 'lamp'])
            self.assertEqual(spec['lamp']['rated_voltage'], 'AC/DC24V')
            self.assertEqual(spec['lamp']['polarity'], 'none')
            with tempfile.TemporaryDirectory() as folder:
                roots = {p.stem: ET.parse(p).getroot() for p in standard.export_model(model, spec, folder)}
                self.assertEqual({t.get('name') for t in roots['pushbutton'].findall('./description/terminal')}, pins)
                self.assertEqual({t.get('name') for t in roots['lamp'].findall('./description/terminal')}, {'X1', 'X2'})
                self.assertEqual(roots['pushbutton'].get('link_type'), 'master')
                self.assertEqual(roots['lamp'].get('link_type'), 'simple')

    def test_three_position_switch_keeps_both_contact_blocks_independent(self):
        model = 'HW1S-3T20'
        spec = gen.STANDARD_DEVICES[model]
        self.assertEqual(spec['position_contact_table'], {'1': {'contact_1': 'closed', 'contact_2': 'open'}, '0': {'contact_1': 'open', 'contact_2': 'open'}, '2': {'contact_1': 'open', 'contact_2': 'closed'}})
        part, template, labels = next(iter(standard.bindings(spec)))
        root = standard.bind_definition(model, spec, part, template, labels)
        terminals = root.findall('./description/terminal')
        self.assertEqual(len({t.get('uuid') for t in terminals}), 4)
        self.assertEqual({(float(t.get('x')), float(t.get('y'))): t.get('name') for t in terminals}, {(0, -21): '3', (0, 21): '4', (50, -21): '3', (50, 21): '4'})
        self.assertEqual({t.get('text') for t in root.findall('./description/text')}, {'1', '0', '2'})
        self.assertEqual(root.get('link_type'), 'simple')

    def test_emergency_two_nc_blocks_do_not_share_terminal_ids(self):
        for model, count in [('HW1B-V401R', 1), ('HW1B-V402R', 2)]:
            spec = gen.STANDARD_DEVICES[model]
            self.assertEqual(spec['operation'], 'push_lock_turn_reset')
            self.assertFalse(spec['safety_function_verified'])
            with tempfile.TemporaryDirectory() as folder:
                roots = [ET.parse(p).getroot() for p in standard.export_model(model, spec, folder)]
                self.assertEqual(len(roots), count)
                uuids = []
                for root in roots:
                    terminals = root.findall('./description/terminal')
                    self.assertEqual({t.get('name') for t in terminals}, {'1', '2'})
                    uuids.extend(t.get('uuid') for t in terminals)
                self.assertEqual(len(set(uuids)), 2 * count)
                if count == 2:
                    self.assertEqual(spec['mechanically_linked'], ['emergency', 'nc'])

    def test_picker_and_registration(self):
        picker = gui_core.part_catalog('standard_model', '')
        for model in MODELS:
            self.assertIn(model, picker['idec']['hw'])
            self.assertNotIn('error', Api().part_options(model))
        with tempfile.TemporaryDirectory() as folder, patch.object(qet_collection, 'user_collection_dir', return_value=Path(folder)):
            result = qet_collection.register_all_parts(models=MODELS)
            self.assertTrue(result['ok'], result['errors'])
            self.assertEqual((result['models'], result['parts']), (5, 8))


if __name__ == '__main__':
    unittest.main()
