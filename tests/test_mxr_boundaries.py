import unittest

import gen_io_page as gen
from renderers.controllers import mxr_symbol


class MxrBoundariesTest(unittest.TestCase):
    def test_internal_boundaries_are_full_height_dashed_with_outer_frame_weight(self):
        for model in (m for m, spec in gen.IQR_CPU.items() if spec.get('network_part')):
            for extensions, height, top in (([], 380, 100), ([dict(base_model='R65B', power_model='R61P')], 190, 124)):
                with self.subTest(model=model, height=height):
                    page = gen.build_iqr_body_page(dict(kind='iqrbody', model=model, base_model='R35B',
                                                       power_model='R61P', extensions=extensions), gen.build_symbols())[0][1]
                    for x in (365 + 73 * i for i in range(gen.IQR_CPU[model]['network_part'].get('slots', 1))):
                        vertical = [s for s in page.shapes if s.get('type') == 'Line'
                                    and float(s.get('x1')) == float(s.get('x2')) == x
                                    and float(s.get('y1')) == top]
                        self.assertEqual(len(vertical), 1)
                        self.assertEqual(float(vertical[0].get('y2')), top + height)
                        pen = vertical[0].find('pen')
                        self.assertEqual(pen.get('style'), 'DashLine')
                        self.assertEqual(float(pen.get('widthF')), 1.5)

    def test_cpu_symbol_does_not_cover_the_dashed_boundary_with_a_solid_edge(self):
        for height in (190, 380):
            for symbol in (mxr_symbol('test', height), gen.iqr_cpu_symbol('test_en', True, True, height, True)):
                self.assertFalse(any(tag == 'rect' and a.get('width') == 80 for tag, a in symbol.parts))
                self.assertFalse(any(tag == 'line' and a['x1'] == a['x2'] == 70 for tag, a in symbol.parts))


if __name__ == '__main__':
    unittest.main()
