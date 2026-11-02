import copy
import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from project_wiring import data as wiring


class WiringDataTest(unittest.TestCase):
    def test_unspecified_and_empty_settings_get_independent_lists(self):
        self.assertEqual(wiring.normalize(None), {'terminal_plan': False, 'boundaries': [], 'connections': []})
        first = wiring.normalize({})
        first['connections'].append({})
        self.assertEqual(wiring.normalize({}), {'terminal_plan': False, 'boundaries': [], 'connections': []})

    def test_terminal_plan_requires_a_boolean(self):
        self.assertTrue(wiring.normalize({'terminal_plan': True})['terminal_plan'])
        for value in (1, 0, 'true', None, [], {}):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'trueまたはfalse'):
                wiring.normalize({'terminal_plan': value})

    def test_defaults_and_supplied_values_are_copied_without_changing_source(self):
        source = {'boundaries': [{}], 'connections': [{'unit_tag': 'PLC1', 'purpose': ' 上限LS '} ]}
        original = copy.deepcopy(source)
        result = wiring.normalize(source)
        self.assertEqual(result['boundaries'][0], {'part': 1, 'x': 240, 'top': 75, 'bottom': 750,
                                                   'left': '盤外', 'right': '盤内'})
        self.assertEqual((result['connections'][0]['part'], result['connections'][0]['x'],
                          result['connections'][0]['y']), (1, 95, 110))
        self.assertEqual(result['connections'][0]['peer_tag'], '')
        self.assertEqual(result['connections'][0]['purpose'], ' 上限LS ')
        result['connections'][0]['unit_tag'] = 'changed'
        result['boundaries'][0]['left'] = 'changed'
        self.assertEqual(source, original)

    def test_unknown_keys_and_invalid_containers_are_rejected(self):
        for value in ([], 'wiring', {'other': []}, {'connections': None}, {'boundaries': {}},
                      {'connections': [None]}, {'boundaries': ['line']},
                      {'connections': [{'terminal_bock': 'TB1'}]}, {'boundaries': [{'y': 10}]}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                wiring.normalize(value)

    def test_part_and_coordinate_types_ranges_and_finite_values(self):
        for part in (0, -1, 1.0, True, '1', None):
            with self.subTest(part=part), self.assertRaisesRegex(ValueError, '分割頁'):
                wiring.normalize({'connections': [{'part': part}]})
        for key in ('x', 'y'):
            limit = 1260 if key == 'x' else 800
            for number in (-1, limit + 1, float('nan'), float('inf'), float('-inf'), 10 ** 1000, True, '95', None):
                with self.subTest(key=key, number=number), self.assertRaisesRegex(ValueError, '有限数'):
                    wiring.normalize({'connections': [{key: number}]})
        valid = wiring.normalize({'connections': [{'part': 2, 'x': 1260, 'y': 0.5}]})
        self.assertEqual(valid['connections'][0]['y'], 0.5)
        self.assertEqual(wiring.normalize({'connections': [{'x': 0, 'y': 800}]})['connections'][0]['y'], 800)

    def test_boundary_coordinates_and_order_are_checked(self):
        for record in ({'x': 1261}, {'top': -1}, {'bottom': 801}, {'top': 500, 'bottom': 500},
                       {'top': 700, 'bottom': 600}, {'bottom': float('nan')}, {'left': None}):
            with self.subTest(record=record), self.assertRaises(ValueError):
                wiring.normalize({'boundaries': [record]})
        self.assertEqual(wiring.normalize({'boundaries': [{'top': 0, 'bottom': 800}]})['boundaries'][0]['bottom'], 800)

    def test_connection_strings_and_reference_values_are_checked(self):
        keys = [key for key, value in wiring.CONNECTION_DEFAULTS.items() if isinstance(value, str)]
        for key in keys:
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, '文字列'):
                wiring.normalize({'connections': [{key: 1}]})
        with self.assertRaisesRegex(ValueError, '空欄・送り・受け'):
            wiring.normalize({'connections': [{'reference': '送信'}]})
        for reference in ('', '送り', '受け'):
            result = wiring.normalize({'connections': [{'reference': reference}]})
            self.assertEqual(result['connections'][0]['reference'], reference)
            self.assertEqual(result['connections'][0]['link_id'], '')

    def test_terminal_rows_include_only_explicit_terminal_pairs_and_keep_duplicates(self):
        connection = {'terminal_block': 'TB1', 'terminal': '1', 'wire': '101', 'purpose': '上限LS'}
        page = {'model': 'RX40C7', 'tag': 'PLC1', 'wiring': {'connections': [connection, dict(connection),
                {'terminal_block': 'TB1'}, {'terminal': '2'}, {'terminal_block': ' ', 'terminal': '3'},
                {'terminal_block': 'TB1', 'terminal': ' '}, {}]}}
        original = copy.deepcopy(page)
        rows = wiring.terminal_rows([(page, [{'端子台番号': '1', '線番': 'existing'}])])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0], rows[1])
        self.assertEqual((rows[0]['ユニット'], rows[0]['タグ名'], rows[0]['分割頁']), ('RX40C7', 'PLC1', '1'))
        self.assertEqual((rows[0]['線番'], rows[0]['相手機器'], rows[0]['送り先']), ('101', '', ''))
        self.assertEqual(page, original)
        self.assertEqual(wiring.terminal_rows([({'model': 'RX40C7'}, [])]), [])

    def test_terminal_rows_sort_naturally_and_export_all_explicit_fields(self):
        connection = {'part': 2, 'unit_tag': 'PLC2', 'unit_terminal': 'B20', 'terminal_block': 'TB2',
                      'terminal': '10', 'wire': '001', 'purpose': '確認', 'peer_tag': 'LS1',
                      'peer_terminal': '2', 'destination': '装置側', 'cable': 'W1', 'core': '01',
                      'section': '0.75', 'shield': '片端接地', 'jumper': '1-2', 'reference': '送り', 'link_id': 'PAIR1'}
        records = [dict(connection, terminal_block='TB10', terminal='1'), connection,
                   dict(connection, terminal='2'), dict(connection, terminal_block='TB1', terminal='1')]
        rows = wiring.terminal_rows([({'model': 'RX40C7', 'tag': 'PLC1', 'wiring': {'connections': records}}, None)])
        self.assertEqual([(row['端子台'], row['端子番号']) for row in rows],
                         [('TB1', '1'), ('TB2', '2'), ('TB2', '10'), ('TB10', '1')])
        self.assertEqual(list(rows[2]), list(wiring.CSV_COLUMNS))
        self.assertEqual(list(rows[2].values()), ['RX40C7', 'PLC2', '2', 'TB2', '', '10', 'B20', '001',
                                                '確認', 'LS1', '2', '装置側', 'W1', '01', '0.75', '片端接地', '1-2'])

    def test_terminal_levels_with_the_same_number_remain_distinct(self):
        records = [{'terminal_block': 'TB1', 'level': level, 'terminal': terminal, 'wire': wire}
                   for level, terminal, wire in [('下段', '1', '102'), ('上段', '2', '103'), ('上段', '1', '101')]]
        rows = wiring.terminal_rows([({'wiring': {'connections': records}}, None)])
        self.assertEqual([(row['端子段'], row['端子番号'], row['線番']) for row in rows],
                         [('上段', '1', '101'), ('上段', '2', '103'), ('下段', '1', '102')])

    def test_csv_has_bom_and_preserves_string_data_and_quoted_text(self):
        page = {'wiring': {'connections': [{'terminal_block': 'TB1', 'terminal': '01', 'wire': '001',
                                           'purpose': '位置,"確認"\n2行目'}]}}
        rows = wiring.terminal_rows([(page, None)])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'terminals.csv'
            wiring.write_terminal_csv(path, rows)
            self.assertTrue(path.read_bytes().startswith(b'\xef\xbb\xbf'))
            with path.open(encoding='utf-8-sig', newline='') as stream:
                self.assertEqual(list(csv.DictReader(stream)), rows)
            self.assertEqual(list(Path(folder).iterdir()), [path])

    def test_failed_csv_replace_preserves_output_and_removes_temporary_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'terminals.csv'
            path.write_bytes(b'previous CSV')
            with patch.object(wiring.os, 'replace', side_effect=PermissionError('locked')):
                with self.assertRaises(PermissionError):
                    wiring.write_terminal_csv(path, [])
            self.assertEqual(path.read_bytes(), b'previous CSV')
            self.assertEqual(list(Path(folder).iterdir()), [path])


if __name__ == '__main__':
    unittest.main()
