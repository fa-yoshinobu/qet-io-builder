import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import gen_io_page as gen


OPTIONS = ('sd_card', 'memory_card', 'memory_cassette')
NZ_SD = [f'NZ1MEM-{size}GBSD' for size in (2, 4, 8, 16)]
LEGACY_SD = ['L1MEM-2GBSD', 'L1MEM-4GBSD']


def cpu_page(model, **options):
    q = model.startswith('Q')
    return dict(kind='qbody' if q else 'iqrbody', model=model,
                base_model='Q33B' if q else 'R35B',
                power_model='Q61P' if q else 'R61P', **options)


class CpuMemoryOptionsTest(unittest.TestCase):
    def cli(self, page, folder):
        source, target = Path(folder) / 'project.json', Path(folder) / 'drawing.qet'
        source.write_text(json.dumps({'front_pages': False, 'pages': [page]}), encoding='utf-8')
        with contextlib.redirect_stdout(io.StringIO()):
            gen.main(str(source), str(target))
        return target

    def test_q_cpu_groups_have_only_the_verified_memory_families(self):
        for model in ('Q00UCPU', 'Q01UCPU'):
            for key in OPTIONS:
                self.assertFalse(gen.Q_CPU[model][key + '_supported'])
                self.assertEqual(gen.Q_CPU[model][key + '_models'], [])
        q02 = gen.Q_CPU['Q02UCPU']
        self.assertTrue(q02['memory_card_supported'])
        self.assertEqual(set(q02['memory_card_models']), {
            'Q2MEM-1MBSN', 'Q2MEM-1MBS', 'Q2MEM-2MBSN', 'Q2MEM-2MBS',
            'Q3MEM-4MBS', 'Q3MEM-4MBS-SET', 'Q3MEM-8MBS', 'Q3MEM-8MBS-SET',
            'Q2MEM-2MBF', 'Q2MEM-4MBF', 'Q2MEM-8MBA', 'Q2MEM-16MBA', 'Q2MEM-32MBA'})
        self.assertFalse(q02['sd_card_supported'])
        self.assertFalse(q02['memory_cassette_supported'])
        for model in ('Q03UDVCPU', 'Q04UDVCPU', 'Q06UDVCPU', 'Q13UDVCPU', 'Q26UDVCPU'):
            spec = gen.Q_CPU[model]
            self.assertEqual(spec['sd_card_models'], NZ_SD + LEGACY_SD)
            self.assertEqual(spec['memory_cassette_models'], [f'Q4MCA-{size}MBS' for size in (1, 2, 4, 8)])
            self.assertFalse(spec['memory_card_supported'])
            self.assertEqual(spec['memory_card_models'], [])

    def test_iqr_cpu_groups_distinguish_small_standard_and_en_cpus(self):
        for key in OPTIONS:
            self.assertFalse(gen.IQR_CPU['R00CPU'][key + '_supported'])
            self.assertEqual(gen.IQR_CPU['R00CPU'][key + '_models'], [])
        for model in ('R01CPU', 'R02CPU'):
            spec = gen.IQR_CPU[model]
            self.assertEqual(spec['sd_card_models'], NZ_SD)
            self.assertFalse(spec['memory_cassette_supported'])
            self.assertEqual(spec['memory_cassette_models'], [])
        for size in (4, 8, 16, 32, 120):
            for suffix in ('CPU', 'ENCPU'):
                model = f'R{size:02}{suffix}'
                spec = gen.IQR_CPU[model]
                self.assertEqual(spec['sd_card_models'], NZ_SD + (LEGACY_SD if suffix == 'CPU' else []))
                self.assertEqual(spec['memory_cassette_models'], [f'NZ2MC-{capacity}MBS' for capacity in (1, 2, 4, 8, 16)])
                self.assertFalse(spec['memory_card_supported'])
                self.assertEqual(spec['memory_card_models'], [])
        for model, spec in {**gen.Q_CPU, **gen.IQR_CPU}.items():
            for key in OPTIONS:
                with self.subTest(model=model, key=key):
                    models = spec[key + '_models']
                    self.assertEqual(len(models), len(set(models)))
                    self.assertEqual(bool(models), spec[key + '_supported'])

    def test_unsupported_states_models_and_invalid_memory_states_are_rejected(self):
        for model, spec in {**gen.Q_CPU, **gen.IQR_CPU}.items():
            for key in OPTIONS:
                if not spec[key + '_supported']:
                    for values in ({key: '有'}, {key + '_model': 'ANY-MEMORY'}):
                        with self.subTest(model=model, values=values):
                            self.assertTrue(gen.cpu_option_error(cpu_page(model, **values), spec))
                for value in ('搭載不可', '装着', '', None, 1):
                    with self.subTest(model=model, key=key, value=value):
                        self.assertTrue(gen.cpu_option_error(cpu_page(model, **{key: value}), spec))
            self.assertEqual(gen.cpu_option_error(cpu_page(model), spec), '')

    def test_memory_models_must_be_strings_and_card_cassettes_must_be_candidates(self):
        for model, key in (('Q03UDVCPU', 'sd_card'), ('Q02UCPU', 'memory_card'),
                           ('Q03UDVCPU', 'memory_cassette'), ('R04CPU', 'memory_cassette')):
            spec = (gen.Q_CPU if model.startswith('Q') else gen.IQR_CPU)[model]
            for value in (None, True, 1, [], {}):
                with self.subTest(model=model, key=key, value=value):
                    error = gen.cpu_option_error(cpu_page(model, **{key: '有', key + '_model': value}), spec)
                    self.assertIn('文字列', error)
            for state in ('有', '無', '要確認'):
                self.assertEqual(gen.cpu_option_error(cpu_page(model, **{key: state}), spec), '')
            if key != 'sd_card':
                self.assertTrue(gen.cpu_option_error(cpu_page(model, **{key: '有', key + '_model': 'UNKNOWN'}), spec))
                self.assertEqual(gen.cpu_option_error(cpu_page(model, **{
                    key: '有', key + '_model': spec[key + '_models'][-1]}), spec), '')

    def test_cli_rejects_q_and_iqr_incompatible_options_without_replacing_output(self):
        cases = [cpu_page('Q00UCPU', sd_card='有', sd_card_model='NZ1MEM-2GBSD'),
                 cpu_page('Q02UCPU', memory_cassette='有', memory_cassette_model='Q4MCA-1MBS'),
                 cpu_page('Q03UDVCPU', memory_card='有', memory_card_model='Q2MEM-1MBSN'),
                 cpu_page('Q03UDVCPU', memory_cassette='有', memory_cassette_model='NZ2MC-8MBS'),
                 cpu_page('R00CPU', sd_card='有'),
                 cpu_page('R01CPU', memory_cassette='有', memory_cassette_model='NZ2MC-1MBS'),
                 cpu_page('R02CPU', sd_card='有', sd_card_model='L1MEM-2GBSD'),
                 cpu_page('R04ENCPU', sd_card='有', sd_card_model='L1MEM-4GBSD'),
                 cpu_page('R04ENCPU', sd_card='有', sd_card_model='l1mem-4gbsd'),
                 cpu_page('R04CPU', memory_cassette='有', memory_cassette_model='Q4MCA-8MBS'),
                 cpu_page('R04CPU', memory_cassette='有', memory_cassette_model='NZ2MC-8MBSE'),
                 cpu_page('RJ72GF15-T2', memory_cassette='有', memory_cassette_model='NZ2MC-8MBS')]
        for page in cases:
            with self.subTest(page=page), tempfile.TemporaryDirectory() as folder:
                target = Path(folder) / 'drawing.qet'
                target.write_bytes(b'previous drawing')
                with self.assertRaises(SystemExit):
                    self.cli(page, folder)
                self.assertEqual(target.read_bytes(), b'previous drawing')

    def test_free_text_sd_models_remain_allowed_and_iqr_battery_has_no_new_restriction(self):
        for model in ('Q03UDVCPU', 'R01CPU'):
            with self.subTest(model=model), tempfile.TemporaryDirectory() as folder:
                target = self.cli(cpu_page(model, sd_card='有', sd_card_model='案件指定SD'), folder)
                self.assertTrue(target.exists())
        spec = gen.IQR_CPU['R04CPU']
        self.assertNotIn('battery_models', spec)
        self.assertEqual(gen.cpu_option_error(cpu_page('R04CPU', battery_model='利用者指定電池'), spec), '')

    def test_drawings_show_selected_models_but_no_fine_option_conditions(self):
        cases = [cpu_page('Q02UCPU', memory_card='有', memory_card_model='Q3MEM-8MBS-SET'),
                 cpu_page('Q03UDVCPU', sd_card='有', sd_card_model='L1MEM-2GBSD',
                          memory_cassette='有', memory_cassette_model='Q4MCA-8MBS'),
                 cpu_page('R04CPU', sd_card='有', sd_card_model='L1MEM-4GBSD',
                          memory_cassette='有', memory_cassette_model='NZ2MC-16MBS')]
        for page in cases:
            with self.subTest(model=page['model']):
                root, _ = gen.build_project({'front_pages': False}, [(page, None)])
                texts = [item.get('text', '') for item in root.findall('./diagram/inputs/input')]
                for key in OPTIONS:
                    if page.get(key) == '有':
                        self.assertIn('有 (' + page[key + '_model'] + ')', texts)
                displayed = '\n'.join(texts)
                for detail in ('生産終了', '生産中止', '保護カバー', 'ファームウェア', 'GX Works3'):
                    self.assertNotIn(detail, displayed)


if __name__ == '__main__':
    unittest.main()
