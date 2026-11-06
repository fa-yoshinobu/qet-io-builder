import copy
import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from webgui.api import Api


class VendorConfigurationsApiTest(unittest.TestCase):
    def checked(self, result):
        self.assertIsInstance(result, dict)
        self.assertNotIn('error', result, result)
        return result

    def configured(self, maker, series, cpu):
        api = Api()
        snapshot = self.checked(api.new_configuration(maker, series))
        self.assertEqual((snapshot['maker'], snapshot['index']), (maker, 0))
        page = self.checked(api.page(0))
        self.assertEqual(page['values']['kind'], 'kvbody' if maker == 'keyence' else 'nxbody')
        self.assertIn(cpu, {row['model'] for row in self.checked(api.catalog('model', 0))['rows']})
        values = dict(page['values'], model=cpu, tag='PLC1')
        self.checked(api.update_page(0, values, page['extra'], 'model'))
        return api

    def modules(self, api):
        rack = self.checked(api.page(0))['rack']
        rows = [item for stage in rack['stages'] for item in stage['items'] if item['type'] == 'module']
        return sorted(rows, key=lambda item: item['slot'])

    def test_bundle_fills_all_bodies_and_overview_keeps_edited_details(self):
        api = self.configured('keyence', 'KV Nano', 'KV-NC32T')
        self.checked(api.set_module(0, 0, 0, 'KV-NC20L', '', 'RS-485（2線式）'))
        detail = self.checked(api.create_unit_page(0, 0, 0, 'kv_io'))['index']
        manual = self.checked(api.page(detail))
        self.checked(api.update_page(detail, dict(manual['values'], title='盤内通信'), manual['extra']))
        self.checked(api.duplicate_page(0))
        before = copy.deepcopy(api._data)
        with tempfile.TemporaryDirectory() as folder:
            full = Path(folder) / 'full.qet'
            overview = Path(folder) / 'overview.qet'
            full.write_text('existing')
            self.assertIn('confirm', api.generate_configuration(True, str(full)))
            self.assertEqual(api._data, before)
            self.checked(api.generate_configuration(True, str(full), True))
            after = copy.deepcopy(api._data)
            self.assertEqual(len(after['pages']), 6)
            self.assertEqual(sum(page.get('title') == '盤内通信' for page in after['pages']), 1)
            self.assertIn('S/R(+)', full.read_text(encoding='utf-8'))
            self.checked(api.generate_configuration(False, str(overview)))
            self.assertEqual(len(ET.parse(overview).getroot().findall('diagram')), 2)
            self.assertEqual(api._data, after)
            self.checked(api.undo())
            self.assertEqual(api._data, before)

    def test_bundle_failure_restores_files_and_project(self):
        api = self.configured('omron', 'NX', 'NX502-1300')
        before = copy.deepcopy(api._data)
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'failed.qet'
            report = target.with_name('failed_iolist.csv')
            for path in (target, report):
                path.write_text('original')
            from os import replace
            def fail_report(src, dest):
                if Path(dest) == report:
                    raise PermissionError('locked')
                replace(src, dest)
            with patch('webgui.api.os.replace', side_effect=fail_report):
                self.assertIn('locked', api.generate_configuration(True, str(target), True)['error'])
            self.assertEqual([p.read_text() for p in (target, report)], ['original', 'original'])
            self.assertEqual(api._data, before)

    def test_new_configuration_uses_selected_root_and_protects_current_project(self):
        api = Api()
        choices = self.checked(api.configuration_roots('omron', 'NX'))['rows']
        self.assertIn(('NX502-1300', 'CPU'), [(r['model'], r['group']) for r in choices])
        self.assertIn(('NX-ECC203', 'カプラ'), [(r['model'], r['group']) for r in choices])
        self.checked(api.new_configuration('omron', 'NX', 'NX502-1300'))
        self.assertIn('x', [bus for bus, _ in self.checked(api.page(0))['rack']['bus_options']])
        self.checked(api.set_module(0, 0, 0, 'NX-EIP201', 'x'))
        before = self.checked(api.page(0))
        for maker, series, wrong in [('omron', 'NX', 'NX-EIP201'), ('keyence', 'KV Nano', 'KV-8000')]:
            self.assertIn('error', api.new_configuration(maker, series, wrong))
            self.assertEqual(self.checked(api.page(0)), before)
        opened = self.checked(api.new_configuration('omron', 'NX', 'NX-ECC203'))
        self.assertEqual(opened['pages'][0]['model'], 'NX-ECC203')

    def test_configure_batch_round_trip_undo_and_generate(self):
        cases = [
            ('omron', 'NX', 'NX502-1300', [
                ('NX-EIP201', 'x', 'NET1'),
                ('NX-PF0630', 'nx', 'PWR1'),
                ('NX-ID3317', 'nx', 'DI1'),
            ], None),
            ('keyence', 'KV Nano', 'KV-N24DT', [('KV-NC16EX', '', 'DI1')], 'KV-N1'),
            ('keyence', 'KV-8000', 'KV-8000', [('KV-B16XC', 'legacy', 'DI1')], 'KV-7000C'),
        ]
        for maker, series, cpu, selected, adapter in cases:
            with self.subTest(cpu=cpu), tempfile.TemporaryDirectory() as folder:
                api = self.configured(maker, series, cpu)
                for slot, (model, bus, tag) in enumerate(selected):
                    self.checked(api.set_module(0, 0, slot, model, bus))
                    self.checked(api.set_module_tag(0, 0, slot, tag))
                rows = self.modules(api)
                self.assertEqual([(row['model'], row['tag']) for row in rows],
                                 [(model, tag) for model, _, tag in selected])
                for row, (_, bus, _) in zip(rows, selected):
                    self.assertTrue(row['bus'])
                    if bus:
                        self.assertEqual(row['bus'], bus)
                if adapter:
                    rack = self.checked(api.page(0))['rack']
                    self.assertIn(adapter, {item['model'] for stage in rack['stages']
                                            for item in stage['items'] if item['type'] == 'adapter'})

                before = self.checked(api.snapshot())['pages']
                made = self.checked(api.create_all_unit_pages(0))
                details = Counter((page['model'], page['tag']) for page in made['pages'] if not page['body'])
                for pair in [(cpu, 'PLC1'), *[(model, tag) for model, _, tag in selected]]:
                    self.assertEqual(details[pair], 1, (pair, made))
                again = self.checked(api.create_all_unit_pages(0))
                self.assertEqual(again['pages'], made['pages'], 'Repeated batch creation duplicated detail pages')
                self.assertEqual(self.checked(api.undo())['pages'], before)
                self.assertEqual(self.checked(api.redo())['pages'], made['pages'])

                path = Path(folder) / 'configuration.json'
                self.checked(api.save_as(str(path)))
                saved = json.loads(path.read_text(encoding='utf-8'))
                self.assertEqual(saved['maker'], maker)
                self.assertEqual(saved['pages'][0]['modules'], [model for model, _, _ in selected])
                self.assertEqual(saved['pages'][0]['module_tags'], [tag for _, _, tag in selected])
                self.assertEqual(saved['pages'][0]['module_buses'], [row['bus'] for row in rows])
                loaded = Api()
                opened = self.checked(loaded.open_configuration(maker, str(path)))
                self.assertEqual(opened['maker'], maker)
                self.assertEqual([(row['model'], row['tag'], row['bus']) for row in self.modules(loaded)],
                                 [(row['model'], row['tag'], row['bus']) for row in rows])
                target = Path(folder) / 'configuration.qet'
                generated = self.checked(loaded.generate(str(target)))
                self.assertTrue(generated.get('ok'), generated)
                diagrams = ET.parse(target).getroot().findall('diagram')
                self.assertGreaterEqual(len(diagrams), 2, 'Only the configuration overview was generated')
                if adapter:
                    self.assertIn(adapter, ET.tostring(diagrams[0], encoding='unicode'))

    def test_rejected_module_or_bus_preserves_configuration_and_history(self):
        api = self.configured('keyence', 'KV Nano', 'KV-N14DT')
        self.checked(api.set_module(0, 0, 0, 'KV-NC16EX'))
        self.checked(api.set_module_tag(0, 0, 0, 'DI1'))
        before = copy.deepcopy((api.snapshot(), api.page(0)))
        operations = [
            lambda: api.set_module(0, 0, 1, 'NX-ID3317'),
            lambda: api.set_module(0, 0, 1, 'KV-NC1EP'),
            lambda: api.set_module(0, 0, 0, 'KV-NC16EX', 'x'),
            lambda: api.set_module_bus(0, 0, 0, 'x'),
        ]
        for operation in operations:
            self.assertIn('error', operation())
            self.assertEqual((api.snapshot(), api.page(0)), before)
        self.checked(api.undo())
        self.assertEqual([(row['model'], row['tag']) for row in self.modules(api)], [('KV-NC16EX', '')])
        self.checked(api.redo())
        self.assertEqual([(row['model'], row['tag']) for row in self.modules(api)], [('KV-NC16EX', 'DI1')])

    def test_wrong_manufacturer_open_preserves_unsaved_configuration(self):
        with tempfile.TemporaryDirectory() as folder:
            source = self.configured('keyence', 'KV Nano', 'KV-N24DT')
            path = Path(folder) / 'keyence.json'
            self.checked(source.save_as(str(path)))
            active = self.configured('omron', 'NX', 'NX502-1300')
            self.checked(active.set_module(0, 0, 0, 'NX-EIP201', 'x'))
            self.checked(active.set_module_tag(0, 0, 0, 'UNSAVED'))
            before = copy.deepcopy((active.snapshot(), active.page(0)))
            self.assertIn('error', active.open_configuration('omron', str(path)))
            self.assertEqual((active.snapshot(), active.page(0)), before)

    def test_replacing_module_clears_the_previous_models_firmware(self):
        api = self.configured('keyence', 'KV-8000', 'KV-8000')
        self.checked(api.set_module(0, 0, 0, 'KV-B16XC', 'legacy'))
        current = self.checked(api.page(0))
        extra = dict(json.loads(current['extra'] or '{}'), module_versions=['1.0'])
        self.checked(api.update_page(0, current['values'], json.dumps(extra)))
        self.checked(api.set_module(0, 0, 0, 'KV-B16TC', 'legacy'))
        self.assertEqual(json.loads(self.checked(api.page(0))['extra'])['module_versions'], [''])
        self.checked(api.undo())
        self.assertEqual(json.loads(self.checked(api.page(0))['extra'])['module_versions'], ['1.0'])

    def test_serial_mode_survives_editing_save_and_detail_generation(self):
        api = self.configured('keyence', 'KV Nano', 'KV-NC32T')
        two = 'RS-485（2線式）'
        model = 'KV-NC20L'
        self.checked(api.set_module(0, 0, 0, model, '', two))
        self.checked(api.create_all_unit_pages(0))
        detail = api.unit_pages(0, 0, 0)['existing'][0]['index']
        self.assertEqual(api.page(detail)['values']['communication_mode'], two)
        self.assertIn('error', api.set_module_mode(0, 0, 0, 'RS-422（2線式）'))
        self.checked(api.set_module_mode(0, 0, 0, 'RS-232C'))
        self.assertEqual(api.page(detail)['values']['communication_mode'], 'RS-232C')
        self.checked(api.undo())
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'config.json'
            target = Path(folder) / 'config.qet'
            self.checked(api.save_as(str(source)))
            loaded = Api()
            self.checked(loaded.open_configuration('keyence', str(source)))
            self.assertEqual(self.modules(loaded)[0]['communication_mode'], two)
            self.checked(loaded.generate(str(target)))
            diagrams = ET.parse(target).getroot().findall('diagram')
            xml = ET.tostring(diagrams[-1], encoding='unicode')
            self.assertIn('Port2 ' + two, xml)
            self.assertIn('S/R(+)', xml)
            self.assertNotIn('Port2 RS-232C', xml)

            # 旧形式は詳細だけに通信方式を持つ。読込・一括作成で上書きしない。
            data = json.loads(source.read_text(encoding='utf-8'))
            del data['pages'][0]['module_modes']
            source.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
            self.checked(loaded.open_configuration('keyence', str(source)))
            self.checked(loaded.create_all_unit_pages(0))
            self.assertEqual(self.modules(loaded)[0]['communication_mode'], '')
            self.assertEqual(loaded.page(detail)['values']['communication_mode'], two)
            self.assertFalse(loaded.detail_differences()['rows'])

    def test_serial_mode_change_is_local_to_its_cpu_even_with_reused_tag(self):
        api = self.configured('keyence', 'KV Nano', 'KV-NC32T')
        cpu = api.page(0)['values']
        for index in (0, 3):
            if index:
                self.checked(api.add_page())
                self.checked(api.update_page(index, cpu, '', 'model'))
            self.checked(api.set_module(index, 0, 0, 'KV-NC20L', '', 'RS-232C'))
            self.checked(api.set_module_tag(index, 0, 0, 'COM1'))
            self.checked(api.create_all_unit_pages(index))
        self.checked(api.set_module_mode(0, 0, 0, 'RS-485（2線式）'))
        self.assertEqual(api.page(2)['values']['communication_mode'], 'RS-485（2線式）')
        self.assertEqual(api.page(5)['values']['communication_mode'], 'RS-232C')


if __name__ == '__main__':
    unittest.main()
