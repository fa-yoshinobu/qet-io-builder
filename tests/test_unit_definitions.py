import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import gen_io_page as gen


class UnitFilesTest(unittest.TestCase):
    def test_all_model_names_are_unique(self):
        d = gen.read_unit_definitions()
        self.assertTrue(all(d[category] for category in ('iqr_q', 'fx5_cpu', 'fx5_ext', 'fx5_analog', 'q_analog')))
        self.assertEqual(len(gen.fx_cpu_models()), len(set(gen.fx_cpu_models())))

    def test_duplicate_model_is_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)
            item={'category':'iqr_q','model':'RX1','definition':{}}
            for name in ('one.json','two.json'):
                (p/name).write_text(json.dumps(item), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, '重複'):
                gen.read_unit_definitions(t)

    def test_invalid_cpu_variant_is_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            item={'category':'fx5_cpu','model':'FX5U-32MR/ES','definition':{'base':'FX5U-32M','variants':['T/ES']}}
            (Path(t)/'wrong.json').write_text(json.dumps(item),encoding='utf-8')
            with self.assertRaisesRegex(ValueError, '一致しません'):
                gen.read_unit_definitions(t)

    def test_duplicate_signal_terminals_are_rejected_after_preset_expansion(self):
        for pins in (['TB1', 'TB1'], ['TB1', ' tb1 '], 'TEST_DUPLICATE'):
            with self.subTest(pins=pins), tempfile.TemporaryDirectory() as folder:
                item = {'category': 'iqr_q', 'model': 'TEST_IO',
                        'definition': {'pins': pins, 'points': 2}}
                (Path(folder) / 'unit.json').write_text(json.dumps(item), encoding='utf-8')
                with patch.dict(gen.PIN_PRESETS, TEST_DUPLICATE=['TB1', 'TB1']):
                    with self.assertRaisesRegex(ValueError, 'TEST_IO.*信号端子.*重複'):
                        gen.load_units(folder)

    def test_blank_or_non_string_signal_terminals_are_rejected(self):
        for pin in ('', ' ', None, 1):
            with self.subTest(pin=pin), tempfile.TemporaryDirectory() as folder:
                item = {'category': 'remote_io', 'model': 'TEST_IO',
                        'definition': {'pins': ['TB1', pin], 'points': 2}}
                (Path(folder) / 'unit.json').write_text(json.dumps(item), encoding='utf-8')
                with self.assertRaisesRegex(ValueError, '信号端子.*文字列'):
                    gen.load_units(folder)

    def test_distinct_signal_terminals_and_shared_common_load(self):
        with tempfile.TemporaryDirectory() as folder:
            item = {'category': 'iqr_q', 'model': 'TEST_IO',
                    'definition': {'pins': ['TB1', 'TB2'], 'points': 2, 'com': ['TB3', 'TB4']}}
            (Path(folder) / 'unit.json').write_text(json.dumps(item), encoding='utf-8')
            self.assertEqual(gen.load_units(folder)[0]['TEST_IO']['pins'], ['TB1', 'TB2'])

    def test_mixed_signal_terminals_are_checked_in_each_direction(self):
        for category in ('q_mixed', 'iqr_mixed', 'remote_mixed'):
            for direction in ('input', 'output'):
                with self.subTest(category=category, direction=direction), tempfile.TemporaryDirectory() as folder:
                    definition = {key: {'pins': ['1', '2'], 'points': 2} for key in ('input', 'output')}
                    definition[direction]['pins'] = ['1', '1']
                    item = {'category': category, 'model': 'TEST_MIXED', 'definition': definition}
                    (Path(folder) / 'mixed.json').write_text(json.dumps(item), encoding='utf-8')
                    with self.assertRaisesRegex(ValueError, f'TEST_MIXED {direction}.*信号端子.*重複'):
                        gen.load_units(folder)

    def test_mixed_connectors_can_reuse_pin_names_between_directions(self):
        with tempfile.TemporaryDirectory() as folder:
            definition = {key: {'pins': ['1', '2'], 'points': 2} for key in ('input', 'output')}
            item = {'category': 'q_mixed', 'model': 'TEST_MIXED', 'definition': definition}
            (Path(folder) / 'mixed.json').write_text(json.dumps(item), encoding='utf-8')
            self.assertEqual(gen.load_units(folder)[15]['TEST_MIXED']['input']['pins'], ['1', '2'])

    def test_reload_keeps_renderer_catalog_references_and_failure_preserves_data(self):
        from renderers.melsec_analog import Q_ANALOG
        original = gen.Q_ANALOG
        try:
            with tempfile.TemporaryDirectory() as folder:
                item = {'category': 'q_analog', 'model': 'CUSTOM_ANALOG', 'definition': {'channels': []}}
                (Path(folder) / 'unit.json').write_text(json.dumps(item), encoding='utf-8')
                gen.use_units(folder)
                self.assertIs(gen.Q_ANALOG, original)
                self.assertIs(Q_ANALOG, original)
                self.assertEqual(Q_ANALOG['CUSTOM_ANALOG'], {'channels': []})
                with tempfile.TemporaryDirectory() as empty:
                    with self.assertRaises(ValueError):
                        gen.use_units(empty)
                self.assertEqual(Q_ANALOG['CUSTOM_ANALOG'], {'channels': []})
        finally:
            gen.use_units()

if __name__ == '__main__':
    unittest.main()
