import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from webgui.api import Api


class DetailComparisonTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.path = self.folder / 'project.json'
        self.path.write_text(json.dumps({'front_pages': False, 'pages': [
            {'kind': 'iqrbody', 'model': 'R04CPU', 'base_model': 'R35B', 'power_model': 'R61P',
             'modules': ['RX41C4', 'RY41NT2P'], 'module_tags': ['DI1', 'DO1']}
        ]}), encoding='utf-8')
        self.api = Api(); self.api.open_project(str(self.path))
        self.api.create_all_unit_pages(0, True)
        self.api.save()

    def test_matching_details_have_no_differences(self):
        self.assertEqual(self.api.detail_differences()['rows'], [])
        self.api._data['pages'][1]['start'] = '000'
        self.assertEqual(self.api.detail_differences()['rows'], [])

    def test_selected_sync_and_undo_preserve_other_pages_and_all_csv_bytes(self):
        self.api.set_module_tag(0, 0, 0, 'DI-NEW')
        self.api.set_module_start(0, 0, 0, '100')
        before = copy.deepcopy(self.api._data)
        csvs = {p: p.read_bytes() for p in self.folder.glob('*.csv')}
        rows = self.api.detail_differences()['rows']
        selected = next(row for row in rows if row['page'] == 1)
        self.assertEqual({c['key'] for c in selected['changes']}, {'tag', 'start'})
        result = self.api.sync_details([selected])
        self.assertNotIn('error', result)
        self.assertEqual(self.api._data['pages'][1]['tag'], 'DI-NEW')
        self.assertEqual(self.api._data['pages'][1]['start'], '100')
        self.assertEqual(self.api._data['pages'][2], before['pages'][2])
        self.assertEqual({p: p.read_bytes() for p in csvs}, csvs)
        self.api.undo()
        self.assertEqual(self.api._data, before)

    def test_model_mismatch_is_fixable_only_for_a_compatible_page_kind(self):
        self.api._data['pages'][1]['model'] = 'RX40C7'
        row = self.api.detail_differences()['rows'][0]
        self.assertTrue(row['can_sync'])
        self.assertEqual(row['expected']['model'], 'RX41C4')
        self.api.set_module(0, 0, 0, 'RY41NT2P')
        row = next(r for r in self.api.detail_differences()['rows'] if r['page'] == 1)
        self.assertFalse(row['can_sync'])
        before = copy.deepcopy(self.api._data)
        self.assertIn('error', self.api.sync_details([row]))
        self.assertEqual(self.api._data, before)

    def test_ambiguous_module_and_stale_selection_are_not_applied(self):
        self.api.set_module_tag(0, 0, 0, 'NEW')
        stale = self.api.detail_differences()['rows'][0]
        self.api.set_module_tag(0, 0, 0, 'NEWER')
        before = copy.deepcopy(self.api._data)
        self.assertIn('error', self.api.sync_details([stale]))
        self.assertEqual(self.api._data, before)
        self.api._data['pages'][0].update(modules=['RX41C4', 'RX41C4'], module_tags=[])
        self.api._data['pages'][1].pop('slot', None)
        self.api._data['pages'][1].pop('tag', None)
        row = next(r for r in self.api.detail_differences()['rows'] if r['page'] == 1)
        self.assertFalse(row['can_sync'])
        self.assertIn('一意', row['reason'])

    def test_left_and_right_communication_sides_are_compared_separately(self):
        self.api._data['pages'] = [
            dict(self.api._data['pages'][0], modules=['RJ71PB91V', 'RJ71PB91V'], module_tags=['NET-A', 'NET-B']),
            {'kind': 'iqrcomm', 'left_model': 'RJ71PB91V', 'left_tag': 'OLD', 'left_slot': '0',
             'right_model': 'RJ71PB91V', 'right_tag': 'NET-B', 'right_slot': '8'}]
        rows = self.api.detail_differences()['rows']
        self.assertEqual(len(rows), 2)
        self.assertNotIn('error', self.api.sync_details(rows))
        detail = self.api._data['pages'][1]
        self.assertEqual((detail['left_tag'], detail['right_slot']), ('NET-A', '1'))

    def test_csv_open_resolves_project_relative_path_without_changing_it(self):
        csv = self.folder / self.api._data['pages'][1]['csv']
        before = csv.read_bytes()
        with patch.object(self.api, 'open_file', return_value={'ok': True}) as opener:
            result = self.api.open_csv(1, 'csv')
            self.assertTrue(result['ok'])
            opener.assert_called_once_with(str(csv.resolve()))
        self.assertEqual(csv.read_bytes(), before)
        self.assertFalse(self.api.snapshot()['dirty'])
        self.api._data['pages'][1]['csv'] = 'missing.csv'
        self.assertIn('error', self.api.open_csv(1, 'csv'))
        self.assertIn('error', self.api.open_csv(1, 'model'))

    def test_csv_recheck_reads_external_edits_each_time(self):
        csv = self.folder / self.api._data['pages'][1]['csv']
        before = csv.read_bytes()
        self.assertNotIn('error', self.api.check())
        csv.write_text('アドレス,信号名\nX999,テスト\n', encoding='utf-8-sig')
        self.assertIn('error', self.api.check())
        csv.write_bytes(before)
        self.assertNotIn('error', self.api.check())


if __name__ == '__main__':
    unittest.main()
