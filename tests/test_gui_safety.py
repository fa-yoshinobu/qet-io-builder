import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import gen_io_page as gen
import gui


class GuiSafetyTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.app = gui.App()
        self.app.withdraw()
        self.addCleanup(self.app.destroy)
        self.app.path = Path(self.folder.name) / 'project.json'

    def show_pages(self, pages):
        self.app.data = gen.project_config({'pages': pages, 'front_pages': False})
        self.app.show_project()
        if pages:
            self.app.show_page(0)

    def dialog(self):
        return next(widget for widget in self.app.winfo_children() if isinstance(widget, gui.tk.Toplevel))

    def choose_model(self, dialog, model):
        controls = dialog.winfo_children()[0].winfo_children()
        boxes = [widget for widget in controls if isinstance(widget, gui.ttk.Combobox)]
        boxes[2].set(model)
        next(widget for widget in controls if isinstance(widget, gui.ttk.Button)).invoke()

    def select_module(self, model):
        dialog = self.dialog()
        controls = dialog.winfo_children()[0].winfo_children()
        units = next(widget for widget in controls if isinstance(widget, gui.tk.Listbox))
        units.selection_set(units.get(0, 'end').index(model))
        next(widget for widget in controls if isinstance(widget, gui.ttk.Button)).invoke()

    def test_failed_encoding_preserves_existing_project(self):
        original = '{"pages":[],"vendor_note":"\\ud800"}'
        self.app.path.write_text(original, encoding='utf-8')
        self.app.data = json.loads(original)
        self.app.show_project()
        self.app.dirty = True
        with patch.object(self.app, 'report') as report:
            self.assertFalse(self.app.save())
        self.assertIsInstance(report.call_args.args[0], UnicodeEncodeError)
        self.assertEqual(self.app.path.read_text(encoding='utf-8'), original)
        self.assertEqual(list(Path(self.folder.name).iterdir()), [self.app.path])
        self.assertTrue(self.app.dirty)

    def test_failed_replace_preserves_existing_project_and_removes_temporary_file(self):
        self.app.path.write_text('original contents', encoding='utf-8')
        self.show_pages([])
        self.app.project_vars['project_title'].set('変更')
        with patch('gui.os.replace', side_effect=PermissionError('locked')), patch.object(self.app, 'report'):
            self.assertFalse(self.app.save())
        self.assertEqual(self.app.path.read_text(encoding='utf-8'), 'original contents')
        self.assertEqual(list(Path(self.folder.name).iterdir()), [self.app.path])
        self.assertTrue(self.app.dirty)

    def test_successful_save_replaces_the_existing_project(self):
        self.app.path.write_text('old contents', encoding='utf-8')
        self.show_pages([])
        self.app.project_vars['project_title'].set('保存した図面')
        self.assertTrue(self.app.save())
        self.assertEqual(json.loads(self.app.path.read_text(encoding='utf-8'))['project_title'], '保存した図面')
        self.assertFalse(self.app.dirty)
        self.assertEqual(list(Path(self.folder.name).iterdir()), [self.app.path])

    def test_invalid_open_keeps_path_data_and_unsaved_form(self):
        self.show_pages([{'kind': 'fx5body', 'model': 'FX5U-32MR/ES'}])
        self.app.vars['tag'].set('未保存タグ')
        self.app.project_vars['project_title'].set('未保存の題名')
        self.app.extra.delete('1.0', 'end')
        self.app.extra.insert('1.0', '{未完成')
        old_path, old_data = self.app.path, self.app.data
        location = self.app.location.cget('text')
        candidate = Path(self.folder.name) / 'bad.json'
        cases = [{'pages': [], 'power': None}, {'pages': [], 'power': []},
                 {'pages': [], 'power': '24V'}, {'pages': [], 'front_pages': 'invalid'},
                 {'pages': [], 'project_title': []}, {'pages': [{'kind': []}]},
                 {'pages': [], 'project_title': '\ud800'}, {'pages': [{'kind': 'fx5body', 'tag': '\ud800'}]}]
        for value in cases:
            with self.subTest(value=value):
                original = json.dumps(value)
                candidate.write_text(original, encoding='utf-8')
                with patch.object(self.app, 'confirm_discard', return_value=True), \
                        patch('gui.filedialog.askopenfilename', return_value=str(candidate)), \
                        patch.object(self.app, 'report') as report:
                    self.app.open()
                report.assert_called_once()
                self.assertEqual(self.app.path, old_path)
                self.assertIs(self.app.data, old_data)
                self.assertEqual(self.app.index, 0)
                self.assertEqual(self.app.vars['tag'].get(), '未保存タグ')
                self.assertEqual(self.app.project_vars['project_title'].get(), '未保存の題名')
                self.assertEqual(self.app.extra.get('1.0', 'end-1c'), '{未完成')
                self.assertEqual(self.app.location.cget('text'), location)
                self.assertTrue(self.app.dirty)
                self.assertEqual(candidate.read_text(encoding='utf-8'), original)

    def test_successful_open_updates_the_project(self):
        candidate = Path(self.folder.name) / 'new.json'
        candidate.write_text(json.dumps({'pages': [], 'project_title': '新しい図面'}), encoding='utf-8')
        with patch('gui.filedialog.askopenfilename', return_value=str(candidate)):
            self.app.open()
        self.assertEqual(self.app.path, candidate)
        self.assertEqual(self.app.project_vars['project_title'].get(), '新しい図面')
        self.assertFalse(self.app.dirty)

    def test_fx5uc_collect_drops_the_hidden_board_and_keeps_other_hidden_settings(self):
        self.show_pages([{'kind': 'fx5body', 'model': 'FX5U-32MR/ES', 'board_model': 'FX5-485-BD',
                          'board_tag': 'BOARD1', 'left_station': '3'}])
        self.app.vars['model'].set('FX5UC-32MT/D')
        page = self.app.collect()['pages'][0]
        self.assertNotIn('board_model', page)
        self.assertNotIn('board_tag', page)
        self.assertEqual(page['left_station'], '3')
        self.assertEqual(page['model'], 'FX5UC-32MT/D')

    def test_got_collect_drops_only_options_the_current_model_does_not_support(self):
        self.show_pages([{'kind': 'gotbody', 'model': 'GT2715-XTBA', 'battery': '装着',
                          'sd_card': '有', 'sd_card_model': 'NZ1MEM-4GBSD', 'serial_mode': 'RS-232',
                          'left_station': '3'}])
        self.app.vars['model'].set('GT2103-PMBLS')
        page = self.app.collect()['pages'][0]
        for key in ('battery', 'sd_card', 'sd_card_model', 'serial_mode'):
            self.assertNotIn(key, page)
        self.assertEqual(page['left_station'], '3')

    def test_supported_options_are_preserved(self):
        for page in ({'kind': 'fx5body', 'model': 'FX5U-32MR/ES', 'board_model': 'FX5-485-BD', 'board_tag': 'B1'},
                     {'kind': 'gotbody', 'model': 'GT2715-XTBA', 'battery': '装着', 'sd_card': '有'}):
            with self.subTest(kind=page['kind']):
                self.show_pages([page])
                collected = self.app.collect()['pages'][0]
                for key, value in page.items():
                    self.assertEqual(collected[key], value)

    def test_part_pickers_grab_input_until_closed(self):
        self.show_pages([{'kind': 'qbody', 'model': 'Q03UDVCPU', 'base_model': 'Q33B', 'power_model': 'Q61P'},
                         {'kind': 'fx5body', 'model': 'FX5U-32MR/ES'}])
        for key in ('model', 'standard_model', 'extension_base_model'):
            with self.subTest(key=key):
                self.app.pick_part(key)
                dialog = self.dialog()
                self.assertIs(self.app.grab_current(), dialog)
                self.assertEqual(dialog.grab_status(), 'local')
                dialog.destroy()
                self.assertIsNone(self.app.grab_current())
        self.assertEqual(self.app.data['pages'][1]['model'], 'FX5U-32MR/ES')

    def test_extension_power_picker_keeps_the_modal_grab(self):
        self.show_pages([{'kind': 'qbody', 'model': 'Q03UDVCPU', 'base_model': 'Q33B', 'power_model': 'Q61P'}])
        self.app.pick_extension()
        base_dialog = self.dialog()
        self.assertIs(self.app.grab_current(), base_dialog)
        self.choose_model(base_dialog, 'Q63B')
        power_dialog = self.dialog()
        self.assertIs(self.app.grab_current(), power_dialog)
        self.choose_model(power_dialog, 'Q61P')
        self.assertIsNone(self.app.grab_current())
        self.assertEqual(self.app.collect()['pages'][0]['extensions'],
                         [{'base_model': 'Q63B', 'power_model': 'Q61P', 'modules': []}])

    def test_network_cpu_reserves_a_slot_when_adding_modules(self):
        self.show_pages([{'kind': 'iqrbody', 'model': 'R04ENCPU', 'base_model': 'R33B',
                          'power_model': 'R61P', 'modules': ['RX40C7']}])
        self.app.pick_modules()
        self.assertIs(self.app.grab_current(), self.dialog())
        with patch('gui.messagebox.showerror') as report:
            self.select_module('RX40C7')
            report.assert_not_called()
        self.assertEqual(self.app.collect()['pages'][0]['modules'], ['RX40C7', 'RX40C7'])
        self.app.pick_modules()
        with patch('gui.messagebox.showerror') as report:
            self.select_module('RX40C7')
            report.assert_called_once()
        self.assertEqual(self.app.collect()['pages'][0]['modules'], ['RX40C7', 'RX40C7'])


if __name__ == '__main__':
    unittest.main()
