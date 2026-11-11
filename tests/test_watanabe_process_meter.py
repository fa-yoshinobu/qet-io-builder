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


class WatanabeProcessMeterTest(unittest.TestCase):
    @requires_qet
    def test_complete_external_connections_and_input_burden(self):
        spec = gen.STANDARD_DEVICES['AL-512']
        self.assertFalse(spec['auxiliary_supply_required'])
        self.assertEqual(spec['physical_wiring_terminals'], 3)
        self.assertEqual(spec['ratings']['input_current_ma_max'], 20)
        self.assertEqual(spec['ratings']['maximum_permissible_input_ma'], 50)
        self.assertEqual(spec['ratings']['voltage_drop_v_typ_at_20ma'], 5.3)
        definitions = []
        for part, template, labels in standard.bindings(spec):
            definitions.append(standard.bind_definition('AL-512', spec, part, template, labels))
        ports = [t for d in definitions for t in d.findall('./description/terminal')]
        self.assertEqual({(float(t.get('x')), float(t.get('y'))): t.get('name') for t in ports},
                         {(-20, 0): 'HI', (20, 0): 'LO', (0, -11): 'E'})
        self.assertEqual(len({t.get('uuid') for t in ports}), 3)
        self.assertTrue(all(d.get('link_type') == 'simple' for d in definitions))
        # Eを計器の測定線へ内部接続したり、D.Pを外部端子へ増やさない。
        self.assertEqual(len(definitions[0].findall('./description/terminal')), 2)
        self.assertEqual(len(definitions[1].findall('./description/terminal')), 1)
        self.assertIn('プロセス電流計', definitions[0].findtext('./names/name'))
        self.assertNotIn('交流', definitions[0].findtext('./names/name'))

    @requires_qet
    def test_picker_and_both_parts_register(self):
        self.assertIn('AL-512', gui_core.part_catalog('standard_model', '')['watanabe']['al'])
        self.assertNotIn('error', Api().part_options('AL-512'))
        with tempfile.TemporaryDirectory() as folder, patch.object(qet_collection, 'user_collection_dir', return_value=Path(folder)):
            result = qet_collection.register_all_parts(['AL-512'])
            self.assertTrue(result['ok'], result['errors'])
            self.assertEqual((result['models'], result['parts']), (1, 2))
            names = [ET.parse(p).findtext('./names/name') for p in Path(folder).rglob('*.elmt')]
            self.assertTrue(any('プロセス電流計' in n for n in names))
            self.assertTrue(any('接地端子' in n for n in names))


if __name__ == '__main__':
    unittest.main()
