import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

import gen_io_page as gen
import gui_core
from renderers import standard
from tools import qet_collection


PINS = {
    '3A1B': ([('23', '24'), ('33', '34'), ('43', '44')], [('11', '12')]),
    '2A2B': ([('33', '34'), ('43', '44')], [('11', '12'), ('21', '22')]),
    '5A1B': ([('23', '24'), ('33', '34'), ('43', '44'), ('53', '54'), ('63', '64')], [('11', '12')]),
    '4A2B': ([('33', '34'), ('43', '44'), ('53', '54'), ('63', '64')], [('11', '12'), ('21', '22')]),
    '3A3B': ([('43', '44'), ('53', '54'), ('63', '64')], [('11', '12'), ('21', '22'), ('31', '32')]),
}
MODELS = [f'G7SA-{suffix} DC24' for suffix in PINS]


class G7saPartsTest(unittest.TestCase):
    def test_manual_pins_polarity_and_linkable_symbols(self):
        for suffix, (no, nc) in PINS.items():
            model = f'G7SA-{suffix} DC24'
            spec = gen.STANDARD_DEVICES[model]
            self.assertTrue(spec['forcibly_guided_contacts'])
            self.assertEqual(spec['coil']['polarity_by_terminal'], {'0': '+', '1': '-'})
            with self.subTest(model=model), tempfile.TemporaryDirectory() as folder:
                roots = [ET.parse(p).getroot() for p in standard.export_model(model, spec, folder)]
                pairs = lambda r: tuple(t.get('name') for t in r.findall('./description/terminal'))
                self.assertEqual(pairs(roots[0]), ('0', '1'))
                self.assertEqual(roots[0].get('link_type'), 'master')
                self.assertEqual([pairs(r) for r in roots[1:]], no + nc)
                self.assertEqual([r.findtext("./kindInformations/kindInformation[@name='state']") for r in roots[1:]], ['NO'] * len(no) + ['NC'] * len(nc))
                self.assertTrue(all(r.get('link_type') == 'slave' for r in roots[1:]))
                names = [r.findtext("./names/name[@lang='ja']") for r in roots]
                self.assertEqual(len(names), len(set(names)))
                ids = [t.get('uuid') for r in roots for t in r.findall('./description/terminal')]
                self.assertEqual(len(ids), len(set(ids)))

    def test_catalog_and_bulk_registration(self):
        self.assertEqual(set(gui_core.part_catalog('standard_model', '')['omron']['g7sa']), set(MODELS))
        with tempfile.TemporaryDirectory() as folder, patch.object(qet_collection, 'user_collection_dir', return_value=Path(folder)):
            result = qet_collection.register_all_parts(MODELS)
            self.assertEqual(result['errors'], [])
            self.assertEqual(result['parts'], 31)
            self.assertEqual(len(list(Path(folder).rglob('*.elmt'))), 31)
