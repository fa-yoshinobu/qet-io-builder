import tempfile
import unittest
from xml.etree import ElementTree as ET

import gen_io_page as gen
from renderers import standard


class StandardContactNamesTest(unittest.TestCase):
    def test_socket_pins_and_multilevel_terminals_are_distinguishable(self):
        for model in ('TP58X1', 'SU4S-21L', 'P2RF-08-PU', '2002-2701'):
            with self.subTest(model=model), tempfile.TemporaryDirectory() as folder:
                spec = gen.STANDARD_DEVICES[model]
                paths = standard.export_model(model, spec, folder)
                names = []
                for part, template, pins in standard.bindings(spec):
                    root = ET.parse(next(p for p in paths if p.stem == part)).getroot()
                    name = root.findtext("./names/name[@lang='ja']")
                    names.append(name)
                    actual = dict.fromkeys(t for values in pins.values() for t in values)
                    self.assertTrue(all(t in name for t in actual), name)
                    self.assertNotIn(' / '.join(list(actual) * 2), name)
                self.assertEqual(len(names), len(set(names)))

    def test_changeover_contacts_have_distinct_names_and_actual_pin_numbers(self):
        for model in ('MY4N', 'MY4Z', 'MY2N', 'H3Y-4', 'RJ2S-CL-D24'):
            with self.subTest(model=model), tempfile.TemporaryDirectory() as folder:
                spec = gen.STANDARD_DEVICES[model]
                paths = standard.export_model(model, spec, folder)
                names = []
                for part, template, pins in standard.bindings(spec):
                    if set(pins) != {'common', 'no', 'nc'}:
                        continue
                    path = next(p for p in paths if p.stem == part)
                    root = ET.parse(path).getroot()
                    name = root.findtext("./names/name[@lang='ja']")
                    names.append(name)
                    for role, prefix in (('common', 'COM:'), ('no', 'a:'), ('nc', 'b:')):
                        self.assertIn(prefix + '/'.join(pins[role]), name)
                    self.assertEqual({t.get('name') for t in root.findall('./description/terminal')},
                                     {'/'.join(v) for v in pins.values()})
                self.assertTrue(names)
                self.assertEqual(len(names), len(set(names)))
                if model.startswith('MY4'):
                    self.assertIn(model + ' c接点1（COM:9 / a:5 / b:1）', names)
                    self.assertIn(model + ' c接点4（COM:12 / a:8 / b:4）', names)


if __name__ == '__main__':
    unittest.main()
