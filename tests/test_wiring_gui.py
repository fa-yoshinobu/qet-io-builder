import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import gen_io_page as gen
import gui
from project_wiring.editor import WiringEditor


class WiringGuiTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.app = gui.App()
        self.app.withdraw()
        self.addCleanup(self.app.destroy)
        self.app.path = Path(self.folder.name) / 'project.json'
        self.app.data = gen.project_config({'pages': [
            {'kind': 'fx5body', 'model': 'FX5U-32MR/ES', 'title': '入力と出力'},
            {'kind': 'fx5body', 'model': 'FX5S-30MR/ES'}]})
        self.app.show_project()
        self.app.show_page(0)
        self.app.collect_page()
        self.app.dirty = False

    def open_editor(self):
        self.app.edit_wiring()
        return next(widget for widget in self.app.winfo_children() if isinstance(widget, WiringEditor))

    def fill(self, editor, group='connections', **values):
        for key, value in values.items():
            editor.variables[group][key].set(str(value))

    def test_button_and_modal_editor_are_visible_for_the_selected_page(self):
        self.app.show_page(None)
        self.assertEqual(str(self.app.wiring_button['state']), 'disabled')
        self.app.show_page(0)
        self.app.deiconify()
        self.app.wiring_button.invoke()
        editor = next(widget for widget in self.app.winfo_children() if isinstance(widget, WiringEditor))
        self.app.update()
        self.assertTrue(self.app.wiring_button.winfo_ismapped())
        self.assertTrue(editor.winfo_viewable())
        self.assertIs(self.app.grab_current(), editor)
        self.assertEqual(str(self.app.wiring_button['state']), 'normal')
        self.assertIn('入力と出力', editor.winfo_children()[0].winfo_children()[0]['text'])
        # The last content row must fit inside the window, not below the Apply buttons.
        variable_name = str(editor.variables['connections']['link_id'])
        entries = self.descendants(editor)
        last = next(widget for widget in entries if isinstance(widget, gui.ttk.Entry)
                    and str(widget['textvariable']) == variable_name)
        self.assertTrue(last.winfo_ismapped())
        apply = next(widget for widget in entries if isinstance(widget, gui.ttk.Button) and widget['text'] == '適用')
        self.assertTrue(apply.winfo_ismapped())
        self.assertLess(last.winfo_rooty() + last.winfo_height(), apply.winfo_rooty())

    def descendants(self, parent):
        result = []
        for widget in parent.winfo_children():
            result.append(widget)
            result.extend(self.descendants(widget))
        return result

    def test_apply_keeps_connections_boundaries_and_extra_json_in_sync(self):
        untouched = copy.deepcopy(self.app.data['pages'][1])
        editor = self.open_editor()
        self.fill(editor, unit_tag='PLC1', unit_terminal='X0', terminal_block='TB1', terminal='1',
                  wire='100', cable='W1', core='赤', section='0.75 mm²', shield='片側接地',
                  peer_tag='LS1', peer_terminal='13', destination='3-C12', purpose='原点', jumper='1-2')
        self.fill(editor, 'boundaries', left='機側', right='制御盤')
        editor.apply()
        wiring = self.app.collect()['pages'][0]['wiring']
        self.assertEqual(wiring['connections'][0]['unit_terminal'], 'X0')
        self.assertEqual(wiring['connections'][0]['terminal_block'], 'TB1')
        self.assertEqual(wiring['connections'][0]['section'], '0.75 mm²')
        self.assertEqual(wiring['boundaries'][0]['left'], '機側')
        self.assertEqual(wiring['boundaries'][0]['x'], 240)
        self.assertEqual(json.loads(self.app.extra.get('1.0', 'end'))['wiring'], wiring)
        self.assertEqual(self.app.data['pages'][1], untouched)
        self.assertTrue(self.app.dirty)
        self.assertIsNone(self.app.grab_current())
        self.assertTrue(self.app.save())
        self.assertEqual(json.loads(self.app.path.read_text(encoding='utf-8'))['pages'][0]['wiring'], wiring)

    def test_cancel_does_not_apply_local_edits_or_change_the_page(self):
        self.app.data['pages'][0]['wiring'] = {'connections': [{'wire': '100'}]}
        self.app.show_page(0)
        self.app.collect_page()
        original = copy.deepcopy(self.app.data['pages'][0])
        editor = self.open_editor()
        self.fill(editor, wire='200')
        editor.add_row('connections')
        editor.destroy()
        self.assertEqual(self.app.collect()['pages'][0], original)
        self.assertFalse(self.app.dirty)

    def test_terminal_plan_and_level_are_editable_and_saved(self):
        editor = self.open_editor()
        self.app.deiconify()
        self.app.update()
        checkbox = next(widget for widget in self.descendants(editor)
                        if isinstance(widget, gui.ttk.Checkbutton) and widget['text'] == '端子台接続図を追加')
        self.assertTrue(checkbox.winfo_ismapped())
        checkbox.invoke()
        self.fill(editor, terminal_block='TB1', level='上段', terminal='01', unit_terminal='X0')
        editor.apply()
        wiring = self.app.collect()['pages'][0]['wiring']
        self.assertTrue(wiring['terminal_plan'])
        self.assertEqual(wiring['connections'][0]['level'], '上段')
        self.assertTrue(self.app.save())
        stored = json.loads(self.app.path.read_text(encoding='utf-8'))['pages'][0]['wiring']
        self.assertEqual(stored, wiring)
        self.app.show_page(0)
        editor = self.open_editor()
        self.assertTrue(editor.terminal_plan.get())
        self.assertEqual(editor.values['connections'][0]['level'], '上段')

    def test_empty_apply_does_not_add_wiring_or_mark_the_project_changed(self):
        editor = self.open_editor()
        editor.apply()
        self.assertNotIn('wiring', self.app.collect()['pages'][0])
        self.assertFalse(self.app.dirty)

    def test_delete_last_row_removes_the_wiring_key(self):
        self.app.data['pages'][0]['wiring'] = {'connections': [{'wire': '100'}]}
        self.app.show_page(0)
        editor = self.open_editor()
        editor.trees['connections'].selection_set('0')
        self.app.update()
        editor.delete_row('connections')
        editor.apply()
        self.assertNotIn('wiring', self.app.collect()['pages'][0])
        self.assertTrue(self.app.dirty)

    def test_invalid_extra_json_does_not_open_an_editor(self):
        self.app.extra.delete('1.0', 'end')
        self.app.extra.insert('1.0', '{')
        with patch.object(self.app, 'report') as report:
            self.app.edit_wiring()
        report.assert_called_once()
        self.assertFalse(any(isinstance(widget, WiringEditor) for widget in self.app.winfo_children()))
        self.assertNotIn('wiring', self.app.data['pages'][0])

    def test_invalid_position_keeps_the_editor_open_and_the_original_untouched(self):
        editor = self.open_editor()
        for values in ({'wire': '100', 'part': '1.5'}, {'part': '1', 'x': 'nan'}, {'x': '1261'}):
            with self.subTest(values=values):
                self.fill(editor, **values)
                with patch('project_wiring.editor.messagebox.showerror') as report:
                    editor.apply()
                report.assert_called_once()
                self.assertTrue(editor.winfo_exists())
                self.assertNotIn('wiring', self.app.data['pages'][0])

    def test_boundary_add_update_delete_and_position_validation(self):
        editor = self.open_editor()
        editor.add_row('boundaries')
        self.assertEqual(len(editor.values['boundaries']), 1)
        self.fill(editor, 'boundaries', part='2', x='300', left='盤外', right='盤内')
        editor.update_row('boundaries')
        self.assertEqual(editor.values['boundaries'][0]['part'], 2)
        self.assertEqual(editor.values['boundaries'][0]['x'], 300)
        self.fill(editor, 'boundaries', top='780', bottom='750')
        with patch('project_wiring.editor.messagebox.showerror') as report:
            editor.update_row('boundaries')
        report.assert_called_once()
        self.assertEqual(editor.values['boundaries'][0]['top'], 75)
        editor.delete_row('boundaries')
        self.assertEqual(editor.values['boundaries'], [])

    def test_selection_change_preserves_pending_edits(self):
        editor = self.open_editor()
        self.fill(editor, wire='100')
        editor.add_row('connections')
        self.fill(editor, wire='200')
        editor.add_row('connections')
        self.app.update()
        self.fill(editor, wire='201')
        editor.trees['connections'].selection_set('0')
        self.app.update()
        self.assertEqual(editor.values['connections'][1]['wire'], '201')
        self.assertEqual(editor.variables['connections']['wire'].get(), '100')
        editor.apply()
        self.assertEqual([row['wire'] for row in self.app.collect()['pages'][0]['wiring']['connections']], ['100', '201'])

    def test_sending_and_receiving_records_keep_the_same_reference_id(self):
        editor = self.open_editor()
        self.fill(editor, reference='送り', link_id='WIRE-A', unit_terminal='X0')
        editor.add_row('connections')
        editor.clear_row('connections')
        self.fill(editor, reference='受け', link_id='WIRE-A', peer_terminal='13')
        editor.add_row('connections')
        editor.apply()
        rows = self.app.collect()['pages'][0]['wiring']['connections']
        self.assertEqual([(row['reference'], row['link_id']) for row in rows], [('送り', 'WIRE-A'), ('受け', 'WIRE-A')])
        self.assertEqual([row['y'] for row in rows], [110, 210])

    def test_next_row_uses_the_same_part_and_x_and_rejects_positions_below_the_page(self):
        editor = self.open_editor()
        self.fill(editor, wire='100', part='2', x='300', y='750')
        editor.add_row('connections')
        with patch('project_wiring.editor.messagebox.showerror') as report:
            editor.clear_row('connections')
        report.assert_called_once()
        self.assertEqual(editor.variables['connections']['wire'].get(), '100')
        self.assertEqual(editor.current['connections'], 0)
        self.fill(editor, y='300')
        editor.update_row('connections')
        editor.clear_row('connections')
        self.assertEqual(editor.variables['connections']['part'].get(), '2')
        self.assertEqual(float(editor.variables['connections']['x'].get()), 300)
        self.assertEqual(float(editor.variables['connections']['y'].get()), 400)
        self.assertEqual(editor.variables['connections']['wire'].get(), '')

    def test_generate_confirms_both_existing_csv_files_together(self):
        self.app.data['pages'][0]['wiring'] = {'connections': [{'terminal_block': 'TB1', 'terminal': '1'}]}
        output = Path(self.folder.name) / 'drawing.qet'
        paths = [output.with_name('drawing_iolist.csv'), output.with_name('drawing_terminals.csv')]
        for path in paths:
            path.write_text('original', encoding='utf-8')
        with patch.object(self.app, 'save', return_value=True), \
                patch('gui.filedialog.asksaveasfilename', return_value=str(output)), \
                patch('gui.messagebox.askyesno', return_value=False) as confirm, \
                patch('gui.subprocess.run') as run:
            self.app.generate()
        confirm.assert_called_once()
        for path in paths:
            self.assertIn(path.as_posix(), confirm.call_args.args[1])
            self.assertEqual(path.read_text(encoding='utf-8'), 'original')
        run.assert_not_called()

    def test_unused_terminal_csv_does_not_change_the_legacy_generation_flow(self):
        output = Path(self.folder.name) / 'drawing.qet'
        terminals = output.with_name('drawing_terminals.csv')
        terminals.write_text('original', encoding='utf-8')
        with patch.object(self.app, 'save', return_value=True), \
                patch('gui.filedialog.asksaveasfilename', return_value=str(output)), \
                patch('gui.messagebox.askyesno') as confirm, patch('gui.messagebox.showerror'), \
                patch('gui.subprocess.run', return_value=SimpleNamespace(returncode=1, stdout='', stderr='test')) as run:
            self.app.generate()
        confirm.assert_not_called()
        run.assert_called_once()
        self.assertEqual(terminals.read_text(encoding='utf-8'), 'original')


if __name__ == '__main__':
    unittest.main()
