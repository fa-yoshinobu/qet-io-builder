import unittest
from xml.etree import ElementTree as ET

import gen_io_page as gen
from renderers import ethernet_switch, terminal_box
from tools.export_power_supply_elements import definition as power_definition


class BoxHeadersTest(unittest.TestCase):
    def test_box_pages_share_io_header_height_and_top_margin(self):
        cases=[{'kind':'qcomm','left_model':'QJ71C24N'},
               {'kind':'iqrcomm','left_model':'RD81DC96','right_model':'RJ71CN91'},
               {'kind':'fxcomm','left_model':'FX5-485ADP'},
               {'kind':'gotbody','model':'GT2715-XTBD'},
               {'kind':'gotoption','left_model':'GT15-RS4-TE'},
               {'kind':'remotebody','model':'NZ2GF12A2-16T'},
               {'kind':'remotebody','model':'AJ65SBTB2-16T1'},
               {'kind':'fx5body','model':'FX5U-32MR/ES'}]
        for pg in cases:
            with self.subTest(page=pg):
                root,_=gen.build_project(gen.project_config({'front_pages':False}),[(pg,None)])
                diagram=root.find('diagram')
                rectangles=diagram.findall('./shapes/shape')
                headers=[r for r in rectangles if r.get('type')=='Rectangle' and r.get('y1')=='34' and r.get('y2')=='52']
                self.assertEqual(len(headers),2 if pg.get('right_model') else 1)
                self.assertFalse(any(r.get('y1')=='52' and r.get('y2')=='80' for r in rectangles))
                if pg['kind']=='fx5body':
                    cpu=next(e for e in diagram.findall('./elements/element') if 'fx5_body_' in e.get('type',''))
                    self.assertEqual(float(cpu.get('y')),52)
                else:
                    self.assertTrue(any(r.get('y1')=='52' and float(r.get('y2'))>52 for r in rectangles))

    def test_communication_headers_keep_number_tag_and_model_separate(self):
        for kind,model,field,caption in [('iqrcomm','RJ71CN91','slot','スロットNo. 2'),
                                         ('fxcomm','FX5-485ADP','unit_no','ユニットNo. 2')]:
            pg={'kind':kind,'left_model':model,'left_tag':'UNIT1','left_'+field:'2'}
            root,_=gen.build_project(gen.project_config({'front_pages':False}),[(pg,None)])
            texts=[t.get('text','') for t in root.findall('.//diagram/inputs/input')]
            for value in (caption,'UNIT1',model):
                self.assertEqual(texts.count(value),1)

    def test_unit_number_tag_and_model_are_in_one_header(self):
        definitions=gen.read_unit_definitions()
        cases=[(m,s,power_definition,260 if s.get('component_style') == 'smart_power_supply' else 240) for m,s in definitions['power_supply'].items()]
        for model,spec in definitions['standard_device'].items():
            if spec.get('component_style')=='terminal_box':
                cases.append((model,spec,terminal_box.definition,260))
            elif spec.get('component_style')=='ethernet_switch':
                cases.append((model,spec,ethernet_switch.definition,260))
        self.assertGreaterEqual(len(cases),33)
        for model,spec,build,width in cases:
            with self.subTest(model=model):
                xml=build(model,spec)
                desc=xml.find('description')
                labels=[n for n in desc.findall('dynamic_text') if n.findtext('info_name')=='label']
                numbers=[n for n in desc.findall('dynamic_text') if n.findtext('info_name')=='auxiliary1']
                self.assertEqual(len(labels),1)
                self.assertEqual(len(numbers),1)
                self.assertTrue(all(n.get('Halignment')=='AlignHCenter' for n in labels+numbers))
                self.assertTrue(all(-18<=float(n.get('y'))<0 for n in labels+numbers))
                self.assertEqual(sum(t.get('text')==model for t in desc.findall('text')),1)
                self.assertEqual(sum(t.get('text')=='ユニットNo.' for t in desc.findall('text')),1)
                header=next(r for r in desc.findall('rect') if float(r.get('y'))==-18)
                self.assertEqual(float(header.get('width')),width)
                self.assertEqual(float(header.get('height')),18)
                self.assertGreaterEqual(float(xml.get('hotspot_y')),18)
                self.assertTrue(all(float(t.get('y'))>=0 for t in desc.findall('terminal')))
                self.assertEqual(ET.tostring(xml),ET.tostring(build(model,spec)))


if __name__=='__main__':
    unittest.main()
