import unittest

import gen_io_page as gen


class TerminalBlockCablesTest(unittest.TestCase):
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
