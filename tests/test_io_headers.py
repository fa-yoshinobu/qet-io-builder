import unittest

import gen_io_page as gen


class IoHeadersTest(unittest.TestCase):
    def test_output_power_labels_have_the_same_height(self):
        for left,right in ((432,454),(446,466)):
            page=gen.Page(gen.build_symbols())
            gen.output_lane_labels(page,left,'N24',right,'P24')
            labels=page.texts
            self.assertEqual([t.get('text') for t in labels],['N24','P24'])
            self.assertEqual(labels[0].get('y'),labels[1].get('y'))
            size=float(labels[0].get('font').split(',')[1])
            self.assertLessEqual((gen.text_w('N24',size)+gen.text_w('P24',size))/2+6,right-left)

    def test_left_and_right_units_have_individual_table_headers(self):
        rows = lambda prefix: [{'アドレス':f'{prefix}{i:X}','機器番号':'','信号名':'予備'} for i in range(16)]
        right = {'kind':'output','model':'QY10','tag':'DO1','slot':'2'}
        page = {'kind':'input','model':'QX40','tag':'DI1','slot':'1','right':right,'_right_rows':rows('Y')}
        root,_=gen.build_project(gen.project_config({'front_pages':False}),[(page,rows('X'))])
        texts=[t.get('text','') for t in root.findall('.//diagram/inputs/input')]
        for value in ('スロットNo. 1','DI1','QX40','スロットNo. 2','DO1','QY10'):
            self.assertEqual(texts.count(value),1)
        self.assertFalse(any(t.startswith('DI1  QX40') for t in texts))

    def test_header_aligns_with_io_table_edges(self):
        p=gen.Page(gen.build_symbols())
        gen.io_table_header(p,{'model':'RX40C7','slot':'1','tag':'DI1'},334,250,(45,100))
        frame=p.shapes[0]
        self.assertEqual((frame.get('x1'),frame.get('x2'),frame.get('y1'),frame.get('y2')),('334','584','34','70'))
        self.assertIn('スロットNo. 1',[t.get('text') for t in p.texts])
        for label,center in (('端子',356.5),('アドレス',406.5),('用途',509)):
            text=next(t for t in p.texts if t.get('text')==label)
            self.assertAlmostEqual(float(text.get('x'))+(gen.text_w(label,7)+2*gen.TEXT_MARGIN)/2,center,delta=0.1)
            self.assertAlmostEqual(float(text.get('y'))+(7*gen.PX_PER_PT+2*gen.TEXT_MARGIN)/2,61,delta=0.1)


if __name__=='__main__':
    unittest.main()
