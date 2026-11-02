import unittest

import gen_io_page as gen


class ExtensionModelsTest(unittest.TestCase):
    def test_16_point_extensions(self):
        for model, output in (
            ('FX5-16ER/ES', 'relay'),
            ('FX5-16ET/ES', 'sink'),
            ('FX5-16ET/ESS', 'source'),
            ('FX5-16ET/ES-H', 'sink'),
            ('FX5-16ET/ESS-H', 'source'),
        ):
            with self.subTest(model=model):
                spec = gen.fx_spec({'kind': 'fx5ext', 'model': model, 'x_start': '20', 'y_start': '40'})
                self.assertEqual(spec['kind'], output)
                self.assertEqual(spec['inputs'], [f'X{i:o}' for i in range(0o20, 0o30)])
                self.assertEqual(spec['groups'], [('', [f'Y{i:o}' for i in range(0o40, 0o50)])])

    def test_unknown_extension_variant_is_rejected(self):
        with self.assertRaises(SystemExit):
            gen.fx_spec({'kind': 'fx5ext', 'model': 'FX5-16ET/INVALID'})

    def test_connector_models_and_input_mode(self):
        for model, common, output in (
            ('FX5-C16EX/D', 'COM', 'sink'),
            ('FX5-C16EX/DS', 'COM0', 'sink'),
            ('FX5-C32ET/DSS-TS', 'S/S', 'source'),
            ('FX5-C16EYR/D-TS', 'S/S', 'relay'),
        ):
            with self.subTest(model=model):
                spec = gen.fx_spec({'kind': 'fx5ext', 'model': model})
                self.assertEqual(spec['in_common'], common)
                self.assertEqual(spec['kind'], output)
        page = {'kind': 'fx5ext', 'model': 'FX5-C16EX/D', 'input_mode': 'source'}
        rows = [{'アドレス': a, '機器番号': ''} for a in gen.fx_spec(page)['inputs']]
        self.assertTrue(any('シンク入力のみ' in error for error in gen.validate_fx(page, rows, [])))

    def test_large_cpu_inputs_fit_half_pages(self):
        self.assertEqual([len(x) for x in gen.fx_split_inputs(list(range(48)))], [16, 16, 16])


if __name__ == '__main__':
    unittest.main()
