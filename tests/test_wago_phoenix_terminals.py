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


class WagoPhoenixTerminalsTest(unittest.TestCase):
    def test_catalog_export_and_registration_keep_all_wire_ports(self):
        catalog = gui_core.part_catalog('standard_model', '')
        expected = {
            'wago': ('topjob_s', {
                '2002-1201': 2, '2002-1207': 2, '2002-1301': 3,
                '2002-1401': 4, '2002-2701': 4, '2002-2708': 4,
                '2004-1201': 2, '2004-1207': 2, '2004-1301': 3}),
            'phoenix_contact': ('pt', {
                'PT 2,5': 2, 'PT 2,5-TWIN': 3, 'PT 2,5-QUATTRO': 4,
                'PT 2,5-PE': 2, 'PT 4': 2, 'PT 4-TWIN': 3,
                'PT 4-QUATTRO': 4, 'PT 4-PE': 2})}
        models = []
        api = Api()
        for maker, (series, entries) in expected.items():
            self.assertTrue(set(entries) <= set(catalog[maker][series]))
            for model, count in entries.items():
                models.append(model)
                with self.subTest(model=model), tempfile.TemporaryDirectory() as folder:
                    spec = gen.STANDARD_DEVICES[model]
                    self.assertNotIn('error', api.part_options(model))
                    paths = standard.export_model(model, spec, folder)
                    roots = [ET.parse(p).getroot() for p in paths]
                    terminals = [t for r in roots for t in r.findall('./description/terminal')]
                    self.assertEqual(len(terminals), count)
                    self.assertEqual(len({t.get('uuid') for t in terminals}), count)
                    self.assertTrue(all('配線口' in t.get('name') for t in terminals))
                    for root in roots:
                        self.assertEqual(sum(t.findtext('info_name') == 'label'
                                             for t in root.findall('./description/dynamic_text')), 1)
                        horizontal = [float(t.get('y')) for t in root.findall('./description/terminal')
                                      if t.get('orientation') in ('e', 'w')]
                        for text in root.findall('./description/dynamic_text'):
                            if horizontal and text.findtext('info_name') in ('label', 'manufacturer_reference', 'comment'):
                                self.assertLess(float(text.get('y')) + 16, min(horizontal))
                    if spec['protective_earth']:
                        self.assertTrue(spec['conductive_din_rail_required'])
                        self.assertNotIn('iec_current_a', spec['ratings'])
                        self.assertEqual(spec['symbol_bindings'][0]['symbol'], 'pe_terminal')
        with tempfile.TemporaryDirectory() as folder, patch.object(
                qet_collection, 'user_collection_dir', return_value=Path(folder)):
            result = qet_collection.register_all_parts(models=models)
            self.assertTrue(result['ok'], result['errors'])
            self.assertEqual(result['models'], 17)
            self.assertEqual(result['parts'], 18)

    def test_double_deck_isolated_and_common_are_different_circuits(self):
        isolated = gen.STANDARD_DEVICES['2002-2701']
        common = gen.STANDARD_DEVICES['2002-2708']
        self.assertEqual(isolated['internal_connections'], [
            ['下段配線口1', '下段配線口2'], ['上段配線口1', '上段配線口2']])
        self.assertEqual([b['symbol'] for b in isolated['symbol_bindings']], ['terminal', 'terminal'])
        self.assertEqual(len(common['internal_connections']), 1)
        self.assertEqual(len(common['internal_connections'][0]), 4)
        self.assertEqual(common['symbol_bindings'][0]['symbol'], 'terminal_4way')


if __name__ == '__main__':
    unittest.main()
