import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import gen_io_page as gen


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
