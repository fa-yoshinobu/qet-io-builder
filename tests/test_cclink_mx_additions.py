import contextlib
import csv
import io
import json
from pathlib import Path
import tempfile
import unittest
from xml.etree import ElementTree as ET

import gen_io_page as gen
import gui_core as core
from renderers.terminal_pages import terminal_rows
from webgui.api import Api

ROOT = Path(__file__).resolve().parents[1]
CC = ROOT / 'parts/plc/mitsubishi/cclink'


class CclinkMxAdditionsTest(unittest.TestCase):
    def test_analog_terminal_anchors_and_nc_from_manuals(self):
        self.assertEqual(len(list((CC / 'analog_io').glob('*.json'))), 10)
        spec = gen.REMOTE_ANALOG['AJ65BT-64DAV']
        self.assertEqual(spec['pins_by_channel'], [['13', '14'], ['17', '18'], ['21', '22'], ['25', '26']])
        self.assertEqual({r['pin'] for r in spec['unused_pins']}, {'12', '15', '16', '19', '20', '23', '24', '27'})
        self.assertEqual(spec['network_terminals'][-1], ['7', '24G'])
        for model in ('AJ65SBT-64AD', 'AJ65SBT2B-64AD'):
            spec = gen.REMOTE_ANALOG[model]
            self.assertTrue(all(pin == '' for channel in spec['pins_by_channel'] for pin in channel))
            self.assertEqual(spec['required_jumpers'][0]['terminals'], ['V+', 'I+'])
        spec = gen.REMOTE_ANALOG['AJ65VBTCU-68DAVN']
        self.assertEqual(spec['pins_by_channel'], [['1', '3']] * 8)
        self.assertEqual({p['pin'] for p in spec['unused_pins']}, {'2', '4'})
        self.assertEqual(spec['network_connectors'][0]['pins'][3], ['4', 'NC'])

    def test_counter_variants_preserve_physical_terminals(self):
        for model in ('AJ65BT-D62', 'AJ65BT-D62D', 'AJ65BT-D62D-S1'):
            rows = gen.REMOTE_PULSE[model]['signal_terminals']
            self.assertEqual(sorted(int(r['pin']) for r in rows), list(range(8, 28)))
        regular = {r['pin']: r['signal'] for r in gen.REMOTE_PULSE['AJ65BT-D62D']['signal_terminals']}
        special = {r['pin']: r['signal'] for r in gen.REMOTE_PULSE['AJ65BT-D62D-S1']['signal_terminals']}
        self.assertEqual(regular['23'], 'EQU2')
        self.assertEqual(special['23'], '/F.START')
        self.assertEqual(special['24'], 'EQU1')
        rows = gen.REMOTE_PULSE['AJ65BT-D75P2-S3']['signal_terminals']
        self.assertEqual(gen.REMOTE_PULSE['AJ65BT-D75P2-S3']['network_terminals'],
                         [['', signal] for signal in ('DA', 'DB', 'DG', 'SLD', '24V', '24G', 'FG')])
        self.assertEqual(len(rows), 72)
        self.assertEqual({r['pin'] for r in rows}, {f'AX{axis}:{pin}' for axis in (1, 2) for pin in range(1, 37)})

    def test_mxr_reserved_slots_ports_and_compatible_catalog(self):
        api = Api()
        api._data['pages'] = [dict(kind='iqrbody', model='MXR300-16', base_model='R35B', power_model='R61P', modules=['RX40C7'])]
        page = api.page(0)
        self.assertNotIn('error', page)
        self.assertEqual(page['values']['series'], 'mx_r')
        slots, errors, _ = gen.slot_assignments(api._data['pages'][0])
        self.assertFalse(errors)
        self.assertEqual([s['start'] for s in slots[0][:3]], [0, 32, 64])
        self.assertEqual(gen.IQR_CPU['MXR300-16']['network_part']['ports_by_slot'][1], [])
        models = core.part_catalog('modules', 'iqrbody')['mitsubishi']['mx_r']
        self.assertIn('RX40C7', models)
        self.assertNotIn('RD81OPC96', models)
        self.assertIn('R61P', core.part_catalog('power_model', 'iqrbody')['mitsubishi']['mx_r'])
        self.assertNotIn('batteryless', page['visible'])
        self.assertNotIn('搭載不可', page['options']['battery'])
        self.assertTrue(gen.cpu_option_error(dict(model='MXR500-256', base_model='R35B', power_model='R62P'), gen.IQR_CPU['MXR500-256']))

    def test_mxf_ports_repeated_commons_and_hex_addresses(self):
        self.assertEqual(len(gen.MX_CPU), 6)
        self.assertEqual(gen.MX_CPU['MXF100-8-N32-EC']['ports'][0]['name'], 'P1 EtherCAT')
        rows = terminal_rows({'x_start': '20', 'y_start': '40'}, gen.MX_IO['MXF100-H32P'])
        self.assertIn('X20', [r['signal'] for r in rows])
        self.assertIn('Y40', [r['signal'] for r in rows])
        self.assertEqual(sum(r['signal'] == 'S/S' for r in rows), 2)
        self.assertEqual(sum(r['signal'] == '+V0' for r in rows), 2)
        relay = gen.MX_IO['MXF100-Y16R']['signal_terminals']
        self.assertEqual(len(relay), 36)
        self.assertEqual(sum(r['signal'] == 'Y00' for r in relay), 2)
        self.assertEqual(sum(r['signal'] == 'COM1' for r in relay), 2)

    def test_csv_roundtrip_and_invalid_rows(self):
        api = Api()
        api._data['pages'] = [dict(kind='mxio', model='MXF100-8-N32')]
        with tempfile.TemporaryDirectory() as folder:
            api.save_as(str(Path(folder) / 'project.json'))
            result = api.make_page_csv(0)
            self.assertNotIn('error', result)
            path = Path(folder) / api._data['pages'][0]['csv']
            self.assertTrue(path.read_bytes().startswith(b'\xef\xbb\xbf'))
            with path.open(encoding='utf-8-sig', newline='') as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 36)
            rows[0]['用途'] = '起動スイッチ'
            output = terminal_rows({}, gen.MX_IO['MXF100-8-N32'], rows)
            self.assertEqual(output[0]['description'], '起動スイッチ')
            for bad in ([{'No.': '0'}], [{'No.': '1'}, {'No.': '1'}], [{'No.': 'bad'}]):
                with self.assertRaises(ValueError):
                    terminal_rows({}, gen.MX_IO['MXF100-8-N32'], bad)

    def test_every_new_model_is_selectable_and_generates_through_cli(self):
        pages = []
        folders = ['cclink/analog_io', 'cclink/counter_pulse', 'mx_r/cpu', 'mx_f/cpu', 'mx_f/digital_io']
        for folder in folders:
            for path in (ROOT / 'parts/plc/mitsubishi' / folder).glob('*.json'):
                item = json.loads(path.read_text(encoding='utf-8'))
                model, category = item['model'], item['category']
                kinds = {'remote_analog': ('remotebody', 'remoteanalog'), 'remote_pulse': ('remotebody', 'remotepulse'),
                         'iqr_cpu': ('iqrbody',), 'mx_cpu': ('mxbody', 'mxio'), 'mx_io': ('mxio',)}[category]
                for kind in kinds:
                    with self.subTest(model=model, kind=kind):
                        catalog = core.part_catalog('model', kind)
                        series = folder.split('/')[0]
                        self.assertIn(model, catalog['mitsubishi'][series])
                        page = dict(kind=kind, model=model, tag='UNIT1')
                        if kind == 'iqrbody':
                            page.update(base_model='R35B', power_model='R61P', modules=['RX40C7'])
                        pages.append(page)
        pages += [dict(kind='qcomm', right_model='QJ71FL71-T-F01'), dict(kind='iqrcomm', right_model='ER-1FL2-T')]
        config = json.loads((ROOT / 'tests/fixtures/project.json').read_text(encoding='utf-8'))
        config.update(front_pages=False, pages=pages)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'project.json'; target = Path(folder) / 'test.qet'
            path.write_text(json.dumps(config, ensure_ascii=False), encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()):
                gen.main(str(path), str(target))
            diagrams = ET.parse(target).getroot().findall('./diagram')
            self.assertEqual(len(diagrams), len(pages) + 1)  # D75 is two terminal pages.
            self.assertTrue(target.with_name('test_iolist.csv').exists())
            for diagram in diagrams:
                for text in diagram.findall('./inputs/input'):
                    self.assertLessEqual(float(text.get('y')), 800)

    def test_flnet_units_have_one_rj45_and_no_dip_by_default(self):
        for kind, model in [('qcomm', 'QJ71FL71-T-F01'), ('iqrcomm', 'ER-1FL2-T')]:
            api = Api(); api._data['pages'] = [dict(kind=kind, right_model=model)]
            page = api.page(0)
            self.assertIn('right_ip', page['visible'])
            self.assertIn('right_station', page['visible'])
            self.assertNotIn('right_dip', page['visible'])
            project, _ = gen.build_project(gen.project_config({'front_pages': False}),
                                           [(api._data['pages'][0], None)])
            drawings = project.findall('diagram')
            self.assertEqual(len(drawings), 1)
            self.assertEqual(sum(e.get('type', '').endswith('/module_rj45.elmt')
                                 for e in drawings[0].findall('./elements/element')), 1)


if __name__ == '__main__':
    unittest.main()
