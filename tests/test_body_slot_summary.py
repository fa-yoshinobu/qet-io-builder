import unittest

import gen_io_page as gen


class BodySlotSummaryTest(unittest.TestCase):
    def body(self, **updates):
        page = {'kind': 'qbody', 'model': 'Q03UDVCPU', 'base_model': 'Q35B',
                'power_model': 'Q61P', 'modules': ['QX40', 'QY10', 'Q64AD', 'QJ71E71-100']}
        page.update(updates)
        return page, gen.build_iqr_body_page(page, gen.build_symbols())

    def texts(self, page):
        return [item.get('text', '') for item in page.texts]

    def references(self, page):
        return [(float(item.get('x')), item.get('text')) for item in page.texts
                if item.get('text', '').startswith('→ ')]

    def test_address_ranges_are_complete_and_aligned_across_module_types(self):
        _, pages = self.body()
        page = pages[0][1]
        for expected in (['X000〜', 'Y010〜', 'X/Y020〜', 'X/Y030〜', '050〜'],
                         ['X00F', 'Y01F', 'X/Y02F', 'X/Y04F', '05F']):
            found = [item for item in page.texts if item.get('text') in expected]
            self.assertEqual({item.get('text') for item in found}, set(expected))
            self.assertEqual(len({item.get('y') for item in found}), 1)
            for item in found:
                self.assertLessEqual(gen.text_w(item.get('text'), 7), 73 - 8)

    def test_mixed_summary_keeps_input_and_output_point_counts_distinct(self):
        self.assertEqual(gen.slot_summary('QX48Y57', True), '入力8点\n出力7点')
        _, pages = self.body(modules=['QX48Y57', 'QY10'])
        texts = self.texts(pages[0][1])
        for value in ('X/Y000〜', 'X/Y007', 'Y008〜', 'Y017'):
            self.assertIn(value, texts)

    def test_same_model_references_follow_tags_when_detail_order_is_reversed(self):
        body, pages = self.body(modules=['QJ71E71-100'] * 2, module_tags=['NET1', 'NET2'])
        second = {'kind': 'qcomm', 'left_model': 'QJ71E71-100', 'left_tag': 'NET2'}
        first = {'kind': 'qcomm', 'right_model': 'QJ71E71-100', 'right_tag': 'NET1'}
        numbers = {id(second): 2, id(first): 3}
        page = pages[0][1]
        page.post([(body, None), (second, None), (first, None)], lambda pg: numbers.get(id(pg)))
        self.assertEqual([text for _, text in sorted(self.references(page))], ['→ 3頁', '→ 2頁'])

    def test_both_units_on_one_detail_page_can_be_referenced(self):
        for detail in ({'left_model': 'QJ71E71-100', 'left_tag': 'NET2',
                        'right_model': 'QJ71E71-100', 'right_tag': 'NET1'},
                       {'model': 'QJ71E71-100', 'tag': 'NET2',
                        'right': {'model': 'QJ71E71-100', 'tag': 'NET1'}}):
            with self.subTest(detail=detail):
                body, pages = self.body(modules=['QJ71E71-100'] * 2, module_tags=['NET1', 'NET2'])
                page = pages[0][1]
                page.post([(body, None), (detail, None)], lambda _: 7)
                self.assertEqual([text for _, text in self.references(page)], ['→ 7頁', '→ 7頁'])

    def test_explicit_tag_never_falls_back_to_a_different_unit(self):
        body, pages = self.body(modules=['QJ71E71-100'], module_tags=['NET1'])
        detail = {'left_model': 'QJ71E71-100', 'left_tag': 'NET2'}
        page = pages[0][1]
        page.post([(body, None), (detail, None)], lambda _: 7)
        self.assertFalse(self.references(page))

    def test_untagged_units_keep_sequential_detail_references(self):
        body, pages = self.body(modules=['QJ71E71-100'] * 2)
        first, second = ({'left_model': 'QJ71E71-100'} for _ in range(2))
        numbers = {id(first): 2, id(second): 3}
        page = pages[0][1]
        page.post([(body, None), (first, None), (second, None)], lambda pg: numbers.get(id(pg)))
        self.assertEqual([text for _, text in sorted(self.references(page))], ['→ 2頁', '→ 3頁'])

    def test_network_reserved_slot_and_extension_keep_address_allocation(self):
        _, pages = self.body(kind='iqrbody', model='R04ENCPU', base_model='R35B',
                             power_model='R61P', modules=['RX41C4'],
                             extensions=[{'base_model': 'R65B', 'power_model': 'R61P',
                                          'modules': ['RY41NT2P']}])
        texts = self.texts(pages[0][1])
        for value in ('X/Y000〜01F', 'X020〜', 'X03F', 'Y070〜', 'Y08F'):
            self.assertIn(value, texts)


if __name__ == '__main__':
    unittest.main()
