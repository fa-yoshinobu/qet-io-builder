"""追加通信ユニットの公式端子表と図面到達を確認。"""
import json
import unittest
import gen_io_page as g

MODELS = ('RJ51AW12AL','RJ71BAC96','RJ71EIP91','RJ71CN91','RJ71DN91','RJ71PB91V','RJ71GB91','B-RIF')

class IqrOtherCommunicationTest(unittest.TestCase):
    def test_manual_terminal_order_and_occupied_points(self):
        anywire = g.IQR_COMM['RJ51AW12AL']
        self.assertEqual(anywire['terminal_order'], ['IN 24V','IN 0V','OUT 24V','OUT 0V','DP','DN','LG'])
        device = g.IQR_COMM['RJ71DN91']['interfaces'][0]
        self.assertEqual(list(zip(device['port_pins'],device['ports'])), [('1','V+'),('2','CAN_H'),('3','Shield'),('4','CAN_L'),('5','V-')])
        self.assertEqual(g.IQR_COMM['RJ71CN91']['interfaces'][0]['ports'], ['CAN+','SLD','CAN-','GND'])
        for model in MODELS:
            self.assertEqual(g.IQR_COMM[model]['occupied_io_points'], 16 if model=='RJ71GB91' else 32)
        self.assertTrue(g.IQR_COMM['B-RIF']['manual_required'])

    def test_connector_pins_are_not_guessed_or_populated_for_unused(self):
        profibus=g.IQR_COMM['RJ71PB91V']['interfaces'][0]
        self.assertEqual([p['pin'] for p in profibus['pinout']], [3,5,6,8])
        self.assertEqual(profibus['unconnected_pins'], ['1','2','4','7','9'])
        gpib=g.IQR_COMM['RJ71GB91']['interfaces'][0]['pinout']
        self.assertEqual(len(gpib),24)
        self.assertEqual(gpib[11], {'pin':12,'signal':'FG'})
        self.assertEqual(gpib[23], {'pin':24,'signal':'Logic GND'})
        for model in ('RJ71BAC96','RJ71EIP91'):
            self.assertEqual(len(g.IQR_COMM[model]['interfaces']),1)
            self.assertEqual(g.IQR_COMM[model]['interfaces'][0]['kind'],'rj45')

    def test_all_models_reach_boxed_diagrams_and_setting_fields(self):
        for model in MODELS:
            with self.subTest(model=model):
                page=g.build_q_comm_page({'kind':'iqrcomm','left_model':model,'left_station':'TEST-STATION','left_ip':'192.0.2.1','left_dip':'TEST-SW'},g.build_symbols())
                text=[t.get('text','') for t in page.texts]
                self.assertEqual('TEST-STATION' in text, model in ('RJ71CN91', 'RJ71DN91', 'RJ71PB91V', 'RJ71GB91'))
                self.assertNotIn('TEST-SW', text)  # 機器設定欄は初期非表示。
                # IP 欄は RJ-45 のある機種だけ
                ethernet='"rj45"' in json.dumps(g.IQR_COMM[model])
                self.assertEqual('192.0.2.1' in text, ethernet)
                interface=g.IQR_COMM[model]['interfaces']
                terminals=[e for k,e,_,_ in page.placed if k=='module_pin']
                self.assertEqual(len(terminals),sum(len(i.get('ports',[])) for i in interface if i['kind']=='terminal'))
