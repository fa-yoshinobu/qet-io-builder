import unittest
import gen_io_page as gen


class IoLabelPositionsTest(unittest.TestCase):
    def test_signal_and_pin_texts_are_centered_and_fit_cells(self):
        for key,texts,label,pin in [('plc_in',gen.IN_TEXTS,'I+/CHK+','左17段'),('plc_out',gen.OUT_TEXTS,'24GDC','B20')]:
            with self.subTest(key=key):
                page=gen.Page(gen.build_symbols())
                page.place(key,330,90,label=label,infos={'auxiliary1':pin},texts=texts)
                element=page.elements[-1]
                for name,value in [('label',label),('auxiliary1',pin)]:
                    text=element.find(f"./dynamic_texts/dynamic_elmt_text[info_name='{name}']")
                    self.assertEqual(text.get('Halignment'),'AlignHCenter')
                    width=float(text.get('text_width'))
                    size=float(text.get('font').split(',')[1])
                    shown=gen.wrap2(value,width-2*gen.TEXT_MARGIN-4,size)
                    self.assertTrue(all(gen.text_w(line,size)+2*gen.TEXT_MARGIN<=width for line in shown.split('\n')))
                    if value=='I+/CHK+':
                        self.assertAlmostEqual(float(text.get('y')),gen.vcenter(size,2),delta=0.1)
                    if value=='左17段':
                        self.assertAlmostEqual(float(text.get('y')),gen.vcenter(size,1),delta=0.1)

    def test_power_wire_labels_are_aligned_before_the_unit(self):
        page=gen.Page(gen.build_symbols())
        for i,label in enumerate(('P24','N24')):
            y=90+40*i
            lane=page.place('junction',40,y)
            unit=page.place('plc_in',330,y,label='電源',texts=gen.IN_TEXTS)
            page.wire(lane,'e',unit,'t',num=label,show=True)
        first,second=page.conductors
        self.assertEqual(first.get('userx'),second.get('userx'))
        self.assertEqual(float(second.get('usery'))-float(first.get('usery')),40)
        self.assertGreater(float(first.get('userx')),270)
        self.assertEqual(first.get('rotation'),'0')

    def test_input_common_number_is_on_the_last_wire_segment(self):
        rows=[{'アドレス':f'X{i:X}','機器番号':'','信号名':'予備'} for i in range(16)]
        page=gen.build_iqr_page(rows,{'kind':'input','model':'QX40'},{},gen.build_symbols())
        label=next(c for c in page.conductors if c.get('num')=='P24' and c.get('displaytext')=='1')
        endpoint=next(key for key,e,_,_ in page.placed if e.get('uuid')==label.get('element2'))
        self.assertEqual(endpoint,'plc_in')
        self.assertIsNotNone(label.get('userx'))

    def test_round_power_terminals_align_wire_numbers_at_the_unit(self):
        page = gen.Page(gen.build_symbols())
        for i, label in enumerate(('P24', 'N24')):
            y = 700 + i * 30
            lane = page.place('junction', 45 + i * 27, y)
            unit = page.place('module_pin', 275, y, label='+' if i == 0 else '-')
            page.wire(lane, 'e', unit, 't', num=label, show=True)
        first, second = page.conductors
        self.assertEqual(first.get('userx'), second.get('userx'))
        self.assertGreater(float(first.get('userx')), 220)
        self.assertEqual(float(second.get('usery')) - float(first.get('usery')), 30)

    def test_fx5_analog_and_got_power_labels_use_explicit_positions(self):
        from renderers.hmi import build_body
        pages = [gen.build_fx_analog_page(dict(kind='fx5analog', model=model), {}, gen.build_symbols(), [])
                 for model in gen.FX5_ANALOG_SPECS]
        pages += [build_body(dict(model=model), gen.build_symbols(), spec, gen.Page, gen.Symbol,
                            gen.page_heading, (gen.LANE, gen.LANE_TOP_Y, gen.ctext))
                  for model, spec in gen.GOT_BODY.items()]
        count = 0
        for page in pages:
            labels = [c for c in page.conductors if c.get('num') in ('P24', 'N24') and c.get('displaytext') == '1']
            for label in labels:
                self.assertIsNotNone(label.get('userx'))
                self.assertIsNotNone(label.get('usery'))
            if labels:
                self.assertEqual(len({c.get('userx') for c in labels}), 1)
                count += 1
        self.assertGreater(count, 1)

    def test_output_power_labels_are_left_aligned_near_unit_terminals(self):
        rows=[{'アドレス':f'Y{i:X}','機器番号':'','信号名':'予備'} for i in range(16)]
        page=gen.build_iqr_page(rows,{'kind':'output','model':'QY40P'},{},gen.build_symbols())
        labels=[c for c in page.conductors if c.get('num') in ('P24','N24') and c.get('displaytext')=='1']
        self.assertEqual({c.get('num') for c in labels},{'P24','N24'})
        self.assertEqual(len({c.get('userx') for c in labels}),1)
        self.assertTrue(all(gen.OUT_X['tb']<float(c.get('userx'))<gen.OUT_X['load'] for c in labels))


if __name__=='__main__':
    unittest.main()
