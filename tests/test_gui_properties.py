import tempfile
import json
import unittest
from pathlib import Path
import gui

class GuiPropertiesTest(unittest.TestCase):
    def test_fx5_body_is_first_and_power_circuit_is_not_selectable(self):
        app = gui.App()
        try:
            app.add_page()
            app.series_display.set(gui.SERIES_NAMES['iq_f']); app.select_page_series(); app.update()
            choices = app.field_widgets['kind'][1]['values']
            self.assertEqual(choices[0], gui.KIND_NAMES['fx5body'])
            self.assertNotIn(gui.KIND_NAMES['power'], choices)
        finally:
            app.destroy()

    def test_project_form_saves_values_and_preserves_other_settings(self):
        app = gui.App()
        try:
            app.data = {'pages': [], 'project_title': '旧図面', 'date': '20261001',
                        'relay_default': 'MY2N', 'power': {'P': '+24V', 'N': '0V', 'P_name': 'P24'}}
            app.show_project(); app.dirty = False
            self.assertEqual(app.project_vars['date'].get(), '20261001')
            app.project_vars['project_title'].set('新図面')
            app.project_vars['author'].set('作成担当')
            app.power_vars['N'].set('DC0V')
            app.front_pages.set(False)
            self.assertTrue(app.dirty)
            with tempfile.TemporaryDirectory() as folder:
                app.path = Path(folder) / 'project.json'
                self.assertTrue(app.save())
                saved = json.loads(app.path.read_text(encoding='utf-8'))
                self.assertEqual(saved['project_title'], '新図面')
                self.assertEqual(saved['author'], '作成担当')
                self.assertEqual(saved['power'], {'P': '+24V', 'N': 'DC0V', 'P_name': 'P24'})
                self.assertEqual(saved['relay_default'], 'MY2N')
                self.assertIs(saved['front_pages'], False)
                app.data = saved; app.show_project()
                self.assertEqual(app.project_vars['project_title'].get(), '新図面')
        finally:
            app.destroy()

    def test_visible_kind_names_and_dropdowns_follow_the_kind_and_keep_json_codes(self):
        app = gui.App()
        try:
            app.data = {'pages': [{'kind': 'qbody', 'model': 'Q03UDVCPU'}]}
            app.show_project(); app.show_page(0); app.update()
            self.assertEqual(app.kind_display.get(), 'Q 本体・ユニット構成')
            self.assertIn('Q61P', app.field_widgets['power_model'][1]['values'])
            self.assertNotIn('R61P', app.field_widgets['power_model'][1]['values'])
            app.series_display.set(gui.SERIES_NAMES['got3000']); app.select_page_series()
            app.kind_display.set(gui.KIND_NAMES['gotbody']); app.select_kind(); app.update()
            self.assertEqual(app.vars['kind'].get(), 'gotbody')
            self.assertTrue(app.pages.get(0).startswith('GOT 本体'))
            self.assertEqual(app.vars['model'].get(), '')
            self.assertIn('GT3708-XRBA', app.field_widgets['model'][1]['values'])
            self.assertNotIn('Q03UDVCPU', app.field_widgets['model'][1]['values'])
            app.collect_page()
            self.assertEqual(app.data['pages'][0]['kind'], 'gotbody')
            self.assertEqual(app.data['pages'][0]['series'], 'got3000')
        finally:
            app.destroy()

    def test_new_page_starts_with_series_and_only_relevant_kinds(self):
        app = gui.App()
        try:
            app.add_page(); app.update()
            self.assertEqual(app.vars['kind'].get(), '')
            self.assertEqual(app.vars['series'].get(), '')
            self.assertEqual(str(app.field_widgets['kind'][1]['state']), 'disabled')
            app.series_display.set(gui.SERIES_NAMES['q']); app.select_page_series(); app.update()
            choices = app.field_widgets['kind'][1]['values']
            self.assertIn(gui.KIND_NAMES['qbody'], choices)
            self.assertNotIn(gui.KIND_NAMES['iqrbody'], choices)
            self.assertNotIn(gui.KIND_NAMES['gotbody'], choices)
            app.kind_display.set(gui.KIND_NAMES['qbody']); app.select_kind(); app.update()
            self.assertEqual(app.catalog_for_page('power_model'), {'mitsubishi': {'q': sorted(gui.gen.Q_POWER)}})
        finally:
            app.destroy()

    def test_folder_fields_and_model_specific_voltage(self):
        self.assertEqual(gui.property_fields('fx5analog'), ['kind','model','tag','unit_no','title','csv'])
        self.assertIn('left_station', gui.property_fields('qcomm'))
        self.assertNotIn('input_voltage', gui.property_fields('input', 'RX40C7'))
        self.assertIn('input_voltage', gui.property_fields('input', 'RX70C4'))
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); (p/'gui_properties.toml').write_text('[fx5analog]\nfields=["unknown"]\n', encoding='utf-8')
            with self.assertRaises(ValueError): gui.property_fields('fx5analog', root=p)

    def test_selected_model_uses_its_own_folder_settings(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for folder, model, fields in [('a', 'A1', '["model", "csv"]'), ('b', 'B1', '["model", "title"]')]:
                p = root / folder; p.mkdir()
                (p/'gui_properties.toml').write_text('[input]\nfields=' + fields + '\n', encoding='utf-8')
                (p/(model+'.json')).write_text(json.dumps({'model':model}), encoding='utf-8')
            self.assertEqual(gui.property_fields('input', 'A1', root), ['kind','model','tag','unit_no','csv'])
            self.assertEqual(gui.property_fields('input', 'B1', root), ['kind','model','tag','unit_no','title'])

    def test_actual_widgets_switch_and_hidden_values_survive(self):
        app = gui.App()
        try:
            app.data={'project_title':'test','pages':[{'kind':'fx5analog','model':'FX5-4AD','csv':'analog.csv','left_station':'保存値'}]}
            app.show_project(); app.show_page(0); app.update()
            self.assertTrue(app.field_widgets['csv'][0].winfo_ismapped())
            self.assertFalse(app.field_widgets['left_station'][0].winfo_ismapped())
            app.collect_page(); self.assertEqual(app.data['pages'][0]['left_station'], '保存値')
            app.vars['kind'].set('qcomm'); app.vars['left_model'].set('QJ61BT11N'); app.update()
            self.assertTrue(app.field_widgets['left_station'][0].winfo_ismapped())
            self.assertFalse(app.field_widgets['csv'][0].winfo_ismapped())
            app.vars['left_station'].set('3'); app.collect_page()
            self.assertEqual(app.data['pages'][0]['left_station'], '3')
        finally:
            app.destroy()

if __name__=='__main__': unittest.main()
