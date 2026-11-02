"""外部給電付きCC-Link IEユニットの物理2スロット占有。"""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from xml.etree import ElementTree as ET

import gen_io_page as gen
from webgui.api import Api

CASES = (
    ('iqrbody', 'R04CPU', 'R35B', 'R61P', 'RJ71GP21S-SX', 'RX40C7'),
    ('qbody', 'Q03UDVCPU', 'Q35B', 'Q61P', 'QJ71GP21S-SX', 'QX40'),
)


def config(case):
    kind, cpu, base, power, _, _ = case
    return dict(kind=kind, model=cpu, base_model=base, power_model=power)


class NetworkTwoSlotsTest(unittest.TestCase):
    def test_definition_and_successor_address(self):
        for case in CASES:
            with self.subTest(model=case[4]):
                spec = gen.slot_definition(case[4], case[0] == 'qbody')
                self.assertEqual((spec['slots'], spec['occupied_io_points'], spec['slot_io_points']), (2, 48, [16, 32]))
                stages, errors, _ = gen.slot_assignments(dict(config(case), modules=[case[4], '', case[5]]))
                self.assertFalse(errors)
                self.assertTrue(stages[0][1]['reserved'])
                self.assertEqual(stages[0][1]['points'], 0)
                self.assertEqual(stages[0][2]['start'], 0x30)

    def test_gui_reserves_neighbor_and_rejects_overlap_and_end_slot(self):
        for case in CASES:
            with self.subTest(model=case[4]):
                api = Api()
                api._data['pages'] = [config(case)]
                result = api.set_module(0, 0, 0, case[4])
                self.assertNotIn('error', result)
                items = {i['id']: i for i in result['rack']['stages'][0]['items']}
                self.assertEqual(items['0:1']['type'], 'reserved')
                self.assertIn('error', api.set_module(0, 0, 1, case[5]))
                self.assertIn('error', api.set_module(0, 0, 4, case[4]))
                result = api.set_module(0, 0, 2, case[5])
                self.assertNotIn('error', result)
                item = next(i for i in result['rack']['stages'][0]['items'] if i['id'] == '0:2')
                self.assertEqual(item['start'], 0x30)
                self.assertEqual(api._slot_number(api._data['pages'][0], 0, 0), 1)

    def test_qet_generation_reserves_neighbor_and_rejects_occupied_slot(self):
        for case in CASES:
            with self.subTest(model=case[4]), tempfile.TemporaryDirectory() as folder:
                source, target = Path(folder) / 'project.json', Path(folder) / 'drawing.qet'
                page = dict(config(case), modules=[case[4], '', case[5]])
                source.write_text(json.dumps(dict(front_pages=False, pages=[page])), encoding='utf-8')
                with contextlib.redirect_stdout(io.StringIO()):
                    gen.main(str(source), str(target))
                texts = [t.get('text') for t in ET.parse(target).getroot().findall('.//diagram/inputs/input')]
                self.assertIn('外部供給電源', texts)
                self.assertNotIn('占有', texts)
                self.assertIn('X/Y010〜', texts)
                self.assertIn('X/Y02F', texts)
                self.assertIn('X030〜', texts)
                page['modules'] = [case[4], case[5]]
                source.write_text(json.dumps(dict(front_pages=False, pages=[page])), encoding='utf-8')
                with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
                    gen.main(str(source), str(target))

    def test_drawing_places_power_on_left_network_on_right_and_dashes_middle(self):
        for case in CASES:
            with self.subTest(model=case[4]):
                page = gen.build_iqr_body_page(dict(config(case), modules=[case[4], ''], module_tags=['NET1', '']), gen.build_symbols())[0][1]
                texts = {t.get('text'): t for t in page.texts}
                self.assertLess(float(texts['外部供給電源'].get('x')), float(texts[case[4]].get('x')))
                self.assertGreater(float(texts['NET1'].get('x')), 438)
                middle = [s for s in page.shapes if s.get('type') == 'Line'
                          and float(s.get('x1')) == float(s.get('x2')) == 438
                          and float(s.get('y1')) == 100 and float(s.get('y2')) == 480]
                self.assertEqual(len(middle), 1)
                self.assertEqual(middle[0].find('pen').get('style'), 'DashLine')
                self.assertEqual(float(middle[0].find('pen').get('widthF')), 1.5)


if __name__ == '__main__':
    unittest.main()
