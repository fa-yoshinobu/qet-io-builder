import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

import gen_io_page as gen
import gui_core as gui


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
