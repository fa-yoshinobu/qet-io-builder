import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import gen_io_page as gen
import gui


class QCpuSpecsTest(unittest.TestCase):
    def test_capacities_and_expansion_limits_match_the_manual(self):
        expected={'Q00UCPU':(10,1024,4,24),'Q01UCPU':(15,1024,4,24),'Q02UCPU':(20,2048,4,36),
                  'Q03UDVCPU':(30,4096,7,64),'Q04UDVCPU':(40,4096,7,64),'Q06UDVCPU':(60,4096,7,64),
                  'Q13UDVCPU':(130,4096,7,64),'Q26UDVCPU':(260,4096,7,64)}
        for model,values in expected.items():
            spec=gen.Q_CPU[model]
            self.assertEqual(tuple(spec[k] for k in ('program_capacity_ksteps','io_points','max_extension_stages','max_module_slots')),values)
            self.assertEqual(spec['io_device_points'],8192)
            self.assertIn('Q8BAT',spec['battery_models'])

    def test_gui_properties_and_options_follow_the_cpu(self):
        app=gui.App()
        try:
            app.data={'pages':[{'kind':'qbody','model':'Q03UDVCPU','base_model':'Q33B','power_model':'Q61P'}]}
            app.show_project();app.show_page(0);app.update()
            self.assertIn('30Kステップ',app.cpu_spec.cget('text'))
            self.assertTrue(app.field_widgets['sd_card'][1].winfo_ismapped())
            self.assertTrue(app.field_widgets['memory_cassette_model'][1].winfo_ismapped())
            self.assertFalse(app.field_widgets['memory_card'][1].winfo_ismapped())
            self.assertIn('Q4MCA-8MBS',app.field_widgets['memory_cassette_model'][1]['values'])
            self.assertNotIn('搭載不可',app.field_widgets['battery'][1]['values'])
            app.vars['sd_card'].set('有');app.vars['memory_cassette_model'].set('Q4MCA-2MBS')
            app.vars['model'].set('Q02UCPU');app.update()
            self.assertIn('20Kステップ',app.cpu_spec.cget('text'))
            self.assertFalse(app.field_widgets['sd_card'][1].winfo_ismapped())
            self.assertTrue(app.field_widgets['memory_card_model'][1].winfo_ismapped())
            self.assertIn('Q3MEM-8MBS',app.field_widgets['memory_card_model'][1]['values'])
            saved=app.collect()['pages'][0]
            self.assertNotIn('sd_card',saved)
            self.assertNotIn('memory_cassette_model',saved)
        finally:
            app.destroy()

    def test_gui_extension_choices_respect_remaining_slots(self):
        app=gui.App()
        try:
            app.data={'pages':[{'kind':'qbody','model':'Q00UCPU','base_model':'Q312B','power_model':'Q61P',
                               'extensions':[{'base_model':'Q68B','power_model':'Q61P','modules':[]}]}]}
            app.show_project();app.show_page(0)
            choices=app.catalog_for_page('extension_base_model')['mitsubishi']['q']
            self.assertIn('Q63B',choices)
            self.assertNotIn('Q65B',choices)
            with patch.object(app,'report') as error:
                app.add_extension('Q65B','Q61P')
                self.assertIn('24',str(error.call_args[0][0]))
            self.assertEqual(len(app.collect()['pages'][0]['extensions']),1)
        finally:
            app.destroy()

    def test_cli_rejects_cpu_limit_and_option_mismatches(self):
        base={'kind':'qbody','model':'Q00UCPU','base_model':'Q33B','power_model':'Q61P'}
        cases=[dict(base,extensions=[{'base_model':'Q63B','power_model':'Q61P'}]*5),
               dict(base,base_model='Q312B',extensions=[{'base_model':'Q612B','power_model':'Q61P'}]*2),
               dict(base,sd_card='有'),dict(base,battery_model='FX3U-32BL'),
               dict(base,model='Q03UDVCPU',memory_cassette_model='Q3MEM-8MBS')]
        with tempfile.TemporaryDirectory() as folder:
            for page in cases:
                source,target=Path(folder)/'project.json',Path(folder)/'result.qet'
                source.write_text(json.dumps(gen.project_config({'pages':[page]})),encoding='utf-8')
                with contextlib.redirect_stdout(io.StringIO()),self.assertRaises(SystemExit):
                    gen.main(str(source),str(target))

    def test_selected_option_models_are_shown_in_the_drawing(self):
        page={'kind':'qbody','model':'Q03UDVCPU','base_model':'Q33B','power_model':'Q61P',
              'battery':'装着','battery_model':'Q8BAT','memory_cassette':'有','memory_cassette_model':'Q4MCA-2MBS'}
        root,_=gen.build_project(gen.project_config({'front_pages':False}),[(page,None)])
        texts=[t.get('text','') for t in root.findall('.//diagram/inputs/input')]
        self.assertIn('装着 (Q8BAT)',texts)
        self.assertIn('有 (Q4MCA-2MBS)',texts)
        page['model']='Q02UCPU';page.pop('memory_cassette');page.pop('memory_cassette_model')
        page.update(memory_card='有',memory_card_model='Q3MEM-8MBS')
        root,_=gen.build_project(gen.project_config({'front_pages':False}),[(page,None)])
        texts=[t.get('text','') for t in root.findall('.//diagram/inputs/input')]
        self.assertIn('メモリカード',texts)
        self.assertIn('有 (Q3MEM-8MBS)',texts)


if __name__=='__main__':
    unittest.main()
