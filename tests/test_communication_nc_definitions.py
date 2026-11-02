import unittest
import gen_io_page as gen


class CommunicationNcDefinitionsTest(unittest.TestCase):
    def test_can_nc_is_the_first_physical_terminal_without_invented_pin_number(self):
        spec=gen.IQR_COMM['RJ71CN91']
        interface=spec['interfaces'][0]
        nc=interface['unconnected_ports']
        self.assertEqual(len(nc),1)
        self.assertEqual(nc[0]['signal'],'NC')
        self.assertEqual(nc[0]['position'],0)
        self.assertNotIn('pin',nc[0])
        self.assertIn('CAN_V+',nc[0]['description'])
        self.assertEqual([nc[0]['signal']]+interface['ports'],spec['terminal_order'])
        self.assertIn('必要時に外部電源ラインを接続',spec['unused_terminals'][0]['description'])

    def test_cc_link_reserved_pins_complete_the_physical_order(self):
        spec=gen.IQR_COMM['RJ61BT11']
        nc=spec['unconnected_ports']
        self.assertEqual([r['pin'] for r in nc],spec['unconnected_pins'])
        self.assertEqual([r['position'] for r in nc],[0,1])
        self.assertEqual([r['pin'] for r in nc]+spec['port_pins'],[str(i) for i in range(1,8)])
        self.assertTrue(all(r['signal']=='NC' for r in nc))

    def test_profibus_nc_and_active_pins_cover_all_nine_pins_without_overlap(self):
        interface=gen.IQR_COMM['RJ71PB91V']['interfaces'][0]
        nc=interface['unconnected_ports']
        self.assertEqual([r['pin'] for r in nc],interface['unconnected_pins'])
        active={int(r['pin']) for r in interface['pinout']}
        unused={int(r['pin']) for r in nc}
        self.assertFalse(active & unused)
        self.assertEqual(active|unused,set(range(1,10)))
        self.assertTrue(all(r['position']==int(r['pin'])-1 for r in nc))

    def test_analog_known_nc_pins_are_retained_as_individual_records(self):
        for model in ('R60DA4','R60DAH4'):
            with self.subTest(model=model):
                spec=gen.IQR_ANALOG[model]
                records=spec['unconnected_ports']
                self.assertEqual([r['pin'] for r in records],spec['unconnected_pins'])
                self.assertEqual([r['channel'] for r in records],[1,2,3])
                self.assertTrue(all(r['signal']=='NC' for r in records))

    def test_analog_nc_rows_show_pins_without_connection_points(self):
        for model in ('R60DA4','R60DAH4'):
            page=gen.build_fx_analog_page({'kind':'iqranalog','model':model}, {}, gen.build_symbols(), [])
            rows=[e for key,e,_,_ in page.placed if key=='plc_in_readonly'
                  and e.findtext("./elementInformations/elementInformation[@name='label']")=='NC']
            self.assertEqual(len(rows),3)
            self.assertEqual([e.findtext("./elementInformations/elementInformation[@name='auxiliary1']") for e in rows],['4','8','12'])
            self.assertTrue(all(not e.findall('./terminals/terminal') for e in rows))
            self.assertEqual([e.findtext("./elementInformations/elementInformation[@name='comment']") for e in rows],
                             [f'CH{channel} 出力 接続しない' for channel in (1, 2, 3)])


if __name__=='__main__':
    unittest.main()
