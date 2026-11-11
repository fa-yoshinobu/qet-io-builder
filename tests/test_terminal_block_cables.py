import unittest

import gen_io_page as gen


class TerminalBlockCablesTest(unittest.TestCase):
    def test_mil_connector_splits_numeric_pins_by_parity(self):
        pages = gen.terminal_block_project_pages('XW2R-J34GD-C2', 'NX-ID6142-5',
                                                 'XW2Z-100K', 'PLC1', 'XT1', 'W1')
        project, _ = gen.build_project({'front_pages': False}, pages)
        io = project.find('diagram')
        columns = {}
        for element in io.findall('elements/element'):
            pin = int(element.findtext("elementInformations/elementInformation[@name='auxiliary1']"))
            columns.setdefault(float(element.get('x')), set()).add(pin % 2)
        self.assertEqual(list(columns.values()), [{1}, {0}])
        self.assertLess(max(columns), gen.BORDER_COLS * gen.COL_SIZE)

    def test_a6tbxy36_zero_volt_terminal_depends_on_plc(self):
        for plc, expected_contacts in [('QX41', 0), ('QY41P', 2)]:
            with self.subTest(plc=plc):
                pages = gen.terminal_block_project_pages('A6TBXY36', plc, 'AC10TB',
                                                         'PLC1', 'XT1', 'W1')
                project, _ = gen.build_project({'front_pages': False}, pages)
                _, block = project.findall('diagram')
                contacts = [el for el in block.findall('elements/element')
                            if el.findtext("elementInformations/elementInformation[@name='label']") == '0V']
                self.assertEqual(len(contacts), expected_contacts)

    def test_separate_sheets_point_to_each_other_after_front_pages(self):
        pages = gen.terminal_block_project_pages('PCX-1H34-TB40-K-Nano', 'KV-NC32T',
                                                 'GRPTS-M34-M34-1', 'PLC7', 'XT3', 'W12')
        project, _ = gen.build_project({'front_pages': True}, pages)
        diagrams = project.findall('diagram')
        io, block = diagrams[-2:]
        for diagram, target in [(io, len(diagrams)), (block, len(diagrams) - 1)]:
            lines = [node.get('text', '') for node in diagram.findall('inputs/input')]
            self.assertTrue(any('W12' in line and 'GRPTS-M34-M34-1' in line
                                and f'相手図  p.{target}' in line for line in lines))
            self.assertTrue(any('PLC7' in line and 'XT3' in line for line in lines))
        self.assertIn('内蔵I/O', io.get('title'))
        self.assertIn('中継端子台', block.get('title'))
        self.assertEqual(len(block.findall('elements/element')), 40)
        self.assertFalse(any('tb_terminal' in el.get('type', '') for el in io.findall('elements/element')))

    def test_unlisted_plc_and_duplicate_cable_number_are_rejected(self):
        with self.assertRaises(ValueError):
            gen.terminal_block_project_pages('PCX-1H34-TB34-K1', 'KV-NC32T',
                                             'GRPTS-M34-M34-1', 'PLC1', 'XT1', 'CB1')
        pages = []
        for plc_tag, block_tag in [('PLC1', 'XT1'), ('PLC2', 'XT2')]:
            pages += gen.terminal_block_project_pages('PCX-1H34-TB34-K1', 'KV-NC32EX',
                                                      'KB34N-1H1H-1MB', plc_tag, block_tag, 'CB1')
        with self.assertRaisesRegex(ValueError, 'ケーブル番号が重複'):
            gen.build_project({}, pages)

    def test_dual_connector_keeps_plc_pin_numbering_and_page_references_separate(self):
        from renderers.cable_routes import iolist_rows

        pages = gen.terminal_block_project_pages('PCX-1H34-TB34-K1', 'KV-C64XC', 'KB34N-1H1H-1MB',
                                                 'PLC1', 'XT1', 'W1', tag2='XT2', cable_tag2='W2',
                                                 cable2='GRPTS-M34-M34-1')
        pg, _ = pages[0]
        pins = {row[4]: (row[1], row[5]) for row in iolist_rows(pg, *gen.terminal_block_choice(pg))}
        self.assertEqual(pins['L側 2'], ('001', 'XT1 TB1 001'))
        self.assertEqual(pins['H側 2'], ('201', 'XT2 TB1 001'))
        self.assertEqual(pins['H側 17'], ('COM2', 'XT2 TB1 COM0'))
        self.assertEqual(pins['H側 18'], ('300', 'XT2 TB2 100'))
        project, _ = gen.build_project({'front_pages': False}, pages)
        for sheet, peer, cable in zip(project.findall('diagram'), (2, 1, 4, 3),
                                      (pg['cable'], pg['cable'], pg['cable2'], pg['cable2']), strict=True):
            self.assertTrue(any(cable in node.get('text') and f'相手図  p.{peer}' in node.get('text')
                                for node in sheet.findall('inputs/input')))
        with self.assertRaisesRegex(ValueError, 'ケーブル番号が重複'):
            gen.terminal_block_choice(dict(pg, cable_tag2='W1'))

    def test_split_cable_ends_at_each_relay_input_and_leaves_load_contacts_isolated(self):
        from renderers.cable_routes import iolist_rows

        pages = gen.terminal_block_project_pages('PCRY-1H20-16A-FD', 'KV-NC32ET',
                                                 'KB40Y-1H1H-100-75-15B', 'PLC1', 'XT1', 'W1', tag2='XT2')
        pg, _ = pages[0]
        rows = list(iolist_rows(pg, *gen.terminal_block_choice(pg)))
        by_pin = {row[4]: (row[1], row[5]) for row in rows}
        self.assertEqual(len(rows), len(by_pin))
        self.assertEqual(by_pin['1'], ('000', 'XT1 CN2 MIL 20'))
        self.assertEqual(by_pin['28'], ('113', 'XT2 CN3 MIL 9'))
        self.assertEqual(by_pin['33'], ('COM0', 'XT1 CN2 MIL 3'))
        self.assertEqual(by_pin['34'], ('COM1', 'XT2 CN3 MIL 3'))
        project, _ = gen.build_project({'front_pages': False}, pages)
        io, first, second = project.findall('diagram')
        for sheet in (first, second):
            contacts = [el for el in sheet.findall('elements/element')
                        if el.get('type', '').endswith('/terminal_block_isolated_no.elmt')]
            self.assertEqual(len(contacts), 16)
            self.assertTrue(all(len(el.findall('terminals/terminal')) == 2 for el in contacts))
            load_ids = {el.get('uuid') for el in contacts}
            self.assertFalse(any(wire.get(end) in load_ids for wire in sheet.findall('conductors/conductor')
                                 for end in ('element1', 'element2')))
