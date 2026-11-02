import json
import shutil
import tempfile
import unittest
from pathlib import Path

from webgui.api import Api

class WebGuiTest(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.path = self.folder / 'project.json'
        self.path.write_text(json.dumps({'front_pages': False, 'pages': [
            {'kind': 'iqrbody', 'model': 'R04CPU', 'tag': 'PLC1', 'base_model': 'R35B',
             'power_model': 'R61P', 'modules': ['RJ71PB91V', 'RJ71PB91V', 'RX41C4', 'RY41NT2P'],
             'module_tags': ['NET-A', 'NET-B', 'DI1', 'DO1']},
            {'kind': 'iqrcomm', 'right_model': 'RJ71PB91V', 'right_tag': 'NET-B'},
            {'kind': 'iqrcomm', 'right_model': 'RJ71PB91V', 'right_tag': 'NET-A'},
        ]}), encoding='utf-8')
        self.api = Api()
        self.assertNotIn('error', self.api.open_project(str(self.path)))

    def tearDown(self):
        shutil.rmtree(self.folder, ignore_errors=True)

    def saved(self):
        self.assertNotIn('error', self.api.save())
        return json.loads(self.path.read_text(encoding='utf-8'))

    def items(self, result, stage=0):
        return {item['id']: item for item in result['rack']['stages'][stage]['items']}

    def test_rack_addresses_follow_slot_order(self):
        page = self.api.page(0)
        items = self.items(page)
        self.assertEqual(items['0:0']['addr'], 'X/Y000〜X/Y01F')
        self.assertEqual(items['0:2']['addr'], 'X040〜X05F')
        self.assertEqual(items['0:3']['addr'], 'Y060〜Y07F')
        self.assertEqual(items['0:4']['model'], '')
        self.assertEqual(page['rack']['slots_total'], 5)

    def test_module_is_placed_in_the_chosen_slot_and_saved(self):
        result = self.api.set_module(0, 0, 4, 'RX40C7')
        self.assertNotIn('error', result)
        self.assertNotIn('error', self.api.set_module_tag(0, 0, 4, 'DI2'))
        page = self.saved()['pages'][0]
        self.assertEqual(page['modules'][4], 'RX40C7')
        self.assertEqual(page['module_tags'][4], 'DI2')

    def test_removing_keeps_positions_of_other_slots(self):
        self.api.remove_module(0, 0, 1)
        page = self.saved()['pages'][0]
        self.assertEqual(page['modules'][:3], ['RJ71PB91V', '', 'RX41C4'])
        self.assertEqual(page['module_tags'][1], '')

    def test_slot_limit_and_two_slot_units_are_checked(self):
        self.assertIn('error', self.api.set_module(0, 0, 5, 'RX40C7'))
        self.assertIn('error', self.api.set_module(0, 0, 4, 'R60AD16-G'))
        self.assertIn('error', self.api.set_module(0, 0, 4, 'Q62AD-DGH'))

    def test_unit_page_is_created_from_slot(self):
        self.api.set_module(0, 0, 4, 'RX40C7')
        self.api.set_module_tag(0, 0, 4, 'DI2')
        kinds = self.api.unit_pages(0, 0, 4)['kinds']
        self.assertIn('input', [k for k, _ in kinds])
        result = self.api.create_unit_page(0, 0, 4, 'input')
        page = self.saved()['pages'][result['index']]
        self.assertEqual((page['kind'], page['model'], page['tag']), ('input', 'RX40C7', 'DI2'))

    def test_communication_page_uses_right_side(self):
        result = self.api.create_unit_page(0, 0, 1, 'iqrcomm')
        page = self.api.page(result['index'])['values']
        self.assertEqual((page['right_model'], page['right_tag'], page['right_slot']), ('RJ71PB91V', 'NET-B', '1'))

    def test_extension_base_and_its_slots(self):
        result = self.api.add_extension(0, 'R65B', 'R61P')
        self.assertNotIn('error', result)
        self.assertEqual(result['rack']['slots_total'], 10)
        self.assertEqual(self.items(result, 1)['1:0']['head'], '5')
        self.assertNotIn('error', self.api.set_module(0, 1, 0, 'RY40NT5P'))
        page = self.saved()['pages'][0]
        self.assertEqual(page['extensions'][0]['modules'], ['RY40NT5P'])
        self.assertIn('error', self.api.add_extension(0, 'R35B', 'R61P'))

    def test_maker_change_clears_lower_choices(self):
        values = self.api.page(0)['values']
        values['series'] = 'q'
        result = self.api.update_page(0, values, '', 'series')
        self.assertEqual(result['values']['kind'], '')
        self.assertEqual(result['values']['model'], '')
        self.assertIn('qbody', [k for k, _ in result['options']['kind']])

    def test_extra_settings_cannot_override_fields(self):
        values = self.api.page(1)['values']
        self.assertIn('error', self.api.update_page(1, values, '{"right_model": "X"}'))
        self.assertNotIn('error', self.api.update_page(1, values, '{"empty_slot_points": 32}'))

    def test_page_without_kind_is_not_saved(self):
        self.api.add_page()
        result = self.api.save()
        self.assertIn('種類', result['error'])

    def test_catalog_lists_modules_with_drawing_pages(self):
        rows = {r['model']: r for r in self.api.catalog('modules', 0)['rows']}
        self.assertEqual(rows['R60AD16-G']['slots'], 2)
        self.assertIn('入力', rows['RX41C4']['summary'])
        self.assertTrue(rows['RX41C4']['pages'])
        parts = {r['model'] for r in self.api.catalog('standard_model')['rows']}
        self.assertIn('S8VK-G01524', parts)

    def test_wiring_is_validated_and_stored(self):
        self.assertIn('error', self.api.set_wiring(1, {'connections': [{'part': 0}]}))
        result = self.api.set_wiring(1, {'connections': [{'terminal_block': 'TB1', 'terminal': '1'}], 'terminal_plan': True})
        self.assertNotIn('error', result)
        self.assertEqual(self.saved()['pages'][1]['wiring']['connections'][0]['terminal_block'], 'TB1')

    def test_check_and_generate_use_the_generator(self):
        self.assertNotIn('error', self.api.check())
        out = self.folder / 'out.qet'
        result = self.api.generate(str(out))
        self.assertTrue(result.get('ok'), result)
        self.assertTrue(out.exists())
        again = self.api.generate(str(out))
        self.assertIn('confirm', again)

    def test_save_as_asks_when_folder_changes(self):
        other = self.folder / 'sub'
        other.mkdir()
        result = self.api.save_as(str(other / 'copy.json'))
        self.assertIn('confirm', result)
        self.assertNotIn('error', self.api.save_as(result['path'], True))
        self.assertTrue((other / 'copy.json').exists())

    def test_unit_page_gets_start_address_from_configuration(self):
        result = self.api.create_unit_page(0, 0, 3, 'output')
        page = self.saved()['pages'][result['index']]
        self.assertEqual((page['model'], page['start'], page['slot']), ('RY41NT2P', '60', '3'))

    def test_all_unit_pages_with_csv_pass_the_generator_check(self):
        self.api.set_module(0, 0, 4, 'RH42C4NT2P')
        self.api.save()
        result = self.api.create_all_unit_pages(0, True)
        self.assertIn('3ページ', result['message'])
        self.assertTrue((self.folder / 'DI1.csv').exists())
        self.assertTrue((self.folder / 'RH42C4NT2P_out.csv').exists())
        first = (self.folder / 'DO1.csv').read_text(encoding='utf-8-sig').splitlines()[1]
        self.assertTrue(first.startswith('Y60,'))
        self.assertNotIn('error', self.api.check())
        again = self.api.create_all_unit_pages(0, True)
        self.assertIn('0ページ', again['message'])

    def test_existing_csv_is_not_overwritten(self):
        (self.folder / 'DI1.csv').write_text('アドレス,信号名\n', encoding='utf-8')
        result = self.api.create_unit_page(0, 0, 2, 'input')
        made = self.api.make_page_csv(result['index'])
        self.assertIn('上書きせず', made['message'])
        self.assertEqual((self.folder / 'DI1.csv').read_text(encoding='utf-8'), 'アドレス,信号名\n')

    def test_io_page_without_csv_is_generated_with_blank_names(self):
        self.api.create_unit_page(0, 0, 2, 'input')
        self.saved()
        self.assertNotIn('error', self.api.check())

    def test_page_can_be_moved_to_any_position(self):
        result = self.api.move_page_to(2, 0)
        self.assertEqual(result['index'], 0)
        pages = self.saved()['pages']
        self.assertEqual([p.get('right_tag', p.get('tag')) for p in pages], ['NET-A', 'PLC1', 'NET-B'])

    def test_manual_start_is_kept_and_odd_assignment_only_warns(self):
        self.assertIn('error', self.api.set_module_start(0, 0, 2, 'X40'))
        result = self.api.set_module_start(0, 0, 3, '48')
        items = self.items(result)
        self.assertEqual(items['0:3']['addr'], 'Y048〜Y067')
        self.assertTrue(items['0:3']['manual'])
        self.assertTrue(items['0:2']['alarm'] and items['0:3']['alarm'])
        alarms = '\n'.join(result['rack']['alarms'])
        self.assertIn('16点(10h)単位', alarms)
        self.assertIn('重なっています', alarms)
        self.assertEqual(items['0:4']['addr'], '068〜077')
        page = self.saved()['pages'][0]
        self.assertEqual(page['module_starts'], ['', '', '', '48'])
        self.assertIn('警告', self.api.check()['message'])

    def test_unit_page_uses_manual_start_and_mismatch_is_reported(self):
        self.api.set_module_start(0, 0, 2, '100')
        result = self.api.create_unit_page(0, 0, 2, 'input')
        self.assertEqual(self.api.page(result['index'])['values']['start'], '100')
        self.api.set_module_start(0, 0, 2, '200')
        alarms = self.api.page(0)['rack']['alarms']
        self.assertTrue(any('DI1 のページの先頭アドレス 100' in a for a in alarms))
        self.assertEqual(self.api.page(result['index'])['values']['start'], '100')

    def test_methods_return_json_data(self):
        for result in (self.api.meta(), self.api.snapshot(), self.api.page(0), self.api.catalog('modules', 0)):
            json.dumps(result, ensure_ascii=False)

    def test_got_summaries_show_screen_resolution_and_supply_without_raw_dicts(self):
        import gen_io_page as gen
        expected = {
            'GT2103-PMBD': '3.8型 / 320x128 / DC24V',
            'GT2510-VTBD': '10.4型 / 640x480 / DC24V',
            'GT3708-XRBA': '8.4型 / 1024x768 / AC100-240V',
            'GT3715-FHCBD': '15.6型ワイド / 1920x1080 / DC24V',
        }
        for model, summary in expected.items():
            self.assertEqual(self.api._describe('got_body', gen.GOT_BODY[model], model), summary)
        for model, spec in gen.GOT_BODY.items():
            summary = self.api._describe('got_body', spec, model)
            self.assertEqual(summary.count('型'), 1, model)
            self.assertNotIn('{', summary, model)
            self.assertNotIn('supply', summary, model)

    def test_got_catalog_uses_formatted_summaries(self):
        self.api._data['pages'] = [{'kind': 'gotbody', 'model': 'GT3708-XRBA'}]
        rows = {row['model']: row['summary'] for row in self.api.catalog('model', 0)['rows']}
        self.assertEqual(rows['GT3708-XRBA'], '8.4型 / 1024x768 / AC100-240V')

    def test_catalog_shows_production_end_year_and_planned_status(self):
        from datetime import date
        from webgui.api import production_end_label

        today = date(2026, 10, 30)
        self.assertEqual(production_end_label({}, today), '')
        self.assertEqual(production_end_label({'production_end_date': '2023-03-31'}, today), '2023年')
        self.assertEqual(production_end_label({'production_end_date': '2029-12-31'}, today), '2029年予定')
        self.assertEqual(production_end_label({'production_end_date': '2026-10-30'}, today), '2026年')
        self.api._data['pages'] = [{'kind': 'qbody', 'model': 'Q03UDVCPU'}]
        rows = {r['model']: r for r in self.api.catalog('power_model', 0)['rows']}
        self.assertEqual(rows['Q64P']['production_end'], '2010年')
        self.assertTrue(rows['Q61P']['production_end'].startswith('2029年'))
        self.api._data['pages'] = [{'kind': 'remotebody', 'model': 'NZ2GF12A4-16D'}]
        rows = {r['model']: r for r in self.api.catalog('model', 0)['rows']}
        self.assertEqual(rows['NZ2GF12A4-16D']['production_end'], '2023年')
        self.assertEqual(rows['NZ2GN12A4-16D']['production_end'], '')

    def test_repeated_untagged_modules_get_separate_pages_and_are_not_duplicated(self):
        self.api._data['pages'] = [{'kind': 'iqrbody', 'model': 'R04CPU', 'base_model': 'R35B',
                                   'power_model': 'R61P', 'modules': ['RX41C4', 'RX41C4']}]
        result = self.api.create_all_unit_pages(0, True)
        self.assertIn('2ページ', result['message'])
        pages = self.saved()['pages'][1:]
        self.assertEqual([(p['slot'], p['start']) for p in pages], [('0', '0'), ('1', '20')])
        self.assertNotEqual(pages[0]['csv'], pages[1]['csv'])
        self.assertIn('0ページ', self.api.create_all_unit_pages(0)['message'])
        self.assertNotIn('error', self.api.check())

    def test_smaller_base_and_en_cpu_do_not_hide_modules_or_mutate_configuration(self):
        import copy
        self.api._data['pages'] = [{'kind': 'iqrbody', 'model': 'R04CPU', 'base_model': 'R38B',
                                   'power_model': 'R61P', 'modules': ['RX41C4'] * 8}]
        original = copy.deepcopy(self.api._data)
        values = self.api.page(0)['values']
        values['base_model'] = 'R35B'
        self.assertIn('収まりません', self.api.update_page(0, values, '', 'base_model')['error'])
        self.assertEqual(self.api._data, original)
        values['base_model'] = 'R38B'; values['model'] = 'R04ENCPU'
        self.assertIn('error', self.api.update_page(0, values, '', 'model'))
        self.assertEqual(self.api._data, original)
        self.api.add_extension(0, 'R68B', 'R61P')
        for slot in range(8):
            self.api.set_module(0, 1, slot, 'RX41C4')
        original = copy.deepcopy(self.api._data)
        self.assertIn('error', self.api.set_stage_part(0, 1, 'base_model', 'R65B'))
        self.assertEqual(self.api._data, original)

    def test_fx5_board_candidates_and_additions_follow_cpu_and_occupied_board(self):
        self.api._data['pages'] = [{'kind': 'fx5body', 'model': 'FX5UC-32MT/D'}]
        self.assertNotIn('FX5-485-BD', [r['model'] for r in self.api.catalog('modules', 0)['rows']])
        self.assertIn('error', self.api.set_module(0, 0, 0, 'FX5-485-BD'))
        self.api._data['pages'][0]['model'] = 'FX5U-32MR/ES'
        self.assertNotIn('error', self.api.set_module(0, 0, 0, 'FX5-485-BD'))
        self.assertIn('error', self.api.set_module(0, 0, 1, 'FX5-485-BD'))
        self.assertNotIn('FX5-485-BD', [r['model'] for r in self.api.catalog('modules', 0)['rows']])
        self.assertEqual(self.api._data['pages'][0]['modules'], ['FX5-485-BD'])
        values = self.api.page(0)['values']; values['board_model'] = 'FX5-3A-BD'
        self.assertIn('error', self.api.update_page(0, values, '', 'board_model'))
        self.assertNotIn('board_model', self.api._data['pages'][0])

    def test_cpu_change_clears_incompatible_fx5_board(self):
        self.api._data['pages'] = [dict(kind='fx5body', model='FX5S-30MR/ES', board_model='FX5-SDCD', board_tag='BD1')]
        values = self.api.page(0)['values']; values['model'] = 'FX5U-32MR/ES'
        result = self.api.update_page(0, values, '', 'model')
        self.assertNotIn('error', result)
        self.assertNotIn('board_model', self.api._data['pages'][0])
        self.assertNotIn('board_tag', self.api._data['pages'][0])

    def test_got_module_is_cleared_when_unit_has_no_module_interface(self):
        self.api._data['pages'] = [dict(kind='gotoption', left_model='GT25-FNADP', left_module='ABCC-M40-DPV1')]
        values = self.api.page(0)['values']; values['left_model'] = 'GT15-RS2-9P'
        result = self.api.update_page(0, values, '', 'left_model')
        self.assertNotIn('error', result)
        self.assertNotIn('left_module', result['visible'])
        self.assertNotIn('left_module', self.api._data['pages'][0])

    def test_cpu_change_cannot_exceed_extension_stage_limit(self):
        import copy
        self.api._data['pages'] = [dict(kind='qbody', model='Q03UDVCPU', base_model='Q38B', power_model='Q61P',
                                       extensions=[dict(base_model='Q68B', power_model='Q61P', modules=[]) for _ in range(5)])]
        original = copy.deepcopy(self.api._data)
        values = self.api.page(0)['values']; values['model'] = 'Q00UCPU'
        self.assertIn('error', self.api.update_page(0, values, '', 'model'))
        self.assertEqual(self.api._data, original)

    def test_cpu_change_clears_incompatible_sd_model_but_preserves_free_text(self):
        for selected, expected in [('L1MEM-4GBSD', ''), ('NZ1MEM-4GBSD', 'NZ1MEM-4GBSD'), ('案件指定SD', '案件指定SD')]:
            self.api._data['pages'] = [{'kind': 'iqrbody', 'model': 'R04CPU', 'base_model': 'R35B',
                                       'power_model': 'R61P', 'sd_card': '有', 'sd_card_model': selected}]
            values = self.api.page(0)['values']; values['model'] = 'R04ENCPU'
            result = self.api.update_page(0, values, '', 'model')
            self.assertNotIn('error', result)
            self.assertEqual(result['values']['sd_card_model'], expected)
            self.assertEqual(self.saved()['pages'][0].get('sd_card_model', ''), expected)
            self.assertNotIn('error', self.api.check())


if __name__ == '__main__':
    unittest.main()
