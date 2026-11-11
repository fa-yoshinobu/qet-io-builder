import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

import gen_io_page as gen


MODELS = ['Q61P','Q62P','Q63P','Q64P','Q64PN','Q61P-D']


class QPowerTest(unittest.TestCase):

    def test_special_terminal_counts_and_names(self):
        for model in MODELS:
            spec=gen.Q_POWER[model]
            symbol=gen.iqr_power_symbol(model,spec['supply'],spec['service_24v'],225,
                                        spec['terminal_labels_top_to_bottom'],spec.get('additional_terminals'))
            with self.subTest(model=model):
                self.assertEqual(len(symbol.terminals),8 if model in ('Q62P','Q61P-D') else 6)
                labels=[a['text'] for kind,a in symbol.parts if kind=='text']
                self.assertEqual(labels,spec['terminal_labels_top_to_bottom'])
                self.assertTrue(all(30<float(pin[3])<225 for pin in symbol.terminals.values()))
        self.assertEqual(gen.Q_POWER['Q63P']['supply'],'DC')
        self.assertFalse(gen.Q_POWER['Q63P']['service_24v'])
        self.assertEqual(gen.Q_POWER['Q62P']['external_output_24v_amps'],0.6)
        self.assertEqual(gen.Q_POWER['Q61P-D']['terminal_labels_top_to_bottom'].count('LIFE OUT'),2)

    def test_all_models_generate_in_main_and_extension_stages(self):
        with tempfile.TemporaryDirectory() as folder:
            source,target=Path(folder)/'project.json',Path(folder)/'result.qet'
            for model in MODELS:
                cfg=gen.project_config({'front_pages':False,'pages':[{
                    'kind':'qbody','model':'Q03UDVCPU','base_model':'Q33B','power_model':model,
                    'extensions':[{'base_model':'Q63B','power_model':model,'modules':[]}]}]})
                source.write_text(json.dumps(cfg),encoding='utf-8')
                with contextlib.redirect_stdout(io.StringIO()):
                    gen.main(str(source),str(target))
                root=ET.parse(target).getroot()
                elements=[e for e in root.findall('./diagram/elements/element') if '_'+model+'_' in e.get('type','')]
                self.assertEqual(len(elements),2)
                definition=next(d for d in root.findall('.//collection//element') if model+'_' in d.get('name','')).find('definition')
                self.assertEqual(len(definition.findall('./description/terminal')),8 if model in ('Q62P','Q61P-D') else 6)


if __name__=='__main__':
    unittest.main()
