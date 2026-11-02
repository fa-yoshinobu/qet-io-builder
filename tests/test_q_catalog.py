import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

import gen_io_page as gen
import gui


CPUS = ['Q03UDVCPU','Q04UDVCPU','Q06UDVCPU','Q13UDVCPU','Q26UDVCPU','Q00UCPU','Q01UCPU','Q02UCPU']
BASES = ['Q33B','Q35B','Q38B','Q312B']
EXTENSIONS = ['Q63B','Q65B','Q68B','Q612B']


class QCatalogTest(unittest.TestCase):
    def test_requested_choices_and_cpu_features(self):
        for key, models in [('model',CPUS),('base_model',BASES),('extension_base_model',EXTENSIONS)]:
            choices=gui.part_catalog(key,'qbody')['mitsubishi']['q']
            self.assertTrue(set(models)<=set(choices))
        self.assertFalse(set(EXTENSIONS)&set(gui.part_catalog('base_model','qbody')['mitsubishi']['q']))
        for model in CPUS:
            self.assertTrue(gen.Q_CPU[model]['usb_port'])
            self.assertEqual(gen.Q_CPU[model]['ethernet'],'UDV' in model)
        for model in CPUS[-3:]:
            self.assertFalse(gen.Q_CPU[model]['sd_card_supported'])

    def test_gui_choices_and_extension_selection_save(self):
        app=gui.App()
        try:
            app.data={'pages':[{'kind':'qbody','model':'Q03UDVCPU','base_model':'Q33B','power_model':'Q61P',
                               'extensions':[{'base_model':'Q63B','power_model':'Q61P','modules':['QX40']}]}]}
            app.show_project();app.show_page(0);app.update()
            self.assertTrue(set(CPUS)<=set(app.field_widgets['model'][1]['values']))
            self.assertTrue(set(BASES)<=set(app.field_widgets['base_model'][1]['values']))
            self.assertTrue(app.extension_button.winfo_ismapped())
            def choose(key,on_select):
                self.assertIn(key,('extension_base_model','power_model'))
                on_select('Q65B' if key=='extension_base_model' else 'Q61P')
            with patch.object(app,'pick_part',side_effect=choose):
                app.pick_extension()
            page=app.collect()['pages'][0]
            self.assertEqual(page['extensions'][0]['modules'],['QX40'])
            self.assertEqual(page['extensions'][1],{'base_model':'Q65B','power_model':'Q61P','modules':[]})
            self.assertEqual(page['base_model'],'Q33B')
        finally:
            app.destroy()

    def test_all_requested_cpus_and_bases_generate(self):
        with tempfile.TemporaryDirectory() as folder:
            source,target=Path(folder)/'project.json',Path(folder)/'result.qet'
            for cpu in CPUS:
                for base,extension in zip(BASES,EXTENSIONS):
                    with self.subTest(cpu=cpu,base=base,extension=extension):
                        cfg=gen.project_config({'front_pages':False,'pages':[{
                            'kind':'qbody','model':cpu,'power_model':'Q61P','base_model':base,
                            'extensions':[{'base_model':extension,'power_model':'Q61P','modules':[]}]}]})
                        source.write_text(json.dumps(cfg),encoding='utf-8')
                        with contextlib.redirect_stdout(io.StringIO()):
                            gen.main(str(source),str(target))
                        self.assertTrue(ET.parse(target).findall('diagram'))


if __name__=='__main__':
    unittest.main()
