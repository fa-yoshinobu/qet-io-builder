import unittest

import gen_io_page as gen
from renderers.analog import channel_rows, extra_rows, nc_rows, readonly_symbol


def information(element, key):
    return next((item.text for item in element.findall('./elementInformations/elementInformation')
                 if item.get('name') == key), '')


class AnalogNcTest(unittest.TestCase):
    def test_fx5_nc_keeps_the_documented_terminal_order_without_invented_numbers(self):
        expected = {
            'FX5-4A-ADP': ['V1+', 'I1+', 'COM1', 'V2+', 'I2+', 'COM2', 'NC',
                          'V3+', 'I3+', 'COM3', 'V4+', 'I4+', 'COM4'],
            'FX5-4DA-ADP': ['V1+', 'I1+', 'COM1', 'V2+', 'I2+', 'COM2',
                           'V3+', 'I3+', 'COM3', 'V4+', 'I4+', 'COM4', 'NC'],
            'FX5-4AD-PT-ADP': ['L1+', 'L1-', 'I1-', 'L2+', 'L2-', 'I2-',
                              'L3+', 'L3-', 'I3-', 'L4+', 'L4-', 'I4-', 'NC'],
            'FX5-4AD-TC-ADP': ['NC', 'L1+', 'L1-', 'NC', 'L2+', 'L2-', 'NC',
                              'L3+', 'L3-', 'NC', 'L4+', 'L4-', 'NC'],
        }
        for model, signals in expected.items():
            with self.subTest(model=model):
                spec = gen.FX5_ANALOG_SPECS[model]
                rows = [row for index in range(4) for row in channel_rows(spec, index)]
                self.assertEqual([row['signal'] for row in rows], signals)
                self.assertTrue(all(row['pin'] == '' and not row['connectable']
                                    for row in rows if row['signal'] == 'NC'))

    def test_remote_nc_uses_io_connector_scope_and_keeps_power_nc_on_the_body(self):
        spec = gen.REMOTE_ANALOG['NZ2GFCE-60DAI8']
        rows = nc_rows(spec)
        self.assertEqual([(row['channel'], row['pin']) for row in rows],
                         [(channel, pin) for channel in range(1, 9) for pin in ('3', '4')])
        self.assertFalse(extra_rows(spec))
        self.assertEqual([row['signal'] for row in channel_rows(spec, 0)], ['I+', 'I-', 'NC', 'NC'])
        self.assertTrue(all(not row['connectable'] for row in rows))
        self.assertEqual([row['pin'] for row in extra_rows(gen.REMOTE_ANALOG['NZ2GF2B-60AD4'])
                          if row['signal'] == 'NC'], ['1', '2'])

    def test_readonly_symbol_removes_only_the_connection_points(self):
        symbols = gen.build_symbols()
        for original in ('plc_in', 'module_pin'):
            with self.subTest(original=original):
                key = readonly_symbol(symbols, original)
                self.assertFalse(symbols[key].terminals)
                self.assertTrue(symbols[original].terminals)
                self.assertEqual(readonly_symbol(symbols, original), key)
                self.assertEqual([part for part in symbols[key].parts if part[0] != 'line'],
                                 [part for part in symbols[original].parts if part[0] != 'line'])

    def test_fx5_drawings_show_all_nc_without_connectable_points_or_overflow(self):
        expected = {'FX5-4A-ADP': (15, 1), 'FX5-4DA-ADP': (15, 1),
                    'FX5-4AD-PT-ADP': (12, 1), 'FX5-4AD-TC-ADP': (8, 5)}
        for model, (active_count, nc_count) in expected.items():
            with self.subTest(model=model):
                page = gen.build_fx_analog_page({'kind': 'fx5analog', 'model': model}, {}, gen.build_symbols(), [])
                active = [element for key, element, x, y in page.placed if key == 'module_pin']
                nc = [element for key, element, x, y in page.placed if information(element, 'label') == 'NC']
                self.assertEqual((len(active), len(nc)), (active_count, nc_count))
                self.assertTrue(all(not element.findall('./terminals/terminal') for element in nc))
                self.assertTrue(all(x >= gen.HALF_W for key, element, x, y in page.placed))
                boxes = [shape for shape in page.shapes if shape.get('type') == 'Rectangle']
                self.assertLess(max(float(shape.get('y2')) for shape in boxes), 782)
                self.assertTrue(all(float(shape.get('x2')) - float(shape.get('x1')) == 235 for shape in boxes))
                self.assertTrue(any(shape.get('y1') == '52' for shape in boxes))

    def test_remote_table_restores_numbered_nc_without_connectable_points(self):
        expected = {'NZ2GF2B-60AD4': ['1', '2'],
                    'NZ2GF2BN-60DA4': ['1', '2', '6', '10', '14', '18'],
                    'NZ2GF2B-60TCTT4': ['6', '11', '13'],
                    'NZ2GN2B-60DA4': ['4', '8', '12', '16', '17', '18']}
        for model, pins in expected.items():
            with self.subTest(model=model):
                page = gen.build_fx_analog_page({'kind': 'remoteanalog', 'model': model}, {}, gen.build_symbols(), [])
                nc = [element for key, element, x, y in page.placed if information(element, 'label') == 'NC']
                self.assertEqual([information(element, 'auxiliary1') for element in nc], pins)
                self.assertTrue(all(not element.findall('./terminals/terminal') for element in nc))
                self.assertFalse(page.conductors)
                self.assertLessEqual(max(y for key, element, x, y in page.placed), 770)

    def test_econ_nc_stays_with_its_channel_and_fits_one_page(self):
        for model, expected_count in [('NZ2GFCE-60ADV8', 8), ('NZ2GFCE-60DAI8', 16)]:
            with self.subTest(model=model):
                spec = gen.REMOTE_ANALOG[model]
                self.assertEqual(gen.analog_page_channels('remoteanalog', spec), 8)
                page = gen.build_fx_analog_page({'kind': 'remoteanalog', 'model': model}, {}, gen.build_symbols(), [])
                nc = [element for key, element, x, y in page.placed if information(element, 'label') == 'NC']
                self.assertEqual(len(nc), expected_count)
                self.assertTrue(all('e-CON' in information(element, 'comment') for element in nc))
                self.assertTrue(all(not element.findall('./terminals/terminal') for element in nc))
                self.assertLessEqual(max(y for key, element, x, y in page.placed), 770)


if __name__ == '__main__':
    unittest.main()
