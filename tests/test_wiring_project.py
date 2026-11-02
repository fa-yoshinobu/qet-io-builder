import contextlib
import csv
import io
import json
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

import gen_io_page as gen


def body(**values):
    return dict(kind='fx5body', model='FX5S-30MR/DS', tag='PLC1', **values)


class WiringProjectTest(unittest.TestCase):
    def generate(self, folder, pages):
        source, target = Path(folder) / 'project.json', Path(folder) / 'drawing.qet'
        source.write_text(json.dumps({'front_pages': False, 'pages': pages}, ensure_ascii=False), encoding='utf-8')
        with contextlib.redirect_stdout(io.StringIO()):
            gen.main(str(source), str(target))
        return target

    def test_unconfigured_project_keeps_its_layout_and_outputs(self):
        plain, plain_stats = gen.build_project({'front_pages': False}, [(body(), None)])
        empty, empty_stats = gen.build_project({'front_pages': False}, [(body(wiring={}), None)])
        self.assertEqual(plain_stats, empty_stats)
        for tag in ('elements', 'conductors', 'shapes', 'inputs'):
            self.assertEqual(len(plain.find('diagram/' + tag)), len(empty.find('diagram/' + tag)))
        with tempfile.TemporaryDirectory() as folder:
            target = self.generate(folder, [body()])
            self.assertTrue(target.with_name('drawing_iolist.csv').exists())
            self.assertFalse(target.with_name('drawing_terminals.csv').exists())

    def test_annotation_and_terminal_table_use_the_same_explicit_connection(self):
        connection = {'x': 900, 'y': 110, 'terminal_block': 'TB1', 'terminal': '01',
                      'unit_terminal': 'X0', 'wire': '001', 'cable': 'W1', 'core': '3',
                      'peer_tag': 'LS1', 'peer_terminal': '13', 'destination': '5-B3'}
        with tempfile.TemporaryDirectory() as folder:
            target = self.generate(folder, [body(wiring={'connections': [connection]})])
            root = ET.parse(target).getroot()
            text = ET.tostring(root.find('diagram'), encoding='unicode')
            for value in ('TB1', 'LS1', '5-B3', 'W1', 'PLC1'):
                self.assertIn(value, text)
            path = target.with_name('drawing_terminals.csv')
            self.assertTrue(path.read_bytes().startswith(b'\xef\xbb\xbf'))
            with path.open(encoding='utf-8-sig', newline='') as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 1)
            self.assertEqual([rows[0][key] for key in ('タグ名', '端子番号', '線番', '相手機器', '送り先')],
                             ['PLC1', '01', '001', 'LS1', '5-B3'])

    def test_native_reports_link_across_the_actual_generated_pages(self):
        pages = [body(wiring={'connections': [{'x': 900, 'y': 110, 'reference': reference,
                                               'link_id': 'LAN1', 'cable': 'W1'}]})
                 for reference in ('送り', '受け')]
        project, _ = gen.build_project({'front_pages': True}, [(page, None) for page in pages])
        self.assertEqual(project.find('newdiagrams/report').get('label'), '%f-%c%l')
        elements = project.findall('./diagram/elements/element')
        reports = [element for element in elements if element.find('links_uuids/link_uuid') is not None]
        self.assertEqual(len(reports), 2)
        self.assertEqual({element.find('links_uuids/link_uuid').get('uuid') for element in reports},
                         {element.get('uuid') for element in reports})
        self.assertTrue(all(element.findall('./terminals/terminal') for element in reports))

    def test_invalid_split_page_and_missing_peer_do_not_write_a_drawing(self):
        for connection in ({'part': 2, 'wire': '101'}, {'reference': '送り', 'link_id': 'missing'}):
            with self.subTest(connection=connection), tempfile.TemporaryDirectory() as folder:
                with self.assertRaises(SystemExit):
                    self.generate(folder, [body(wiring={'connections': [connection]})])
                self.assertFalse((Path(folder) / 'drawing.qet').exists())


if __name__ == '__main__':
    unittest.main()
