import unittest

import gen_io_page as gen
import plc_configuration as plc


def page(model, modules=(), **values):
    return dict(kind='nxbody' if model.startswith('NX') else 'kvbody',
                model=model, modules=list(modules), **values)


class PlcConfigurationTest(unittest.TestCase):
    def test_category_catalog_and_defaults_preserve_tags(self):
        definitions = gen.read_unit_definitions()
        result = plc.resolve(page('KV-X550', ['KV-SIR32XT', 'KV-B16XC'],
                                  module_tags=['IN1', 'IN2']), definitions)
        self.assertEqual([m['bus'] for m in result['modules']], ['direct', 'legacy'])
        self.assertEqual([m['tag'] for m in result['modules']], ['IN1', 'IN2'])
        self.assertEqual(result['adapters'], [dict(model='KV-7000C', before_index=1, bus='legacy')])
        self.assertEqual(result['end_cover'], 'エンドユニット')
        self.assertEqual(result['modules'][1]['category'], 'kv_io')

    def test_old_bus_cannot_be_followed_by_high_speed_unit(self):
        with self.assertRaisesRegex(ValueError, 'CPU側'):
            plc.resolve(page('KV-X550', ['KV-B16XC', 'KV-SIR32XT']))

    def test_large_device_limit_does_not_replace_extension_stage_requirement(self):
        config = page('KV-X550', ['KV-B16XC'] * 17)
        with self.assertRaisesRegex(ValueError, '機器全体上限は48台.*増設段'):
            plc.resolve(config)
        self.assertTrue(any('増設段' in s for s in plc.resolve(config, complete=False)['warnings']))
        plc.resolve(page('KV-X550', ['KV-B16XC'] * 16))

    def test_unresolved_compatibility_is_rejected_in_editor_too(self):
        for config in (page('KV-X550', ['KV-SC20V']),
                       page('KV-EP02', ['KV-NC32EXE'])):
            with self.subTest(model=config['model']), self.assertRaisesRegex(ValueError, '保留'):
                plc.resolve(config, complete=False)
        plc.resolve(page('KV-X550', ['KV-SC20']))

    def test_nano_adapters_are_inserted_only_at_bus_changes(self):
        result = plc.resolve(page('KV-N24AR', ['KV-NC16EX', 'KV-N16EX']))
        self.assertEqual([a['model'] for a in result['adapters']], ['KV-N1', 'KV-NC1'])
        self.assertEqual(len(result['modules']), 2)
        explicit = plc.resolve(page('KV-N24AR', ['KV-N1', 'KV-NC16EX']))
        self.assertEqual(len(explicit['adapters']), 1)
        self.assertEqual([m['index'] for m in explicit['modules']], [1])
        with self.assertRaisesRegex(ValueError, '1構成'):
            plc.resolve(page('KV-N24AR', ['KV-NC16EX', 'KV-N16EX', 'KV-NC16EX']))

    def test_nano_physical_sockets_and_cpu_restrictions(self):
        for config in (page('KV-N14AR', ['KV-NC1EP']),
                       page('KV-NC32T', ['KV-N1AW']),
                       page('KV-N14AR', ['KV-N10L', 'KV-N1AW']),
                       page('KV-N40AR', ['KV-N1AW', 'KV-N1AW'])):
            with self.subTest(config=config), self.assertRaises(ValueError):
                plc.resolve(config)
        plc.resolve(page('KV-N40AR', ['KV-N10L', 'KV-N1AW']))
        plc.resolve(page('KV-NC32T', ['KV-NC20L']))

    def test_points_and_coupler_slots_are_separate_from_unit_count(self):
        with self.assertRaisesRegex(ValueError, '128点'):
            plc.resolve(page('KV-N14AR', ['KV-NC32EXT'] * 3))
        plc.resolve(page('KV-EP02', ['KV-NC4AD'] * 4))
        with self.assertRaisesRegex(ValueError, 'スロット'):
            plc.resolve(page('KV-EP02', ['KV-NC4AD'] * 5))
        plc.resolve(page('KV-EC01', ['KV-NC4AD'] * 8))

    def test_nx701_requires_its_power_and_has_no_local_nx(self):
        with self.assertRaisesRegex(ValueError, '電源ユニット'):
            plc.resolve(page('NX701-1600'))
        draft = plc.resolve(page('NX701-1600'), complete=False)
        self.assertTrue(any('電源ユニット' in message for message in draft['warnings']))
        plc.resolve(page('NX701-1600', ['NX-PA9001']))
        with self.assertRaises(ValueError):
            plc.resolve(page('NX701-1600', ['NX-PA9001', 'NX-ID3317']), complete=False)

    def test_nx_x_bus_and_remote_coupler_are_not_interchangeable(self):
        plc.resolve(page('NX502-1300', ['NX-EIP201'] * 4))
        with self.assertRaisesRegex(ValueError, '最大4'):
            plc.resolve(page('NX502-1300', ['NX-EIP201'] * 5), complete=False)
        for config in (page('NX102-1000', ['NX-EIP201']),
                       page('NX-EIC202', ['NX-PG0112']),
                       page('NX-ECC203', ['NX-ECT101'])):
            with self.subTest(config=config), self.assertRaises(ValueError):
                plc.resolve(config)
        plc.resolve(page('NX-ECC203', ['NX-PG0112']))

    def test_nx_io_supply_must_precede_bus_powered_module(self):
        with self.assertRaisesRegex(ValueError, 'I/O電源追加'):
            plc.resolve(page('NX102-1000', ['NX-ILM400']))
        self.assertTrue(plc.resolve(page('NX102-1000', ['NX-ILM400']), complete=False)['warnings'])
        plc.resolve(page('NX102-1000', ['NX-PF0730', 'NX-ILM400']))
        plc.resolve(page('NX-ECC203', ['NX-ILM400']))

    def test_explicit_old_firmware_is_rejected_but_missing_version_is_a_condition(self):
        config = page('KV-7500', ['KV-XH64EC'])
        self.assertTrue(any('2.4以上' in s for s in plc.validate(config)))
        with self.assertRaisesRegex(ValueError, '2.4'):
            plc.resolve(dict(config, cpu_version='2.3'))
        plc.resolve(dict(config, cpu_version='2.40', software_version='11.6'))
        with self.assertRaisesRegex(ValueError, '1.66'):
            plc.resolve(page('NX502-1300', ['NX-EIP201'], cpu_version='1.60',
                             module_versions=['1.01']))
        with self.assertRaisesRegex(ValueError, '確認範囲外'):
            plc.resolve(page('KV-X550', ['KV-XD02'], cpu_version='1.4', module_versions=['1.7']))
        plc.resolve(page('KV-X550', ['KV-XD02'], cpu_version='1.4.0', module_versions=['2.0']))

    def test_invalid_saved_arrays_and_bus_do_not_silently_truncate(self):
        for values in ({'module_tags': []}, {'module_buses': ['x']},
                       {'module_versions': ['bad']}, {'modules': ['unknown']},
                       {'modules': 'KV-SIR32XT'}):
            config = page('KV-X550', ['KV-SIR32XT'])
            config.update(values)
            with self.subTest(values=values), self.assertRaises(ValueError):
                plc.resolve(config, complete=False)


if __name__ == '__main__':
    unittest.main()
