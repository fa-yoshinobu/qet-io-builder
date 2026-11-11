import unittest
import gen_io_page as g
import gui_core as gui

class IqrInputVoltageTest(unittest.TestCase):
    def info(self, element, name):
        return element.find(f"./elementInformations/elementInformation[@name='{name}']").text

    def test_low_voltage_and_grouped_commons(self):
        for model, voltage, common, polarity in [('RX70C4','12',['TB17'],'P'), ('RX71C4','5',['B1'],'P'), ('RX72C4','5',['1B1'],'P'), ('RX40PC6H','',['TB9','TB18'],'P'), ('RX40NC6H','',['TB9','TB18'],'N'), ('RX41C6HS','',['B1'],'P'), ('RX61C6HS','5',['B1'],'P')]:
            with self.subTest(model=model):
                unit=g.IO_UNITS[model]
                rows=[{'アドレス':f'X{i:X}', '機器番号':'', '信号名':''} for i in range(min(16,unit['points']))]
                page=g.Page(g.build_symbols()); uc={'model':model}
                if voltage: uc['input_voltage']=voltage
                g.iqr_input_half(page,0,uc,rows,0,0)
                coms=[e for k,e,_,_ in page.placed if k=='plc_in' and self.info(e,'label')=='COM']
                self.assertEqual([self.info(e,'auxiliary1') for e in coms], common)
                expected = polarity + voltage if voltage else g.LANE[polarity]
                for e in coms:
                    self.assertEqual(self.info(e,'comment'),'コモン')
                    tb = next(c.get('element1') for c in page.conductors if c.get('element2')==e.get('uuid'))
                    supply = next(c for c in page.conductors if c.get('element2')==tb)
                    self.assertEqual(supply.get('num'),expected)
                if voltage:
                    texts=[t.get('text') for t in page.texts]
                    self.assertIn('P'+voltage,texts); self.assertNotIn('P24',texts)
                self.assertIn(model,gui.part_catalog('model','input')['mitsubishi']['iq_r'])
                if voltage: self.assertTrue(g.validate(rows,dict(uc,kind='input',csv='in.csv',input_voltage='24')))

    def test_all_signal_pins_and_ranges(self):
        expected={'RX70C4':(16,'TB1','TB16'), 'RX71C4':(32,'B20','A5'), 'RX72C4':(64,'1B20','2A5'), 'RX40PC6H':(16,'TB1','TB17'), 'RX40NC6H':(16,'TB1','TB17'), 'RX41C6HS':(32,'B20','A5'), 'RX61C6HS':(32,'B20','A5')}
        for model,(count,first,last) in expected.items():
            u=g.IO_UNITS[model]
            self.assertEqual((len(u['pins']),u['pins'][0],u['pins'][-1]),(count,first,last))
            self.assertEqual(len(g.unit_addrs({'model':model,'start':'100'})),count)

if __name__=='__main__': unittest.main()

