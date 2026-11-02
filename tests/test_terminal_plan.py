import copy
import unittest

import gen_io_page as gen
from renderers import terminal_plan


class TerminalPlanTest(unittest.TestCase):
    def build(self, pages):
        return terminal_plan.build_pages([(page, None) for page in pages], {}, gen.Page, gen.table, gen.page_heading)

    def page(self, connections, enabled=True):
        return {'model': 'RX40C7', 'tag': 'PLC1',
                'wiring': {'terminal_plan': enabled, 'connections': connections}}

    def texts(self, page):
        return [item.get('text') for item in page.texts]

    def test_only_enabled_explicit_external_terminals_are_listed(self):
        page = self.page([{'terminal_block': 'TB1', 'terminal': '01', 'unit_terminal': 'X0', 'wire': '001'},
                          {'terminal_block': 'TB1'}, {'terminal': '2'}, {'unit_terminal': 'COM'}])
        original = copy.deepcopy(page)
        unselected = self.page([{'terminal_block': 'HIDDEN', 'terminal': '3'}], enabled=False)
        result = self.build([page, unselected])
        self.assertEqual(len(result), 1)
        values = self.texts(result[0][1])
        self.assertIn('PLC1', values)
        self.assertIn('01', values)
        self.assertIn('001', values)
        self.assertIn('X0', values)
        self.assertNotIn('COM', values)
        self.assertNotIn('NC', values)
        self.assertNotIn('HIDDEN', values)
        self.assertEqual(page, original)
        self.assertEqual(self.build([self.page([], enabled=True), unselected]), [])

    def test_same_terminal_number_on_different_levels_keeps_both_rows(self):
        result = self.build([self.page([{'terminal_block': 'TB1', 'terminal': '1', 'level': level, 'wire': wire}
                                       for level, wire in [('上段', '101'), ('下段', '102')]])])
        values = self.texts(result[0][1])
        self.assertEqual(values.count('1'), 2)
        for text in ('上段', '下段', '101', '102'):
            self.assertEqual(values.count(text), 1)

    def test_long_cells_wrap_without_losing_records_and_headers_repeat_on_every_page(self):
        records = [{'terminal_block': 'TB1', 'terminal': f'{i:03}', 'wire': f'W{i:03}',
                    'peer_tag': '相手機器を識別する長いタグ名' * 4, 'peer_terminal': '13',
                    'destination': '別ページの接続先', 'cable': 'CB01', 'core': '赤',
                    'section': '0.75 mm²', 'shield': '片側接地', 'jumper': '1-2'} for i in range(1, 45)]
        result = self.build([self.page(records)])
        self.assertGreater(len(result), 1)
        all_values = []
        for _, page in result:
            values = self.texts(page)
            all_values.extend(values)
            for header, _ in terminal_plan.COLUMNS:
                self.assertEqual(values.count(header), 1)
            self.assertFalse(page.elements)
            self.assertTrue(page.shapes)
            self.assertTrue(all(shape.get('is_movable') == '1' for shape in page.shapes))
            self.assertTrue(all(float(shape.get('y2')) <= terminal_plan.BOTTOM for shape in page.shapes))
            xs = [terminal_plan.LEFT]
            for _, width in terminal_plan.COLUMNS:
                xs.append(xs[-1] + width)
            for item in page.texts:
                y = float(item.get('y'))
                if y < terminal_plan.TOP + terminal_plan.HEADER_HEIGHT:
                    continue
                x = float(item.get('x'))
                right = next(bound for bound in xs if bound > x)
                self.assertLessEqual(terminal_plan._width(item.get('text')), right - x - 8)
                self.assertLess(y + 20, terminal_plan.BOTTOM)
        for record in records:
            self.assertEqual(all_values.count(record['terminal']), 1)
            self.assertEqual(all_values.count(record['wire']), 1)
        self.assertIn('CB01 / 赤', all_values)
        self.assertIn('線径 0.75 mm²', all_values)
        self.assertIn('シールド 片側接地', all_values)
        self.assertIn('渡り 1-2', all_values)

    def test_single_row_too_tall_to_fit_is_rejected_instead_of_clipped(self):
        with self.assertRaisesRegex(ValueError, '1行が1ページに収まりません'):
            self.build([self.page([{'terminal_block': 'TB1', 'terminal': '1', 'purpose': '長文' * 1000}])])


if __name__ == '__main__':
    unittest.main()
