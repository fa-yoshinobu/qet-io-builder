import copy
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET

import gen_io_page as gen
from project_wiring import data
from renderers import standard, wiring


def info(element, key):
    return next((item.text or '' for item in element.findall('./elementInformations/elementInformation')
                 if item.get('name') == key), '')


class WiringRenderingTest(unittest.TestCase):
    def setUp(self):
        self.page = gen.Page(gen.build_symbols())

    def apply(self, settings, part=1, page=None):
        return wiring.apply(page or self.page, data.normalize(settings), part, gen.Symbol, 'PLC1')

    def test_empty_settings_leave_existing_elements_positions_and_wires_unchanged(self):
        self.page.place('module_pin', 275, 120, label='P1')
        before = [ET.tostring(element) for element in self.page.elements]
        symbols = set(self.page.sym)
        self.assertEqual(self.apply({}), [])
        self.assertEqual(before, [ET.tostring(element) for element in self.page.elements])
        self.assertEqual(symbols, set(self.page.sym))
        self.assertFalse(self.page.shapes)
        self.assertFalse(self.page.conductors)

    def test_boundary_has_requested_coordinates_and_does_not_draw_on_another_part(self):
        settings = {'boundaries': [{'part': 2, 'x': 240, 'top': 75, 'bottom': 750,
                                   'left': '盤外', 'right': '盤内'}]}
        self.apply(settings)
        self.assertFalse(self.page.shapes)
        self.apply(settings, part=2)
        line = self.page.shapes[0]
        self.assertEqual([line.get(key) for key in ('x1', 'x2', 'y1', 'y2')], ['240', '240', '75', '750'])
        self.assertEqual(line.find('pen').get('style'), 'DashLine')
        self.assertEqual(line.find('pen').get('widthF'), '0.5')
        self.assertEqual([text.get('text') for text in self.page.texts], ['盤外', '盤内'])
        self.assertLess(float(self.page.texts[0].get('x')), 240)
        self.assertGreater(float(self.page.texts[1].get('x')), 240)
        self.assertTrue(all(text.get('font').startswith('MS Gothic,8,') for text in self.page.texts))
        self.assertFalse(self.page.elements)
        self.assertFalse(self.page.conductors)

    def test_normal_note_is_editable_and_keeps_supplied_connection_details_without_wiring(self):
        row = dict(x=100, y=100, unit_tag='PLC1', unit_terminal='X0', terminal_block='TB1', terminal='3',
                   wire='101', cable='W1', core='2', peer_tag='LS1', peer_terminal='13',
                   destination='5-C2', purpose='上限LS', section='0.75mm²', shield='片側接地', jumper='TB1:4')
        with patch.object(standard, 'collection_root', side_effect=AssertionError('通常注記に標準部品は不要')):
            refs = self.apply({'connections': [row]})
        self.assertFalse(refs)
        self.assertEqual(len(self.page.elements), 1)
        element = self.page.elements[0]
        label = info(element, 'label').replace('\n', '')
        for value in ('TB1:3', '線 101', 'W1/芯2', 'PLC1:X0 → LS1:13', '送り先 5-C2',
                      '線径 0.75mm²', 'シールド 片側接地', '用途 上限LS', '渡り TB1:4'):
            self.assertIn(value, label)
        self.assertFalse(element.findall('./terminals/terminal'))
        text = element.find('./dynamic_texts/dynamic_elmt_text')
        self.assertEqual(text.get('text_from'), 'ElementInfo')
        self.assertEqual(text.findtext('info_name'), 'label')
        self.assertTrue(text.get('font').startswith('MS Gothic,8,'))
        self.assertEqual(text.get('text_width'), str(wiring.NOTE_WIDTH + 8))
        self.assertFalse(self.page.conductors)
        self.assertEqual((element.get('x'), element.get('y')), ('100', '100'))

    def test_long_note_wraps_without_losing_text_and_uses_one_shared_symbol(self):
        purpose = '長い信号名を折り返して保持する' * 3
        self.apply({'connections': [{'purpose': purpose}, {'x': 300, 'purpose': '短い信号名'}]})
        first = info(self.page.elements[0], 'label')
        self.assertIn('\n', first)
        self.assertEqual(first.replace('\n', ''), '用途 ' + purpose)
        self.assertTrue(all(wiring._width(line) <= wiring.NOTE_WIDTH for line in first.split('\n')))
        self.assertEqual(self.page.elements[0].get('type'), self.page.elements[1].get('type'))
        self.assertEqual(sum(name == 'wiring_note' for name in self.page.sym), 1)

    def test_connection_endpoint_names_wrap_at_word_boundaries_and_only_long_tokens_split(self):
        text = 'PLC1:Ethernet → GOT1:Ethernet'
        lines = wiring._wrap(text)
        self.assertEqual(lines, ['PLC1:Ethernet → ', 'GOT1:Ethernet'])
        self.assertTrue(all(wiring._width(line) <= wiring.NOTE_WIDTH for line in lines))
        self.assertEqual(''.join(lines), text)
        long_token = 'PLC_' + 'X' * 80
        long_lines = wiring._wrap(long_token)
        self.assertGreater(len(long_lines), 1)
        self.assertTrue(all(wiring._width(line) <= wiring.NOTE_WIDTH for line in long_lines))
        self.assertEqual(''.join(long_lines), long_token)

    def test_outside_note_and_boundary_labels_fail_with_context(self):
        for settings in (
            {'connections': [{'x': 1250, 'purpose': '位置超過'}]},
            {'connections': [{'y': 790, 'purpose': '非常に長い用途説明' * 20}]},
            {'boundaries': [{'x': 0, 'left': '盤外'}]},
            {'boundaries': [{'top': 1, 'left': '盤外'}]},
        ):
            with self.subTest(settings=settings), self.assertRaisesRegex(ValueError, 'PLC1.*図枠外'):
                self.apply(settings)

    def test_native_report_pair_preserves_standard_source_and_has_no_automatic_conductor(self):
        second = gen.Page(self.page.sym)
        refs = self.apply({'connections': [{'reference': '送り', 'link_id': 'SIG-1', 'unit_tag': 'PLC1'}]})
        refs += self.apply({'connections': [{'reference': '受け', 'link_id': 'SIG-1', 'unit_tag': 'PLC2'}]}, page=second)
        self.assertEqual(wiring.link_references(refs), 1)
        self.assertEqual(wiring.link_references(refs), 1)
        for source, target in (refs, refs[::-1]):
            element = source['element']
            self.assertEqual([link.get('uuid') for link in element.findall('./links_uuids/link_uuid')],
                             [target['element'].get('uuid')])
            self.assertEqual(len(element.findall('./terminals/terminal')), 1)
            self.assertEqual(info(element, 'label'), '')  # nativeの参照文字はQETに任せる。
            self.assertEqual(element.get('freezeLabel'), 'false')
            native_text = element.find('./dynamic_texts/dynamic_elmt_text')
            self.assertEqual(native_text.get('text_from'), 'ElementInfo')
            self.assertEqual(native_text.findtext('info_name'), 'label')
            symbol = source['page'].sym[wiring.REPORTS[source['reference']][0]]
            original = ET.parse(standard.collection_root() / wiring.REPORTS[source['reference']][1]).getroot()
            saved = symbol.to_xml().find('definition')
            self.assertEqual(saved.get('link_type'), original.get('link_type'))
            self.assertEqual(saved.findtext('informations'), original.findtext('informations'))
            self.assertEqual(saved.findtext('./elementInformations/elementInformation[@name="qet_io_standard_source"]'),
                             wiring.REPORTS[source['reference']][1])
            shapes = lambda xml: [(item.tag, item.attrib) for item in xml.find('description') if item.tag != 'dynamic_text']
            self.assertEqual(shapes(saved), shapes(original))
            self.assertTrue(all(text.get('font') == wiring.FONT for text in saved.findall('./description/dynamic_text')))
            self.assertFalse(source['page'].conductors)

    def test_reference_pair_requires_two_opposite_roles_on_different_pages(self):
        for roles, same_page in ((['送り'], False), (['送り', '送り'], False),
                                 (['送り', '受け', '受け'], False), (['送り', '受け'], True)):
            with self.subTest(roles=roles, same_page=same_page):
                refs = []
                for index, role in enumerate(roles):
                    page = self.page if same_page else gen.Page(self.page.sym)
                    refs += self.apply({'connections': [{'reference': role, 'link_id': 'SIG', 'y': 110 + index * 100}]}, page=page)
                with self.assertRaisesRegex(ValueError, 'link_id SIG'):
                    wiring.link_references(refs)
                self.assertTrue(all(item['element'].find('links_uuids') is None for item in refs))

    def test_reference_configuration_is_complete_and_pair_validation_is_atomic(self):
        for row in ({'reference': '送り'}, {'link_id': 'SIG'}):
            with self.subTest(row=row), self.assertRaisesRegex(ValueError, '両方指定'):
                self.apply({'connections': [row]})
        refs = []
        for role, link_id in [('送り', 'GOOD'), ('受け', 'GOOD'), ('送り', 'BAD')]:
            refs += self.apply({'connections': [{'reference': role, 'link_id': link_id}]},
                               page=gen.Page(self.page.sym))
        with self.assertRaisesRegex(ValueError, 'link_id BAD'):
            wiring.link_references(refs)
        self.assertTrue(all(item['element'].find('links_uuids') is None for item in refs))

    def test_rendering_does_not_mutate_normalized_input_and_skips_blank_rows(self):
        settings = data.normalize({'boundaries': [{}], 'connections': [{}]})
        before = copy.deepcopy(settings)
        wiring.apply(self.page, settings, 1, gen.Symbol, 'PLC1')
        self.assertEqual(settings, before)
        self.assertFalse(self.page.elements)

    def test_note_overlap_is_checked_across_apply_calls_and_includes_native_arrow(self):
        for first in ({'purpose': '通常注記'}, {'reference': '送り', 'link_id': 'REF'}):
            with self.subTest(first=first):
                page = gen.Page(gen.build_symbols())
                self.apply({'connections': [first]}, page=page)
                before = [ET.tostring(element) for element in page.elements]
                with self.assertRaisesRegex(ValueError, '重なります.*位置を調整'):
                    self.apply({'connections': [{'y': 120, 'purpose': '二つ目'}]}, page=page)
                self.assertEqual(before, [ET.tostring(element) for element in page.elements])
                self.apply({'connections': [{'y': 210, 'purpose': '位置調整済み'}]}, page=page)
                self.assertEqual(len(page.wiring_note_boxes), 2)


if __name__ == '__main__':
    unittest.main()
