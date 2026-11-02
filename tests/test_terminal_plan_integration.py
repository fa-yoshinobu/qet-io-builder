import copy
import unittest

import gen_io_page as gen
from project_wiring.data import terminal_rows


class TerminalPlanIntegrationTest(unittest.TestCase):
    def page(self, enabled):
        return {'kind': 'fx5body', 'model': 'FX5S-30MR/DS', 'tag': 'PLC1',
                'wiring': {'terminal_plan': enabled, 'connections': [
                    {'x': 900, 'y': 110, 'terminal_block': 'TB1', 'level': '上段',
                     'terminal': '01', 'wire': '001', 'unit_terminal': 'X0',
                     'peer_tag': 'LS1', 'peer_terminal': '13', 'cable': 'W1', 'core': '3'}]}}

    def test_optional_terminal_plan_keeps_the_original_diagram(self):
        source = self.page(True)
        original = copy.deepcopy(source)
        enabled, _ = gen.build_project({'front_pages': False}, [(source, None)])
        disabled, _ = gen.build_project({'front_pages': False}, [(self.page(False), None)])
        self.assertEqual(source, original)
        self.assertEqual(len(disabled.findall('diagram')), 1)
        self.assertEqual(len(enabled.findall('diagram')), 2)
        for section in ('elements', 'conductors', 'shapes', 'inputs'):
            self.assertEqual(len(enabled.find('diagram/' + section)),
                             len(disabled.find('diagram/' + section)))
        text = '\n'.join(t.get('text', '') for t in enabled.findall('./diagram/inputs/input'))
        for value in ('TB1', '上段', '01', '001', 'PLC1', 'LS1', 'W1'):
            self.assertIn(value, text)

    def test_terminal_plan_is_included_in_contents_and_page_count(self):
        project, _ = gen.build_project({'front_pages': True}, [(self.page(True), None)])
        diagrams = project.findall('diagram')
        last_title = diagrams[-1].get('title')
        self.assertIn('端子', last_title)
        toc = next(page for page in diagrams if page.get('title') == '目次')
        texts = [item.get('text', '') for item in toc.findall('./inputs/input')]
        self.assertIn(last_title, texts)
        self.assertEqual(diagrams[-1].get('order'), str(len(diagrams)))
        self.assertEqual(diagrams[-1].get('folio'), '%id/%total')

    def test_single_communication_unit_keeps_its_tag_in_notes_and_terminal_plan(self):
        page = self.page(True)
        page.update(kind='iqrcomm', right_model='RJ71PB91V', right_tag='NET1')
        page.pop('model')
        page.pop('tag')
        page['wiring']['connections'][0].update(x=60)
        project, _ = gen.build_project({'front_pages': False}, [(page, None)])
        row = terminal_rows([(page, None)])[0]
        self.assertEqual((row['ユニット'], row['タグ名']), ('RJ71PB91V', 'NET1'))
        texts = [item.get('text', '') for item in project.findall('./diagram/inputs/input')]
        self.assertIn('NET1', texts)
        page.update(left_model='RJ71PB91V', left_tag='NET2')
        self.assertEqual(terminal_rows([(page, None)])[0]['タグ名'], '')


if __name__ == '__main__':
    unittest.main()
