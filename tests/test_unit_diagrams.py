import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import gen_io_page as gen
from renderers.unit_diagrams import build_pages, validate
from webgui.api import Api


def info(element, name):
    return element.findtext(f"elementInformations/elementInformation[@name='{name}']")


class UnitDiagramsTest(unittest.TestCase):
    def test_terminal_expansion_preserves_every_real_terminal(self):
        for model, spec in gen.UNIT_DIAGRAMS.items():
            with self.subTest(model=model):
                expected = sum(row['signal'].upper() != 'NC'
                               for section in spec['sections']
                               if not section.get('connector') or section.get('expand')
                               or len(section.get('terminals', [])) > 12
                               for row in section.get('terminals', []))
                pages = build_pages({'model': model}, spec, gen.build_symbols())
                actual = [(key, element, y) for _, page in pages for key, element, _, y in page.placed
                          if key.startswith(('module_pin', 'plc_in_unit'))]
                self.assertEqual(len(actual), expected)
                for key, element, y in actual:
                    self.assertNotEqual(info(element, 'label'), 'NC')
                    self.assertLessEqual(y + 20, 790)
                for _, page in pages:
                    for key, _, _, y in page.placed:
                        if key.startswith('plc_in_unit'):
                            self.assertLessEqual(y + 20, page.communication_footer_top - 8)

    def test_independent_output_common_stays_with_its_group(self):
        model = 'NX1P2-1040DT'
        pages = build_pages({'model': model}, gen.UNIT_DIAGRAMS[model], gen.build_symbols())
        columns = []
        for _, page in pages:
            for x in {x for key, _, x, _ in page.placed if key.startswith('plc_in_unit')}:
                columns.append([info(e, 'label') for key, e, xx, _ in page.placed
                                if key.startswith('plc_in_unit') and xx == x])
        for common, signals in [('C0(0V)', [f'{n:02}' for n in range(8)]),
                                ('C1(0V)', [f'{n:02}' for n in range(8, 16)])]:
            column = next(rows for rows in columns if common in rows)
            self.assertTrue(all(signal in column for signal in signals))

    def test_unit_and_io_supplies_are_separate_networks(self):
        spec = dict(manufacturer='omron', series=['NX'], function='電源', sections=[
            dict(name='電源', terminals=[dict(pin=str(i), signal=group + lane,
                                             lane=lane, power_group=group)
                                        for i, (group, lane) in enumerate([
                                            ('unit', 'P'), ('unit', 'N'), ('io', 'P'), ('io', 'N')])])])
        page = build_pages({'model': 'test'}, spec, gen.build_symbols())[0][1]
        adjacency = {}
        for wire in page.conductors:
            a, b = wire.get('element1'), wire.get('element2')
            adjacency.setdefault(a, set()).add(b)
            adjacency.setdefault(b, set()).add(a)
        terminals = {info(e, 'label'): e.get('uuid') for key, e, _, _ in page.placed
                     if key == 'plc_in_unit'}
        for name, start in terminals.items():
            seen, pending = set(), [start]
            while pending:
                node = pending.pop()
                if node not in seen:
                    seen.add(node)
                    pending.extend(adjacency.get(node, []))
            self.assertEqual({label for label, uid in terminals.items() if uid in seen}, {name})

    def test_unused_nc_and_relay_nc_contact_are_distinct(self):
        spec = dict(manufacturer='omron', series=['NX'], function='端子', sections=[dict(name='端子台', terminals=[
            dict(pin='1', signal='NC', connectable=False),
            dict(pin='2', signal='CJ', connectable=False),
            dict(pin='3', signal='NC0')])])
        page = build_pages({'model': 'test'}, spec, gen.build_symbols())[0][1]
        placed = {info(e, 'label'): page.sym[key] for key, e, _, _ in page.placed
                  if key.startswith('plc_in_unit')}
        self.assertEqual(set(placed), {'CJ', 'NC0'})
        self.assertFalse(placed['CJ'].terminals)
        self.assertTrue(placed['NC0'].terminals)

    def test_duplicate_pins_are_scoped_to_each_connector(self):
        spec = copy.deepcopy(gen.UNIT_DIAGRAMS['NX-CIF210'])
        validate('NX-CIF210', spec)
        section = next(s for s in spec['sections'] if s.get('connector'))
        section['terminals'].append(copy.deepcopy(section['terminals'][0]))
        with self.assertRaises(ValueError):
            validate('NX-CIF210', spec)

    def test_failed_nx_save_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'existing.qet'
            target.write_text('existing', encoding='utf-8')
            with patch.object(gen.ET.ElementTree, 'write', side_effect=OSError('write failed')):
                result = Api().generate_nx('NX-ECC203', '', '', str(target))
            self.assertIn('error', result)
            self.assertEqual(target.read_text(encoding='utf-8'), 'existing')
            self.assertIn('error', Api().generate_nx('KV-8000', '', '', str(target)))


if __name__ == '__main__':
    unittest.main()
