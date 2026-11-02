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


class InterfaceRelaysTest(unittest.TestCase):
    CASES = {
        '857-304': ('wago', 'relay_857', 1),
        '788-304': ('wago', 'relay_788', 1),
        '788-312': ('wago', 'relay_788', 2),
        'PLC-RSC-24DC/21': ('phoenix_contact', 'plc_interface', 1),
        'PLC-RSC-24DC/21-21': ('phoenix_contact', 'plc_interface', 2),
        'PLC-RPT-24DC/21': ('phoenix_contact', 'plc_interface', 1),
        'PLC-RPT-24DC/21-21': ('phoenix_contact', 'plc_interface', 2),
    }

    def test_module_external_terminals_polarity_and_contact_roles(self):
        catalog = gui_core.part_catalog('standard_model', '')
        for model, (maker, series, poles) in self.CASES.items():
            with self.subTest(model=model), tempfile.TemporaryDirectory() as folder:
                self.assertIn(model, catalog[maker][series])
                self.assertNotIn('error', Api().part_options(model))
                spec = gen.STANDARD_DEVICES[model]
                self.assertEqual(spec['terminal_numbering'], 'relay_module_external_terminals')
                self.assertFalse(spec['coil']['voltage_selection_required'])
                paths = standard.export_model(model, spec, folder)
                roots = {p.stem: ET.parse(p).getroot() for p in paths}
                self.assertEqual(len(paths), poles + 1)
                coil = roots['coil']
                self.assertEqual(coil.get('link_type'), 'master')
                self.assertEqual({t.get('name') for t in coil.findall('./description/terminal')}, {'A1', 'A2'})
                texts = [t.findtext('text') for t in coil.findall('./description/dynamic_text')]
                self.assertIn('A1 (+)', texts)
                self.assertIn('A2 (-)', texts)
                info_texts = {t.findtext('info_name'): t for t in coil.findall('./description/dynamic_text')
                              if t.findtext('info_name')}
                self.assertLess(float(info_texts['manufacturer_reference'].get('y')),
                                float(info_texts['comment'].get('y')))
                self.assertLess(float(info_texts['comment'].get('y')) + 10,
                                float(info_texts['label'].get('y')))
                names = set()
                for i in range(1, poles + 1):
                    root = roots[f'contact_{i}']
                    self.assertEqual(root.get('link_type'), 'slave')
                    terminals = {(float(t.get('x')), float(t.get('y'))): t.get('name')
                                 for t in root.findall('./description/terminal')}
                    self.assertEqual(terminals, {(0, 20): f'{i}1', (0, -20): f'{i}4', (-20, -20): f'{i}2'})
                    name = root.findtext("./names/name[@lang='ja']")
                    self.assertIn(f'COM:{i}1 / a:{i}4 / b:{i}2', name)
                    names.add(name)
                self.assertEqual(len(names), poles)

    def test_registration_handles_slash_in_order_names_without_nesting(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(
                qet_collection, 'user_collection_dir', return_value=Path(folder)):
            result = qet_collection.register_all_parts(models=list(self.CASES))
            self.assertTrue(result['ok'], result['errors'])
            self.assertEqual(result['models'], 7)
            self.assertEqual(result['parts'], 17)
            base = Path(folder) / 'qet-io-builder' / 'phoenix_contact' / 'plc_interface'
            self.assertTrue((base / 'PLC-RSC-24DC-21' / 'coil.elmt').exists())
            self.assertFalse((base / 'PLC-RSC-24DC' / '21').exists())


if __name__ == '__main__':
    unittest.main()
