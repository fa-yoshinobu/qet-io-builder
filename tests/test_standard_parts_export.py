from tests.qet_support import requires_qet
import copy
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

import gen_io_page as g
import gui_core as gui
from renderers import standard


class StandardPartsExportTest(unittest.TestCase):
    @requires_qet
    def test_multipole_terminal_labels_keep_full_names_at_readable_size(self):
        devices = g.read_unit_definitions()['standard_device']
        for model in ('CP30FM-2P001', 'CP30-BA 3P 1-M 1A', 'TR65X3H-044', 'TH-T18KP 0.9A'):
            with self.subTest(model=model):
                spec = devices[model]
                part, template, labels = next(standard.bindings(spec))
                xml = standard.bind_definition(model, spec, part, template, labels)
                texts = {n.findtext('text'): n for n in xml.findall('./description/dynamic_text')
                         if n.get('text_from') == 'UserText'}
                for values in labels.values():
                    name = '/'.join(values)
                    self.assertIn(name, texts)
                    self.assertEqual(float(texts[name].get('font').split(',')[1]), 7)
                upper = [texts['/'.join(values)] for role, values in labels.items() if role.startswith('line')]
                lower = [texts['/'.join(values)] for role, values in labels.items() if role.startswith('load')]
                self.assertLess(float(upper[1].get('y')), float(upper[0].get('y')))
                self.assertGreater(float(lower[1].get('y')), float(lower[0].get('y')))

    @requires_qet
    def test_all_catalog_symbols_match_the_installed_collection(self):
        root = standard.collection_root()
        self.assertTrue({'coil', 'contact_no', 'contact_nc', 'contact_changeover', 'lamp'} <= set(standard.catalog()))
        for key, record in standard.catalog().items():
            with self.subTest(key=key):
                xml = ET.parse(root / record['path']).getroot()
                actual = {(float(t.get('x')), float(t.get('y'))) for t in xml.findall('./description/terminal')}
                self.assertEqual(actual, {tuple(p) for p in record['terminal_roles'].values()})
                self.assertEqual(xml.get('link_type'), record['link_type'])

    @requires_qet
    def test_each_model_and_auxiliary_choice_exports_with_standard_geometry(self):
        devices = g.read_unit_definitions()['standard_device']
        self.assertGreaterEqual(len(devices), 75)
        for model, spec in devices.items():
            if spec.get('component_style') in ('terminal_box', 'ethernet_switch', 'swallow_transformer'):
                continue  # 箱型電子機器は専用の端子数検証で確認する。
            choices = [o['id'] for o in spec.get('auxiliary_options', [])] or [None]
            for choice, configuration in ((c, o) for c in choices for o in ([v['id'] for v in spec.get('configuration_options', [])] or [None])):
                with self.subTest(model=model, auxiliary=choice), tempfile.TemporaryDirectory() as folder:
                    paths = standard.export_model(model, spec, folder, choice, configuration=configuration)
                    self.assertTrue(paths)
                    for path, (_, template, labels) in zip(paths, standard.bindings(standard.configured_spec(spec, configuration), choice)):
                        xml = ET.parse(path).getroot()
                        record = standard.catalog()[template]
                        original = ET.parse(standard.collection_root() / record['path']).getroot()
                        geometry = lambda node: [ET.tostring(e) for e in node.find('description') if e.tag not in ('text', 'dynamic_text', 'terminal')]
                        # 空白インデントを除き、標準記号の線・形状が変わっていないことを確認。
                        def normalized(node):
                            node = copy.deepcopy(node)
                            for child in node.iter():
                                child.tail = None
                            return geometry(node)
                        self.assertEqual(normalized(xml), normalized(original))
                        self.assertEqual(len(xml.findall('./description/terminal')), len(labels))
                        self.assertIn('QElectroTech', xml.findtext('informations'))
                        self.assertEqual(xml.findtext("./elementInformations/elementInformation[@name='manufacturer_reference']"), model)

    @requires_qet
    def test_exported_master_information_leaves_room_for_automatic_contact_references(self):
        for model in ('MY4ZN-CBG', 'PLC-RSC-24DC/21', 'H3Y-2', 'HW1B-M110G', 'TR65X3H-044'):
            with self.subTest(model=model), tempfile.TemporaryDirectory() as folder:
                paths = standard.export_model(model, g.STANDARD_DEVICES[model], folder)
                for path in paths:
                    definition = ET.parse(path).getroot()
                    fields = {n.findtext('info_name'): n for n in definition.findall('./description/dynamic_text')}
                    label, model_text = fields['label'], fields['manufacturer_reference']
                    self.assertEqual(label.get('x'), model_text.get('x'))
                    self.assertAlmostEqual(float(model_text.get('y')) - float(label.get('y')), 17)
                    last = model_text
                    if 'comment' in fields:
                        last = fields['comment']
                        self.assertEqual(label.get('x'), last.get('x'))
                        self.assertAlmostEqual(float(last.get('y')) - float(model_text.get('y')), 15)
                    if definition.get('link_type') == 'master':
                        self.assertGreaterEqual(float(label.get('text_height')), float(last.get('y')) - float(label.get('y')) + 17)
                        self.assertEqual(label.get('Valignment'), 'AlignTop')
                        self.assertGreater(float(last.get('z')), float(label.get('z')))
                    for field in ('label', 'manufacturer_reference'):
                        self.assertEqual(fields[field].get('text_from'), 'ElementInfo')

    @requires_qet
    def test_physical_relay_pins_replace_generic_coil_numbers(self):
        spec = g.STANDARD_DEVICES['MY4N']
        xml = standard.bind_definition('MY4N', spec, 'coil', 'coil', {'a1': ['13'], 'a2': ['14']})
        self.assertEqual([t.get('name') for t in xml.findall('./description/terminal')], ['13', '14'])
        user_text = [t.findtext('text') for t in xml.findall('./description/dynamic_text') if t.get('text_from') == 'UserText']
        self.assertEqual(user_text, ['13', '14'])
        ly = list(standard.bindings(g.STANDARD_DEVICES['LY1']))
        self.assertEqual(ly[1][2]['common'], ['5', '6'])

    def test_invalid_choice_and_missing_library_do_not_write_files(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'new'
            with self.assertRaisesRegex(ValueError, '補助接点'):
                standard.export_model('SC09XG', g.STANDARD_DEVICES['SC09XG'], target)
            self.assertFalse(target.exists())
            with self.assertRaises(ValueError):
                standard.export_model('MY4N', g.STANDARD_DEVICES['MY4N'], target, elements=Path(folder) / 'missing')
            self.assertFalse(target.exists())

    @requires_qet
    def test_auxiliary_variants_have_distinct_ids_and_dc_polarity_is_visible(self):
        spec = g.STANDARD_DEVICES['SC09XG']
        variants = []
        for choice in ('1a', '1b'):
            part, template, labels = list(standard.bindings(spec, choice))[-1]
            xml = standard.bind_definition('SC09XG', spec, part, template, labels)
            variants.append(xml.find('uuid').get('uuid'))
        self.assertNotEqual(*variants)
        part, template, labels = next(standard.bindings(spec, '1a'))
        xml = standard.bind_definition('SC09XG', spec, part, template, labels)
        texts = [n.findtext('text') for n in xml.findall('./description/dynamic_text')]
        self.assertIn('A1 (+)', texts)
        self.assertIn('A2 (-)', texts)

    def test_gui_catalog_and_io_reference_use_model_data(self):
        picker = gui.part_catalog('standard_model', '')
        self.assertTrue({'omron', 'fuji'} <= set(picker))
        self.assertIn('MY4N', picker['omron']['my'])
        self.assertIn('SC09XG', picker['fuji']['sc_next'])
        self.assertEqual(g.DEFAULT_RELAY_TYPES['MY2N']['contacts'][0]['common'], ['9'])
        rows = {'out': [{'機器番号': 'K1', '負荷': 'RY', '形式': 'MY4N'}], 'in': [{'機器番号': 'K1'}]}
        devices = g.xref_devices([({'kind': 'fx5u'}, rows)], {})
        g.xref_reset(devices)
        page = g.Page(g.build_symbols())
        g.register_coil(page, 'K1', 1, 500, 100, 400)
        g.register_contact(page, 'K1', 'a', 1, 150, 100)
        self.assertFalse(g.write_references(lambda _: 1))
        texts = [t.get('text') for t in page.texts]
        for pin in ('9', '5', '13', '14'):
            self.assertIn(pin, texts)
        g.xref_reset([])

    @requires_qet
    def test_generic_binding_preserves_switch_positions_and_sets_breaker_rating(self):
        spec = {'manufacturer': 'テスト', 'source': 'テスト用定義',
                'symbol_bindings': [{'name': 'switch', 'symbol': 'selector_2position',
                                     'terminals': {'first': ['13'], 'second': ['14']}}]}
        part, template, labels = next(standard.bindings(spec))
        xml = standard.bind_definition('TEST', spec, part, template, labels)
        self.assertEqual({t.get('text') for t in xml.findall('./description/text')}, {'0', '1'})
        self.assertEqual({t.get('name') for t in xml.findall('./description/terminal')}, {'13', '14'})
        spec['standard_text_overrides'] = {'breaker_2p': {'Calibre __A': '10A'}}
        xml = standard.bind_definition('TEST', spec, 'breaker', 'breaker_2p',
                                      {'line1': ['1'], 'load1': ['2'], 'line2': ['3'], 'load2': ['4']})
        texts = [t.findtext('text') for t in xml.findall('./description/dynamic_text')]
        self.assertIn('10A', texts)
        self.assertNotIn('Calibre __A', texts)

    @requires_qet
    def test_sensor_modes_are_required_and_export_distinct_contact_states(self):
        model = 'E3Z-D61 2M'
        spec = g.STANDARD_DEVICES[model]
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'parts'
            for choice in (None, 'invalid'):
                with self.assertRaisesRegex(ValueError, '動作構成'):
                    standard.export_model(model, spec, target, configuration=choice)
                self.assertFalse(target.exists())
            variants = []
            for choice, template in [('light_on', 'photoelectric_sensor_no'), ('dark_on', 'photoelectric_sensor_nc')]:
                paths = standard.export_model(model, spec, target, configuration=choice)
                xml = ET.parse(paths[0]).getroot()
                variants.append(xml.find('uuid').get('uuid'))
                self.assertIn(standard.catalog()[template]['path'], xml.findtext('informations'))
                self.assertEqual({t.get('name') for t in xml.findall('./description/terminal')}, {'茶 +V', '青 0V', '黒 OUT'})
                self.assertIn(choice, paths[0].parts)
            self.assertNotEqual(*variants)
            sio = g.STANDARD_DEVICES['E2E-X2B1D12 2M']
            with self.assertRaises(ValueError):
                standard.export_model('E2E-X2B1D12 2M', sio, target)
            self.assertTrue(standard.export_model('E2E-X2B1D12 2M', sio, target, configuration='sio_no'))

    @requires_qet
    def test_field_symbols_keep_function_marks_and_separate_long_wire_text(self):
        for model, marks in [('SF-PR(200V-4P-0.75KW)', {'M', '3 ~'}), ('IS10-01', {'P'})]:
            spec = g.STANDARD_DEVICES[model]
            part, template, labels = next(standard.bindings(spec))
            xml = standard.bind_definition(model, spec, part, template, labels)
            texts = {n.get('text') for n in xml.findall('./description/text')}
            texts.update(n.findtext('text') for n in xml.findall('./description/dynamic_text'))
            self.assertTrue(marks <= texts)
        spec = g.STANDARD_DEVICES['FQ-6']
        part, template, labels = next(standard.bindings(spec))
        xml = standard.bind_definition('FQ-6', spec, part, template, labels)
        nodes = xml.findall('./description/dynamic_text')
        model_node = next(n for n in nodes if n.findtext('info_name') == 'manufacturer_reference')
        self.assertGreater(float(model_node.get('x')), 80)
        self.assertFalse({'3', '4'} & {n.get('text') for n in xml.findall('./description/text')})

    def test_field_families_are_available_in_gui_picker(self):
        picker = gui.part_catalog('standard_model', '')
        for maker, series in [('omron', 'wl'), ('omron', 'e2e_next'), ('omron', 'e3z'), ('omron', 'm2bj'), ('smc', 'is10'), ('smc', '10_sy'), ('nohken', 'fq'), ('mitsubishi', 'sf_pr')]:
            self.assertTrue(picker[maker][series])
            self.assertIn(maker, gui.MAKER_NAMES)
            self.assertIn(series, gui.SERIES_NAMES)

    @requires_qet
    def test_breaker_pole_counts_and_example_rating_are_not_reused(self):
        spec = {'manufacturer': 'テスト', 'source': '検証用', 'display_ratings': '1A'}
        for poles in (1, 2, 3):
            labels = {f'{side}{n}': [f'{side} {n}'] for n in range(1, poles + 1) for side in ('line', 'load')}
            spec['standard_text_overrides'] = {f'breaker_{poles}p': {'Calibre __A': '1A'}}
            xml = standard.bind_definition('TEST', spec, 'main', f'breaker_{poles}p', labels)
            self.assertEqual(len(xml.findall('./description/terminal')), poles * 2)
            self.assertEqual({n.get('name') for n in xml.findall('./description/terminal')}, {v[0] for v in labels.values()})
            texts = {n.findtext('text') for n in xml.findall('./description/dynamic_text')}
            self.assertFalse({'C, 16A', 'Calibre __A'} & texts)

    @requires_qet
    def test_idec_and_mitsubishi_picker_and_fixed_coil_voltage(self):
        picker = gui.part_catalog('standard_model', '')
        for maker, series in [('idec', 'hw'), ('idec', 'rj'), ('idec', 'ru'), ('idec', 'sj'), ('mitsubishi', 'ms_t'), ('mitsubishi', 'th_t'), ('mitsubishi', 'nf'), ('mitsubishi', 'cp30_ba')]:
            self.assertTrue(picker[maker][series])
            self.assertIn(maker, gui.MAKER_NAMES)
            self.assertIn(series, gui.SERIES_NAMES)
        spec = g.STANDARD_DEVICES['RJ1S-CL-D24']
        part, template, labels = next(standard.bindings(spec))
        xml = standard.bind_definition('RJ1S-CL-D24', spec, part, template, labels)
        self.assertIn('コイル電圧は機種定義の固定定格', xml.findtext('informations'))
        self.assertNotIn('コイル電圧・ソケットは別途選択', xml.findtext('informations'))


if __name__ == '__main__':
    unittest.main()
