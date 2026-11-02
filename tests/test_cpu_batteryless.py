import json
import tempfile
import unittest
from pathlib import Path

import gen_io_page as gen
from webgui.api import Api


class CpuBatterylessTest(unittest.TestCase):
    def api(self, model='R04CPU', **options):
        api = Api()
        api._data['pages'] = [dict(kind='iqrbody', model=model, base_model='R35B', power_model='R61P', **options)]
        return api

    def test_supported_cpus_and_field_visibility(self):
        for model, spec in gen.IQR_CPU.items():
            supported = model.startswith('R') and model not in ('R00CPU', 'R01CPU', 'R02CPU')
            self.assertEqual(spec['batteryless_supported'], supported)
            page = self.api(model).page(0)
            self.assertEqual('batteryless' in page['visible'], supported)
            if supported:
                self.assertEqual(spec['batteryless_model'], 'NZ1BLC')
                self.assertEqual(page['options']['batteryless'], ['有', '無', '要確認'])

    def test_selection_is_saved_reloaded_and_shown_in_drawing(self):
        api = self.api()
        values = api.page(0)['values']; values['batteryless'] = '有'
        self.assertNotIn('error', api.update_page(0, values, '', 'batteryless'))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'project.json'
            self.assertNotIn('error', api.save_as(str(path)))
            self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['pages'][0]['batteryless'], '有')
            other = Api(); other.open_project(str(path))
            self.assertEqual(other.page(0)['values']['batteryless'], '有')
            self.assertNotIn('error', other.check())
        root, _ = gen.build_project({'front_pages': False}, [(api._data['pages'][0], None)])
        texts = [t.get('text', '') for t in root.findall('./diagram/inputs/input')]
        self.assertIn('有 (NZ1BLC)', texts)

    def test_shared_cassette_slot_switches_without_leaving_incompatible_model(self):
        api = self.api(memory_cassette='有', memory_cassette_model='NZ2MC-4MBS')
        values = api.page(0)['values']; values['batteryless'] = '有'
        result = api.update_page(0, values, '', 'batteryless')
        self.assertEqual(result['values']['memory_cassette'], '無')
        self.assertEqual(result['values']['memory_cassette_model'], '')
        values = result['values']; values['memory_cassette'] = '有'
        result = api.update_page(0, values, '', 'memory_cassette')
        self.assertEqual(result['values']['batteryless'], '無')

    def test_switching_to_unsupported_cpu_removes_option(self):
        api = self.api(batteryless='有')
        values = api.page(0)['values']; values['model'] = 'R01CPU'
        result = api.update_page(0, values, '', 'model')
        self.assertNotIn('batteryless', result['visible'])
        self.assertNotIn('batteryless', api._data['pages'][0])

    def test_tk_field_is_selectable_and_saved(self):
        import gui
        app = gui.App()
        try:
            app.data = self.api()._data
            app.show_project(); app.show_page(0); app.update()
            widget = app.field_widgets['batteryless'][1]
            self.assertTrue(widget.winfo_ismapped())
            self.assertEqual(tuple(widget['values']), ('有', '無', '要確認'))
            app.vars['batteryless'].set('有')
            self.assertEqual(app.collect()['pages'][0]['batteryless'], '有')
            app.vars['model'].set('R01CPU'); app.update()
            self.assertFalse(widget.winfo_ismapped())
            self.assertNotIn('batteryless', app.collect()['pages'][0])
        finally:
            app.destroy()

    def test_cli_validation_rejects_unsupported_conflicting_and_invalid_states(self):
        for model, options in [('R00CPU', {'batteryless': '有'}),
                               ('R04CPU', {'batteryless': '有', 'memory_cassette': '有'}),
                               ('R04CPU', {'batteryless': 'NZ1BLC'})]:
            api = self.api(model, **options)
            self.assertIn('error', api.check())
        self.assertTrue(gen.cpu_option_error({'batteryless': '有'}, gen.Q_CPU['Q03UDVCPU']))
        self.assertTrue(gen.cpu_option_error({'batteryless': '有'}, gen.iqr_cpu_positions()['RJ72GF15-T2']))


if __name__ == '__main__':
    unittest.main()
