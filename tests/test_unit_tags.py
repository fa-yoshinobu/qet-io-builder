import unittest

import gen_io_page as gen
from tools.export_power_supply_elements import definition


class UnitTagsTest(unittest.TestCase):
    def test_body_tags_keep_model_and_use_native_label(self):
        page = gen.build_fx5_body_page({'model':'FX5U-32MR/ES', 'tag':'PLC-主機 1',
                                       'board_model':'FX5-485-BD', 'board_tag':'UNIT1'}, gen.build_symbols())
        cpu = next(e for kind,e,_,_ in page.placed if kind.startswith('fx5_body_'))
        info = {n.get('name'):n.text for n in cpu.findall('./elementInformations/elementInformation')}
        self.assertEqual(info['label'], 'PLC-主機 1')
        self.assertEqual(info['manufacturer_reference'], 'FX5U-32MR/ES')
        self.assertEqual(info['auxiliary11'], 'UNIT1')
        self.assertIsNotNone(cpu.find("./dynamic_texts/dynamic_elmt_text[info_name='auxiliary11']"))

    def test_structure_and_communication_tags_are_independent(self):
        body = {'kind':'qbody','model':'Q03UDVCPU','power_model':'Q61P','base_model':'Q35B',
                'tag':'PLC1','power_tag':'AVR1','base_tag':'BASE1',
                'modules':['QX40','QX40'],'module_tags':['UNIT1','UNIT2']}
        comm = {'kind':'qcomm','left_model':'QJ71E71-100','right_model':'QJ71E71-100',
                'left_tag':'NET1','right_tag':'NET2'}
        root,_ = gen.build_project(gen.project_config({'front_pages':False}), [(body,None),(comm,None)])
        texts = [t.get('text','') for t in root.findall('.//diagram/inputs/input')]
        for tag in ('BASE1','UNIT1','UNIT2'):
            self.assertIn(tag,texts)
        for tag in ('NET1','NET2'):
            self.assertIn(tag,texts)
        self.assertEqual(texts.count('QJ71E71-100'),2)
        infos = [n.text for n in root.findall('.//diagram/elements/element/elementInformations/elementInformation')]
        for value in ('PLC1','AVR1','Q03UDVCPU','Q61P'):
            self.assertIn(value,infos)

    def test_power_parts_have_editable_label(self):
        spec = gen.read_unit_definitions()['power_supply']['S8VK-G01524']
        xml = definition('S8VK-G01524',spec)
        self.assertIsNotNone(xml.find("./description/dynamic_text[info_name='label']"))


if __name__=='__main__':
    unittest.main()
