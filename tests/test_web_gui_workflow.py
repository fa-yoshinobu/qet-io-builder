import copy
import json
import tempfile
import unittest
from pathlib import Path

from webgui.api import Api


class WebGuiWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'project.json'
        self.path.write_text(json.dumps({'front_pages': False, 'pages': [
            {'kind': 'iqrbody', 'model': 'R04CPU', 'tag': 'PLC1', 'base_model': 'R35B',
             'power_model': 'R61P', 'modules': ['RX41C4', 'RX41C4']}
        ]}), encoding='utf-8')
        self.api = Api()
        self.api.open_project(str(self.path))
        self.api.page(0)

    def test_batch_creation_is_one_undo_and_redo_including_csv_references(self):
        before = copy.deepcopy(self.api._data)
        made = self.api.create_all_unit_pages(0, True)
        self.assertTrue(made['can_undo'])
        self.assertEqual(len(self.api._undo), 1)
        after = copy.deepcopy(self.api._data)
        self.assertEqual(len(after['pages']), 3)
        undone = self.api.undo()
        self.assertEqual(self.api._data, before)
        self.assertFalse(undone['dirty'])
        self.assertTrue(undone['can_redo'])
        redone = self.api.redo()
        self.assertEqual(self.api._data, after)
        self.assertTrue(redone['dirty'])
        # 取り消しはプロジェクトの参照を戻す。作成済みファイルは削除しない。
        self.assertTrue((self.path.parent / after['pages'][1]['csv']).exists())

    def test_saved_state_dirty_tracking_and_new_edit_discards_redo(self):
        self.api.set_module_tag(0, 0, 0, 'DI1')
        self.api.save()
        self.assertFalse(self.api.snapshot()['dirty'])
        self.assertTrue(self.api.undo()['dirty'])
        self.assertFalse(self.api.redo()['dirty'])
        self.api.undo()
        self.api.set_module_tag(0, 0, 0, 'DI2')
        self.assertFalse(self.api.snapshot()['can_redo'])

    def test_failed_edit_does_not_create_history_or_modify_data(self):
        before = copy.deepcopy(self.api._data)
        result = self.api.set_module(0, 0, 5, 'RX41C4')
        self.assertIn('error', result)
        self.assertEqual(self.api._data, before)
        self.assertFalse(self.api.snapshot()['can_undo'])
        self.assertFalse(self.api.snapshot()['dirty'])

    def test_inline_slot_tag_start_and_model_changes_can_be_undone(self):
        self.api.set_module_tag(0, 0, 0, 'DI1')
        self.api.set_module_start(0, 0, 0, '100')
        self.api.set_module(0, 0, 0, 'RX40C7')
        self.api.undo()
        self.assertEqual(self.api._data['pages'][0]['modules'][0], 'RX41C4')
        self.api.undo()
        self.assertNotIn('module_starts', self.api._data['pages'][0])
        self.api.undo()
        self.assertNotIn('module_tags', self.api._data['pages'][0])

    def test_page_delete_and_move_are_reversible(self):
        self.api.create_all_unit_pages(0)
        before = copy.deepcopy(self.api._data)
        self.api.move_page_to(2, 1)
        self.api.undo()
        self.assertEqual(self.api._data, before)
        self.api.delete_page(1)
        self.api.undo()
        self.assertEqual(self.api._data, before)

    def test_open_and_new_clear_previous_history(self):
        self.api.set_module_tag(0, 0, 0, 'DI1')
        self.api.open_project(str(self.path))
        self.assertFalse(self.api.snapshot()['can_undo'])
        self.api.add_page()
        self.api.new_project()
        self.assertFalse(self.api.snapshot()['can_undo'])
        self.assertFalse(self.api.snapshot()['can_redo'])

    def test_parent_groups_use_model_tag_slot_without_reordering_pages(self):
        self.api.create_all_unit_pages(0)
        self.api.add_page()
        self.api._data['pages'][-1] = {'kind': 'gotbody', 'model': 'GT2510-VTBD'}
        before = copy.deepcopy(self.api._data)
        snap = self.api.snapshot()
        self.assertEqual([p['parent'] for p in snap['pages']], [None, 0, 0, None])
        self.assertEqual(self.api._data, before)
        self.api.move_page_to(1, 0)
        snap = self.api.snapshot()
        self.assertEqual(snap['pages'][0]['parent'], 1)

    def test_parent_groups_distinguish_two_racks_and_right_side_communication(self):
        pages = self.api._data['pages']
        pages[0]['modules'] = ['RJ71PB91V']; pages[0]['module_tags'] = ['NET1']
        pages.extend([
            {'kind': 'iqrcomm', 'right_model': 'RJ71PB91V', 'right_tag': 'NET1'},
            {'kind': 'iqrbody', 'model': 'R04CPU', 'tag': 'PLC2', 'base_model': 'R35B',
             'power_model': 'R61P', 'modules': ['RX41C4']},
            {'kind': 'input', 'model': 'RX41C4', 'slot': '0'},
        ])
        self.assertEqual([p['parent'] for p in self.api.snapshot()['pages']], [None, 0, None, 2])

    def test_overlap_warning_links_to_both_involved_slots(self):
        result = self.api.set_module_start(0, 0, 1, '10')
        warning = next(w for w in result['rack']['alarm_targets'] if '重なっています' in w['text'])
        self.assertEqual({t['id'] for t in warning['targets']}, {'0:0', '0:1'})
        self.assertTrue(all(t['field'] == 'start' for t in warning['targets']))

    def test_extension_warning_uses_global_slot_number_and_stage_local_target(self):
        self.api.add_extension(0, 'R65B', 'R61P')
        self.api.set_module(0, 1, 0, 'RX41C4')
        result = self.api.set_module_start(0, 1, 0, '101')
        warning = next(w for w in result['rack']['alarm_targets'] if '16点(10h)単位' in w['text'])
        self.assertEqual(warning['targets'], [{'id': '1:0', 'label': 'スロット5', 'field': 'start'}])

    def test_invalid_advanced_xy_setting_links_to_settings_without_changing_it(self):
        self.api._data['pages'][0]['module_starts'] = 'invalid'
        page = self.api.page(0)
        warning = next(w for w in page['rack']['alarm_targets'] if '文字列の配列' in w['text'])
        self.assertEqual(warning['targets'][0]['field'], 'extra')
        self.assertEqual(self.api._data['pages'][0]['module_starts'], 'invalid')


if __name__ == '__main__':
    unittest.main()
