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


MODELS = [model for model, spec in gen.STANDARD_DEVICES.items()
          if spec.get('component_style') == 'swallow_transformer']


class SwallowCatalogPartsTest(unittest.TestCase):
    def test_small_models_and_actual_terminal_labels(self):
        expected = ({f'LB21-{v}E' for v in (200, 300, 500)} |
                    {f'ELB21-{v}E' for v in (300, 500, 750)} |
                    {f'CL{f}-{v}A' for f in (21, 41) for v in (1, 2, 3)} |
                    {f'CL{f}-{v}E' for f in (21, 41) for v in (300, 500, 750)} |
                    {f'M{f}-{v}EL' for f in (21, 41, 42) for v in (200, 300, 500, 750)})
        self.assertEqual(set(MODELS), expected)
        for model in MODELS:
            spec = gen.STANDARD_DEVICES[model]
            self.assertLessEqual(spec['ratings']['capacity_va'], 750)
            self.assertTrue(spec['galvanic_isolation'])
            p = spec['external_terminals']['primary']
            s = spec['external_terminals']['secondary']
            if model.startswith('M'):
                self.assertEqual(len(p), 5)
                self.assertEqual(p, ['230V', '200V', '-10V', '0', '+10V'] if model.startswith('M21') else ['460V', '400V', '-20V', '0', '+20V'])
                self.assertEqual(s, ['240V', '220V', '200V', '0', 'E'] if model.startswith('M42') else ['120V', '110V', '100V', '0', 'E'])
            elif model.startswith('CL') and model.endswith('A'):
                self.assertEqual(s, ['⏚'])
                self.assertFalse(spec['electrostatic_shield'])
                self.assertEqual(spec['protection']['location'], 'outlet_branch')
            else:
                self.assertEqual(s, ['110V', '100V', '0', 'E', '⏚'] if model.startswith('CL') else ['110V', '100V', '0', 'E'])
            if model.startswith('LB'):
                self.assertEqual(spec['protection']['location'], 'primary_zero')
            if model.startswith('ELB'):
                self.assertEqual(spec['protection']['location'], 'outlet_branch')

    @requires_qet
    def test_export_preserves_all_ports_and_has_repeatable_ids(self):
        catalog = gui_core.part_catalog('standard_model', '')['swallow']
        for model in MODELS:
            spec = gen.STANDARD_DEVICES[model]
            self.assertIn(model, catalog[spec['series'].lower().replace('-', '_')])
            self.assertNotIn('error', Api().part_options(model))
            with self.subTest(model=model), tempfile.TemporaryDirectory() as folder:
                p, = standard.export_model(model, spec, folder)
                before = p.read_bytes()
                root = ET.parse(p).getroot()
                ports = root.findall('./description/terminal')
                expected = spec['external_terminals']['primary'] + spec['external_terminals']['secondary']
                self.assertEqual([n.get('name') for n in ports], expected)
                self.assertEqual(len(ports), spec['physical_wiring_terminals'])
                self.assertEqual(len({n.get('uuid') for n in ports}), len(ports))
                self.assertTrue(all(float(n.get('x')) in (0, 320) for n in ports))
                self.assertIn('内部結線は省略', root.findtext('informations'))
                standard.export_model(model, spec, folder)
                self.assertEqual(before, p.read_bytes())

    @requires_qet
    def test_bulk_registration(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(qet_collection, 'user_collection_dir', return_value=Path(folder)):
            result = qet_collection.register_all_parts(MODELS)
            self.assertTrue(result['ok'], result['errors'])
            self.assertEqual((result['models'], result['parts']), (30, 30))
            self.assertEqual(len(list(Path(folder).rglob('*.elmt'))), 30)
