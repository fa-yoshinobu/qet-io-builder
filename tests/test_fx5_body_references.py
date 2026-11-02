import unittest

import gen_io_page as gen


class Fx5BodyReferencesTest(unittest.TestCase):
    def build(self, tag='', details=()):
        body = {'kind': 'fx5body', 'model': 'FX5U-32MR/ES', 'tag': tag}
        page = gen.build_fx5_body_page(body, gen.build_symbols())
        page.post([(body, None)] + [(detail, None) for detail in details],
                  lambda detail: detail['number'])
        return page

    def texts(self, page):
        return [item.get('text') for item in page.texts]

    def test_catalog_does_not_list_other_cpu_models_in_each_body(self):
        details = [{'kind': 'fx5u', 'model': model, 'number': index + 1}
                   for index, model in enumerate(gen.FX5U_SPECS)]
        page = self.build(details=details)
        self.assertEqual(self.texts(page).count('本体の入出力'), 1)
        self.assertNotIn('FX5UC-32MT/D', self.texts(page))
        self.assertTrue(all(float(item.get('y')) >= 20 for item in page.texts))

    def test_same_model_with_a_different_tag_is_not_its_io_page(self):
        details = [{'kind': 'fx5u', 'model': 'FX5U-32MR/ES', 'tag': tag, 'number': number}
                   for tag, number in [('PLC2', 34), ('PLC1', 12)]]
        page = self.build('PLC1', details)
        self.assertEqual(self.texts(page).count('本体の入出力'), 1)
        self.assertIn('12', self.texts(page))
        self.assertNotIn('34', self.texts(page))

    def test_single_cpu_untagged_project_keeps_its_io_reference(self):
        page = self.build(details=[{'kind': 'fx5u', 'model': 'FX5U-32MR/ES', 'number': 5}])
        self.assertIn('本体の入出力', self.texts(page))
        self.assertIn('5', self.texts(page))


if __name__ == '__main__':
    unittest.main()
