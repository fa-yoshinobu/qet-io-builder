import unittest

import gen_io_page as gen


def unit_page(model, start=0, device='K1', load='RY'):
    spec = gen.IO_UNITS[model]
    prefix = 'X' if spec['io'] == 'in' else 'Y'
    page = {'kind': 'input' if spec['io'] == 'in' else 'output',
            'model': model, 'start': f'{start:X}', 'csv': f'{model}_{start}.csv'}
    rows = [{'アドレス': f'{prefix}{start + i:X}', '機器番号': device if i == 0 else '',
             '信号名': '確認', '負荷': load, '形式': 'MY2N'} for i in range(spec['points'])]
    return page, rows


class ProjectOutputDevicesTest(unittest.TestCase):
    def tearDown(self):
        gen.xref_reset([])

    def test_duplicate_outputs_on_different_pages_are_rejected_before_generation(self):
        pages = [unit_page('RX40C7'), unit_page('RY40NT5P', 0x10), unit_page('RY40NT5P', 0x20)]
        self.assertTrue(all(not gen.validate(rows, pg) for pg, rows in pages))
        with self.assertRaisesRegex(SystemExit, '機器番号重複: K1.*ページ設定2.*Y10.*ページ設定3.*Y20'):
            gen.build_project({'front_pages': False}, pages)

    def test_multiple_input_contacts_can_reference_one_output_coil(self):
        page, rows = unit_page('RX40C7')
        rows[1]['機器番号'] = 'K1'
        project, _ = gen.build_project({'front_pages': False}, [(page, rows), unit_page('RY40NT5P')])
        self.assertEqual(len(project.findall('diagram')), 2)
        self.assertEqual(gen.XREF['relay_type']['K1'], 'MY2N')

    def test_duplicates_include_fx_outputs_and_non_coil_loads(self):
        fx = ({'kind': 'fx5u', 'model': 'FX5U-32MT/ES'},
              {'in': [], 'out': [{'アドレス': 'Y0', '機器番号': 'H1', '負荷': 'PL'}]})
        with self.assertRaisesRegex(SystemExit, '機器番号重複: H1'):
            gen.xref_devices([fx, unit_page('QY40P', device='H1', load='PL')], {})

    def test_right_hand_unit_is_included_and_blank_tags_are_allowed(self):
        page, rows = unit_page('QY40P')
        page['right'], page['_right_rows'] = unit_page('QY40P', 0x10)
        with self.assertRaisesRegex(SystemExit, '機器番号重複: K1'):
            gen.xref_devices([(page, rows)], {})
        rows[0]['機器番号'] = ''
        page['_right_rows'][0]['機器番号'] = ''
        self.assertEqual(gen.xref_devices([(page, rows)], {}), set())


if __name__ == '__main__':
    unittest.main()
