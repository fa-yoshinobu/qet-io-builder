import copy
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


CONTACTS = {
    'HW1B-M120G': (2, 0), 'HW1B-M102R': (0, 2), 'HW1B-M122G': (2, 2),
    'HW1B-A110G': (1, 0), 'HW1B-A111G': (1, 1), 'HW1B-A120G': (2, 0), 'HW1B-A122G': (2, 2),
    'HW1L-M120Q4G': (2, 0), 'HW1L-M102Q4R': (0, 2), 'HW1L-M122Q4G': (2, 2),
    'HW1L-A110Q4G': (1, 0), 'HW1L-A111Q4G': (1, 1),
    'HW1K-2A10': (1, 0), 'HW1K-2A11': (1, 1), 'HW1K-2B10': (1, 0), 'HW1K-2C10': (1, 0),
    'HW1S-2T20': (2, 0), 'HW1S-2T22': (2, 2),
    'HW1B-V403R': (0, 3), 'HW1B-V404R': (0, 4), 'HW1B-V411R': (1, 1), 'HW1B-V422R': (2, 2),
    'HW1B-X401R': (0, 1), 'HW1B-X402R': (0, 2), 'HW1B-V301R': (0, 1), 'HW1B-V302R': (0, 2),
}
LAMPS = {'HW1P-1Q4W': '乳白', 'HW1P-1Q4S': '青', 'HW1P-1Q4A': 'アンバー', 'HW1P-1Q4PW': 'ピュアホワイト'}
MODELS = [*CONTACTS, *LAMPS]


class IdecHwVariantsTest(unittest.TestCase):
    def test_real_contact_pins_lamps_and_display_names(self):
        for model in MODELS:
            with self.subTest(model=model), tempfile.TemporaryDirectory() as folder:
                spec = gen.STANDARD_DEVICES[model]
                self.assertLessEqual(set(spec.get('contact_block_positions', {})),
                                     {b['name'] for b in spec['symbol_bindings']})
                roots = [ET.parse(p).getroot() for p in standard.export_model(model, spec, folder)]
                labels = [r.findtext("./names/name[@lang='ja']") for r in roots]
                self.assertEqual(len(labels), len(set(labels)))
                ids, no, nc, lamp = [], 0, 0, 0
                for root in roots:
                    ports = root.findall('./description/terminal')
                    ids += [p.get('uuid') for p in ports]
                    pins = {p.get('name') for p in ports}
                    if pins == {'3', '4'}:
                        no += 1
                    elif pins == {'1', '2'}:
                        nc += 1
                    else:
                        self.assertEqual(pins, {'X1', 'X2'})
                        lamp += 1
                        self.assertEqual(root.get('link_type'), 'simple')
                self.assertEqual(len(ids), len(set(ids)))
                self.assertEqual((no, nc), CONTACTS.get(model, (0, 0)))
                self.assertEqual(lamp, int(model in LAMPS or model.startswith('HW1L-')))
                if lamp:
                    self.assertEqual(spec['lamp']['rated_voltage'], 'AC/DC24V')
                    self.assertEqual(spec['lamp']['polarity'], 'none')
                if model in LAMPS:
                    self.assertEqual(spec['lamp']['color'], LAMPS[model])

    def test_key_removal_contact_states_and_reset_mechanism(self):
        for model, positions in [('HW1K-2A10', [1, 2]), ('HW1K-2B10', [1]), ('HW1K-2C10', [2])]:
            spec = gen.STANDARD_DEVICES[model]
            self.assertEqual(spec['key_removal_positions'], positions)
            self.assertEqual(spec['position_contact_table'], {'1': {'selector': 'open'}, '2': {'selector': 'closed'}})
            self.assertEqual(spec['symbol_bindings'][0]['symbol'], 'key_selector_2position')
        spec = gen.STANDARD_DEVICES['HW1K-2A11']
        self.assertEqual(spec['position_contact_table']['1'], {'selector': 'open', 'nc_1': 'closed'})
        self.assertEqual(spec['position_contact_table']['2'], {'selector': 'closed', 'nc_1': 'open'})
        for model in CONTACTS:
            spec = gen.STANDARD_DEVICES[model]
            if model.startswith(('HW1B-V', 'HW1B-X')):
                self.assertFalse(spec['safety_function_verified'])
                key = model.startswith('HW1B-X')
                self.assertEqual(spec['operation'], 'push_lock_key_reset' if key else 'push_lock_turn_reset')
                self.assertEqual(spec['symbol_bindings'][0]['symbol'], 'emergency_key_reset_nc' if key else 'emergency_turn_reset_nc')

    def test_alternate_is_linkable_without_momentary_geometry(self):
        for model in MODELS:
            spec = gen.STANDARD_DEVICES[model]
            if spec.get('operation') != 'alternate':
                continue
            part, template, labels = next(standard.bindings(spec))
            self.assertEqual(template, 'maintained_switch_no')
            self.assertIn('オルタネイト', spec['display_ratings'])
            root = standard.bind_definition(model, spec, part, template, labels)
            self.assertEqual(root.get('link_type'), 'master')
            self.assertEqual(root.findtext("./kindInformations/kindInformation[@name='type']"), 'commutator')
            source = ET.parse(standard.collection_root() / standard.catalog()[template]['path']).getroot()
            def geometry(node):
                result = []
                for child in node.find('description'):
                    if child.tag in ('terminal', 'text', 'dynamic_text'):
                        continue
                    child = copy.deepcopy(child)
                    child.tail = None
                    result.append(ET.tostring(child))
                return result
            self.assertEqual(geometry(root), geometry(source))

    def test_gui_and_all_added_parts_register(self):
        catalog = gui_core.part_catalog('standard_model', '')['idec']['hw']
        for model in MODELS:
            self.assertIn(model, catalog)
            self.assertNotIn('error', Api().part_options(model))
        with tempfile.TemporaryDirectory() as folder, patch.object(qet_collection, 'user_collection_dir', return_value=Path(folder)):
            result = qet_collection.register_all_parts(MODELS)
            self.assertTrue(result['ok'], result['errors'])
            self.assertEqual((result['models'], result['parts']), (30, 67))


if __name__ == '__main__':
    unittest.main()
