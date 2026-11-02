import unittest
from tkinter import ttk
from unittest.mock import patch

import gen_io_page as gen
import gui


MEMORY_OPTIONS = ('sd_card', 'memory_card', 'memory_cassette')


class CpuMemoryGuiTest(unittest.TestCase):
    def setUp(self):
        self.app = gui.App()
        self.addCleanup(self.app.destroy)

    def show(self, kind, model, **options):
        self.app.data = {'pages': [dict(kind=kind, model=model, **options)]}
        self.app.show_project()
        self.app.show_page(0)
        self.app.update()

    def widget(self, key):
        return self.app.field_widgets[key][1]

    def test_q_and_iqr_memory_candidates_use_the_selected_cpu_and_sd_remains_editable(self):
        for kind, model in (('qbody', 'Q03UDVCPU'), ('iqrbody', 'R04CPU')):
            with self.subTest(kind=kind), patch.dict(gui.cpu_options(kind, model), {
                    'sd_card_supported': True, 'sd_card_models': ['SD-A', 'SD-B'],
                    'memory_cassette_supported': True, 'memory_cassette_models': ['SRAM-A'],
                    'memory_card_supported': True, 'memory_card_models': ['CARD-A']}):
                self.show(kind, model)
                for option in MEMORY_OPTIONS:
                    self.assertTrue(self.widget(option).winfo_ismapped())
                    self.assertTrue(self.widget(option + '_model').winfo_ismapped())
                self.assertIsInstance(self.widget('sd_card_model'), ttk.Combobox)
                self.assertEqual(str(self.widget('sd_card_model')['state']), 'normal')
                self.assertEqual(self.widget('sd_card_model')['values'], ('', 'SD-A', 'SD-B'))
                self.assertEqual(self.widget('memory_card_model')['values'], ('', 'CARD-A'))
                self.assertEqual(self.widget('memory_cassette_model')['values'], ('', 'SRAM-A'))
                self.widget('sd_card_model').set('案件のSD型式')
                self.app.vars['sd_card'].set('有')
                self.assertEqual(self.app.collect()['pages'][0]['sd_card_model'], '案件のSD型式')
                if kind == 'iqrbody':
                    self.assertFalse(self.widget('battery_model').winfo_ismapped())

    def test_cpu_change_removes_unsupported_memory_options_from_saved_page(self):
        for kind, before, after in (('qbody', 'Q03UDVCPU', 'Q00UCPU'),
                                    ('iqrbody', 'R04CPU', 'R00CPU')):
            with self.subTest(kind=kind), patch.dict(gui.cpu_options(kind, before), {
                    key + '_supported': True for key in MEMORY_OPTIONS}), patch.dict(gui.cpu_options(kind, after), {
                    key + '_supported': False for key in MEMORY_OPTIONS}):
                self.show(kind, before, battery='装着')
                for key in MEMORY_OPTIONS:
                    self.app.vars[key].set('有')
                    self.app.vars[key + '_model'].set('前CPUの型式')
                self.app.vars['model'].set(after)
                self.app.update()
                saved = self.app.collect()['pages'][0]
                for key in MEMORY_OPTIONS:
                    self.assertFalse(self.widget(key).winfo_ismapped())
                    self.assertFalse(self.widget(key + '_model').winfo_ismapped())
                    self.assertNotIn(key, saved)
                    self.assertNotIn(key + '_model', saved)
                self.assertEqual(saved['battery'], '装着')

    def test_candidates_switch_between_supported_cpus(self):
        with patch.dict(gen.IQR_CPU['R04CPU'], {'memory_cassette_supported': True,
                                             'memory_cassette_models': ['SRAM-A']}), \
                patch.dict(gen.IQR_CPU['R08CPU'], {'memory_cassette_supported': True,
                                                'memory_cassette_models': ['SRAM-B']}):
            self.show('iqrbody', 'R04CPU')
            self.assertEqual(self.widget('memory_cassette_model')['values'], ('', 'SRAM-A'))
            self.app.vars['model'].set('R08CPU')
            self.app.update()
            self.assertTrue(self.widget('memory_cassette_model').winfo_ismapped())
            self.assertEqual(self.widget('memory_cassette_model')['values'], ('', 'SRAM-B'))

    def test_missing_candidate_lists_default_to_empty_choices(self):
        spec = gen.IQR_CPU['R04CPU']
        with patch.dict(spec):
            for key in MEMORY_OPTIONS:
                spec[key + '_supported'] = True
                spec.pop(key + '_models', None)
            self.show('iqrbody', 'R04CPU')
            for key in MEMORY_OPTIONS:
                self.assertEqual(self.widget(key + '_model')['values'], ('',))

    def test_remote_head_hides_and_discards_cpu_memory(self):
        options = {key: '有' for key in MEMORY_OPTIONS}
        options.update({key + '_model': '前CPUの型式' for key in MEMORY_OPTIONS})
        self.show('iqrbody', 'RJ72GF15-T2', **options)
        saved = self.app.collect()['pages'][0]
        for key in MEMORY_OPTIONS:
            self.assertFalse(self.widget(key).winfo_ismapped())
            self.assertFalse(self.widget(key + '_model').winfo_ismapped())
            self.assertNotIn(key, saved)
            self.assertNotIn(key + '_model', saved)

    def test_got_and_fx5_keep_free_sd_model_input_without_cpu_candidates(self):
        got = next(model for model, spec in gen.GOT_BODY.items() if spec.get('sd_card_supported'))
        for kind, model in (('gotbody', got), ('fx5body', 'FX5U-32MR/ES')):
            with self.subTest(kind=kind):
                self.show(kind, model)
                self.assertTrue(self.widget('sd_card_model').winfo_ismapped())
                self.assertEqual(str(self.widget('sd_card_model')['state']), 'normal')
                self.assertEqual(self.widget('sd_card_model')['values'], ('',))
                self.widget('sd_card_model').set('任意の既存SD型式')
                self.app.vars['sd_card'].set('有')
                self.assertEqual(self.app.collect()['pages'][0]['sd_card_model'], '任意の既存SD型式')

    def test_real_cpu_memory_choices_and_selected_models_are_saved(self):
        for kind, model in (('qbody', 'Q03UDVCPU'), ('qbody', 'Q02UCPU'), ('iqrbody', 'R04CPU')):
            with self.subTest(model=model):
                spec = gui.cpu_options(kind, model)
                self.show(kind, model)
                selected = {}
                for key in MEMORY_OPTIONS:
                    supported = bool(spec.get(key + '_supported'))
                    self.assertEqual(bool(self.widget(key).winfo_ismapped()), supported)
                    self.assertEqual(bool(self.widget(key + '_model').winfo_ismapped()), supported)
                    models = spec.get(key + '_models', [])
                    self.assertEqual(self.widget(key + '_model')['values'], ('',) + tuple(models))
                    if supported and models:
                        self.app.vars[key].set('有')
                        self.widget(key + '_model').set(models[0])
                        selected[key + '_model'] = models[0]
                self.assertTrue(selected)
                saved = self.app.collect()['pages'][0]
                for key, value in selected.items():
                    self.assertEqual(saved[key], value)
                self.assertNotIn('メモリ適用条件', self.app.cpu_spec.cget('text'))


if __name__ == '__main__':
    unittest.main()
