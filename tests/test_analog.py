import contextlib
import csv
import io
import json
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

import gen_io_page as gen


class AnalogGenerationTest(unittest.TestCase):
    def test_fx5_headers_join_the_first_channel_boxes(self):
        for model,spec in gen.FX5_ANALOG_SPECS.items():
            with self.subTest(model=model):
                page=gen.build_fx_analog_page({'kind':'fx5analog','model':model,'unit_no':'2','tag':'AD1'}, {}, gen.build_symbols(), [])
                right_only=model!='FX5-8AD'
                sides=1 if right_only else 2
                offset=gen.HALF_W if right_only else 0
                for side in range(sides):
                    rectangles=[s for s in page.shapes if s.get('type')=='Rectangle' and float(s.get('x1'))==275+offset+side*gen.HALF_W]
                    self.assertTrue(any(s.get('y1')=='34' and s.get('y2')=='52' for s in rectangles))
                    self.assertTrue(any(s.get('y1')=='52' and float(s.get('y2'))>52 for s in rectangles))
                texts=[t.get('text','') for t in page.texts]
                self.assertEqual(texts.count('ユニットNo. 2'),sides)
                self.assertEqual(texts.count('AD1'),sides)
                self.assertEqual(texts.count(model),sides)
                self.assertNotIn(model+' アナログ端子',texts)
                if right_only:
                    self.assertTrue(all(x>=640 for _,_,x,_ in page.placed))
                    self.assertTrue(all(float(t.get('x'))>=640 for t in page.texts))
                self.assertLess(max(float(s.get('y2')) for s in page.shapes if s.get('type')=='Rectangle'),782)

    def test_fx5_adapter_input_and_output_terminal_functions(self):
        spec = gen.FX5_ANALOG_SPECS['FX5-4A-ADP']
        page = gen.build_fx_analog_page({'kind':'fx5analog', 'model':'FX5-4A-ADP'}, {}, gen.build_symbols(), [])
        pins = [e for kind, e, _, _ in page.placed if kind == 'module_pin']
        def info(e, name):
            return next((v.text for v in e.findall('./elementInformations/elementInformation') if v.get('name') == name), None)
        self.assertEqual([(info(e, 'label'), info(e, 'comment')) for e in pins[:3]],
                         [('V1+', '電圧/電流入力'), ('I1+', '電流入力短絡用'), ('COM1', 'コモン')])
        self.assertEqual([(info(e, 'label'), info(e, 'comment')) for e in pins[6:9]],
                         [('V3+', '電圧出力'), ('I3+', '電流出力'), ('COM3', 'コモン')])
        self.assertEqual([info(e, 'label') for e in pins[-3:]], ['+', '-', '⏚'])

    def test_fx5_analog_lanes_and_supply_connections(self):
        page = gen.build_fx_analog_page({'kind':'fx5analog', 'model':'FX5-4A-ADP'}, {}, gen.build_symbols(), [])
        by_id = {element.get('uuid'): (kind, element, x, y) for kind, element, x, y in page.placed}
        self.assertTrue({('junction', 665), ('junction', 692)} <= {(kind, x) for kind, _, x, _ in page.placed})
        for conductor in page.conductors:
            a = by_id[conductor.get('element1')]; b = by_id[conductor.get('element2')]
            if b[0] != 'module_pin':
                continue
            label = next((v.text for v in b[1].findall('./elementInformations/elementInformation') if v.get('name') == 'label'), '')
            if label in ('+', '-'):
                self.assertEqual((a[0], a[2]), ('junction', 665 if label == '+' else 692))

    def test_all_models_generate_expected_wires(self):
        base = json.loads((Path(__file__).parent / 'fixtures' / 'project.json').read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            for model, spec in gen.FX5_ANALOG_SPECS.items():
                with self.subTest(model=model):
                    base['pages'] = [{'kind': 'fx5analog', 'model': model}]
                    (p/'input.json').write_text(json.dumps(base, ensure_ascii=False), encoding='utf-8')
                    with contextlib.redirect_stdout(io.StringIO()):
                        gen.main(str(p/'input.json'), str(p/'result.qet'))
                    root = ET.parse(p/'result.qet').getroot()
                    # 端子はすべて部品として置き、線は電源レーン(P24/N24)につなぐ端子だけに引く
                    expected = sum(len(spec.get('terminals_by_direction', {}).get(ch, spec['terminals'])) for ch in spec['channels']) + len(spec['power']) + len(spec.get('auxiliary_terminals', []))
                    pins = [e for e in root.findall('.//diagram/elements/element') if e.get('type').endswith('/module_pin.elmt')]
                    self.assertEqual(len(pins), expected)
                    k = sum(terminal in ('+24V', '24V', '0V', '24G') for terminal in spec['power'])
                    self.assertEqual(len(root.findall('.//diagram/conductors/conductor')), 2 + 2 * k if k else 0)

    def test_method_pins_and_jumper_rule(self):
        self.assertEqual(gen.analog_method_pins(['V1+', 'I1+', 'COM1'], '入力', '電圧'), ('V1+', 'COM1', None, None))
        self.assertEqual(gen.analog_method_pins(['V1+', 'I1+', 'COM1'], '入力', '電流'), ('I1+', 'COM1', ('V1+', 'I1+'), None))
        self.assertEqual(gen.analog_method_pins(['V+', 'V-', 'I+', 'SLD'], '入力', '電流'), ('I+', 'V-', ('V+', 'I+'), 'SLD'))
        self.assertIsNone(gen.analog_method_pins(['V1+', 'COM1'], '入力', '電流'))
        self.assertFalse(gen.CURRENT_JUMPER['FX5-4AD'])
        self.assertTrue(gen.CURRENT_JUMPER['Q64AD'])

    def test_method_column_draws_device_and_jumper(self):
        base = json.loads((Path(__file__).parent / 'fixtures' / 'project.json').read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            counts = {}
            for model, method in (('FX5-4A-ADP', ''), ('FX5-4A-ADP', '電圧'), ('FX5-4A-ADP', '電流'), ('FX5-4AD', '電流')):
                (p/'ch.csv').write_text(f'CH,用途,方式,機器番号\n1,圧力,{method},PT1\n', encoding='utf-8-sig')
                base['pages'] = [{'kind': 'fx5analog', 'model': model, 'csv': 'ch.csv'}]
                (p/'input.json').write_text(json.dumps(base, ensure_ascii=False), encoding='utf-8')
                with contextlib.redirect_stdout(io.StringIO()):
                    gen.main(str(p/'input.json'), str(p/'result.qet'))
                root = ET.parse(p/'result.qet').getroot()
                devs = [e for e in root.findall('.//diagram/elements/element') if '/analog_dev_' in e.get('type')]
                counts[(model, method)] = (len(devs), len(root.findall('.//diagram/conductors/conductor')))
            n0 = counts[('FX5-4A-ADP', '')][1]
            self.assertEqual(counts[('FX5-4A-ADP', '')][0], 0)
            # 電圧: +・-・シールド(接地) の3本。電流: さらに V+ と I+ の短絡
            self.assertEqual(counts[('FX5-4A-ADP', '電圧')], (1, n0 + 3))
            self.assertEqual(counts[('FX5-4A-ADP', '電流')], (1, n0 + 4))
            self.assertEqual(counts[('FX5-4AD', '電流')][0], 1)

    def test_invalid_channel_is_rejected(self):
        base = json.loads((Path(__file__).parent / 'fixtures' / 'project.json').read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p/'channels.csv').write_text('CH,用途\n9,予備\n', encoding='utf-8-sig')
            base['pages'] = [{'kind': 'fx5analog', 'model': 'FX5-4AD', 'csv': 'channels.csv'}]
            (p/'input.json').write_text(json.dumps(base, ensure_ascii=False), encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
                gen.main(str(p/'input.json'), str(p/'result.qet'))
            self.assertFalse((p/'result.qet').exists())

    def test_iqr_analog_modules_and_configuration(self):
        base = json.loads((Path(__file__).parent / 'fixtures' / 'project.json').read_text(encoding='utf-8'))
        base['pages'] = [
            {'kind': 'iqrbody', 'model': 'R04CPU', 'power_model': 'R61P',
             'base_model': 'R35B', 'modules': ['R60AD4', 'R60DA4']},
            *[{'kind': 'iqranalog', 'model': model} for model in ('R60AD4', 'R60DA4')],
        ]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p/'input.json').write_text(json.dumps(base, ensure_ascii=False), encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()):
                gen.main(str(p/'input.json'), str(p/'result.qet'))
            diagrams = ET.parse(p/'result.qet').getroot().findall('.//diagram')
            self.assertEqual(len(diagrams), 3)
            for diagram, model in zip(diagrams[1:], ('R60AD4', 'R60DA4')):
                spec = gen.IQR_ANALOG[model]
                # iQ-R も Q と同じ表(端子│信号│用途)。端子は plc_in、線は P24/N24 レーンへの電源だけ
                pins = [e for e in diagram.findall('./elements/element') if e.get('type').endswith(('/plc_in.elmt', '/plc_in_readonly.elmt'))]
                self.assertEqual(len(pins), len(spec['channels']) * len(spec['terminals']) + len(spec['power']) + len(spec.get('auxiliary_terminals', [])) + len(spec.get('unconnected_ports', [])))
                lane = {e.get('uuid') for e in diagram.findall('./elements/element') if e.get('type').endswith(('/junction.elmt', '/node.elmt'))}
                self.assertTrue(all({c.get('element1'), c.get('element2')} & lane for c in diagram.findall('./conductors/conductor')))

    def test_all_iqr_analog_models_generate(self):
        base = json.loads((Path(__file__).parent / 'fixtures' / 'project.json').read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            for model, spec in gen.IQR_ANALOG.items():
                with self.subTest(model=model):
                    base['pages'] = [{'kind': 'iqranalog', 'model': model}]
                    (p/'input.json').write_text(json.dumps(base, ensure_ascii=False), encoding='utf-8')
                    with contextlib.redirect_stdout(io.StringIO()):
                        gen.main(str(p/'input.json'), str(p/'result.qet'))
                    root = ET.parse(p/'result.qet').getroot()
                    diagrams = root.findall('.//diagram')
                    pins = [e for d in diagrams for e in d.findall('./elements/element') if e.get('type').endswith(('/plc_in.elmt', '/plc_in_readonly.elmt'))]
                    # 電源・補助端子は各ページに出る
                    self.assertEqual(len(pins), len(spec['channels']) * len(spec['terminals']) + len(diagrams) * (len(spec['power']) + len(spec.get('auxiliary_terminals', [])) + len(spec.get('unconnected_ports', []))))
                    for d in diagrams:
                        lane = {e.get('uuid') for e in d.findall('./elements/element') if e.get('type').endswith(('/junction.elmt', '/node.elmt'))}
                        self.assertTrue(all({c.get('element1'), c.get('element2')} & lane for c in d.findall('./conductors/conductor')))

    def test_q_analog_and_mixed_series_rejection(self):
        base = json.loads((Path(__file__).parent / 'fixtures' / 'project.json').read_text(encoding='utf-8'))
        body = {'kind': 'qbody', 'model': 'Q03UDVCPU', 'power_model': 'Q61P',
                'base_model': 'Q35B', 'modules': ['QX41', 'QY41P', 'Q64AD', 'Q64DAN']}
        base['pages'] = [body, *[{'kind': 'qanalog', 'model': m} for m in ('Q64AD', 'Q64DAN')]]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            source, result = p/'input.json', p/'result.qet'
            source.write_text(json.dumps(base, ensure_ascii=False), encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()):
                gen.main(str(source), str(result))
            diagrams = ET.parse(result).getroot().findall('.//diagram')
            self.assertEqual(len(diagrams), 3)
            for diagram, model in zip(diagrams[1:], ('Q64AD', 'Q64DAN')):
                spec = gen.Q_ANALOG[model]
                pins = [e for e in diagram.findall('./elements/element') if e.get('type').endswith('/plc_in.elmt')]
                self.assertEqual(len(pins), len(spec['channels']) * len(spec['terminals']) + len(spec['power']) + len(spec.get('auxiliary_terminals', [])))
                k = sum(t in ('+24V', '24V', '0V', '24G') for t in spec['power'])
                self.assertEqual(len(diagram.findall('./conductors/conductor')), 2 + 2 * k if k else 0)
            body['modules'] = ['R60AD4']
            source.write_text(json.dumps(base, ensure_ascii=False), encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
                gen.main(str(source), str(result))

    def test_all_q_analog_models_generate(self):
        base = json.loads((Path(__file__).parent / 'fixtures' / 'project.json').read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            for model, spec in gen.Q_ANALOG.items():
                with self.subTest(model=model):
                    base['pages'] = [{'kind': 'qanalog', 'model': model}]
                    (p/'input.json').write_text(json.dumps(base, ensure_ascii=False), encoding='utf-8')
                    with contextlib.redirect_stdout(io.StringIO()):
                        gen.main(str(p/'input.json'), str(p/'result.qet'))
                    root = ET.parse(p/'result.qet').getroot()
                    expected = sum(len(spec.get('terminals_by_channel', [])[i] if spec.get('terminals_by_channel') else spec.get('terminals_by_direction', {}).get(ch, spec['terminals'])) for i, ch in enumerate(spec['channels'])) + len(spec['power']) + len(spec.get('auxiliary_terminals', []))
                    pins = [e for e in root.findall('.//diagram/elements/element') if e.get('type').endswith('/plc_in.elmt')]
                    self.assertEqual(len(pins), expected)
                    k = sum(t in ('+24V', '24V', '0V', '24G') for t in spec['power'])
                    self.assertEqual(len(root.findall('.//diagram/conductors/conductor')), (2 + 2 * k) * ((len(spec['channels']) + 7) // 8) if k else 0)

    def test_combined_module_uses_input_and_output_terminal_names(self):
        page = gen.build_fx_analog_page({'kind': 'qanalog', 'model': 'Q64AD2DA'}, {}, gen.build_symbols(), [])
        labels = []
        for key, element, _, _ in page.placed:
            if key != 'plc_in':
                continue
            values = {v.get('name'): v.text for v in element.findall('./elementInformations/elementInformation')}
            labels.append(values['label'])
        self.assertEqual(labels[:3], ['V+', 'V-/I-', 'I+'])
        self.assertEqual(labels[12:15], ['V+', 'COM', 'I+'])

if __name__ == '__main__':
    unittest.main()
