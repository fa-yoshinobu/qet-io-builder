import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET
import gen_io_page as gen


class BodyStatusTest(unittest.TestCase):
    def run_body(self, battery, model='FX5U-32MR/ES', **options):
        config = json.loads((Path(__file__).parent / 'fixtures' / 'project.json').read_text(encoding='utf-8'))
        page = {'kind':'fx5body','model':model}
        page.update(options)
        if battery is not None: page['battery'] = battery
        config['pages'] = [page]
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        p = Path(folder.name)
        (p/'config.json').write_text(json.dumps(config, ensure_ascii=False), encoding='utf-8')
        with contextlib.redirect_stdout(io.StringIO()):
            gen.main(str(p/'config.json'), str(p/'out.qet'))
        return ET.parse(p/'out.qet').getroot()

    def test_selected_battery_and_usb_are_recorded(self):
        for status in ('装着', '非装着', None):
            with self.subTest(status=status):
                root = self.run_body(status)
                infos = [x.text for x in root.findall('.//diagram/elements/element/elementInformations/elementInformation')]
                self.assertIn('バッテリ: '+(status or '要確認'), infos)
                self.assertIn('USBポート: なし', infos)

    def test_battery_choices_mark_only_actual_status(self):
        for status, first, second in [('装着', '■', '□'), ('非装着', '□', '■'), (None, '□', '□')]:
            root = self.run_body(status)
            info = [v.text for v in root.findall('.//diagram/elements/element/elementInformations/elementInformation')]
            self.assertIn(first + ' 有 (FX3U-32BL)', info)
            self.assertIn(second + ' 無', info)
            self.assertIn('■ 無', info)
        root = self.run_body(None, 'FX5S-30MR/ES')
        info = [v.text for v in root.findall('.//diagram/elements/element/elementInformations/elementInformation')]
        self.assertIn('■ 装着不可', info)
        self.assertIn('■ 有 (Mini-B)', info)

    def test_battery_impossible_is_rejected_for_fx5u(self):
        with self.assertRaises(SystemExit): self.run_body('搭載不可')

    def test_sd_card_selection_and_model(self):
        for state, first, second in [('有', '■', '□'), ('無', '□', '■'), ('要確認', '□', '□')]:
            root = self.run_body(None, sd_card=state, sd_card_model='NZ1MEM-4GBSD')
            info = [v.text for v in root.findall('.//diagram/elements/element/elementInformations/elementInformation')]
            self.assertIn(first + ' 有 (NZ1MEM-4GBSD)', info)
            self.assertIn(second + ' 無', info)
        with self.assertRaises(SystemExit): self.run_body(None, sd_card='不正')

    def test_fx5s_sd_card_requires_sdcd_board(self):
        for board in ('', 'なし', 'FX5-3A-BD'):
            root = self.run_body(None, 'FX5S-30MR/ES', board_model=board)
            info = [v.text for v in root.findall('.//diagram/elements/element/elementInformations/elementInformation')]
            self.assertNotIn('SD CARD', info)
            with self.assertRaises(SystemExit):
                self.run_body(None, 'FX5S-30MR/ES', board_model=board, sd_card='有')
        root = self.run_body(None, 'FX5S-30MR/ES', board_model='FX5-SDCD', sd_card='有', sd_card_model='NZ1MEM-4GBSD')
        info = [v.text for v in root.findall('.//diagram/elements/element/elementInformations/elementInformation')]
        self.assertIn('SD CARD', info)
        self.assertIn('■ 有 (NZ1MEM-4GBSD)', info)
        self.assertIn('FX5-SDCD', info)
        texts = {v.findtext('info_name'): (int(v.get('x')), int(v.get('y'))) for v in root.findall('.//diagram/elements/element/dynamic_texts/dynamic_elmt_text')}
        self.assertEqual(texts['auxiliary6'], (183, 125))
        self.assertEqual(texts['auxiliary7'], (227, 125))
        self.assertEqual(texts['auxiliary8'], (227, 144))

    def test_ac_and_dc_use_correct_power_and_service_terminals(self):
        for model, power, has_service in (
            ('FX5U-32MR/ES', {'L', 'N', '⏚'}, True),
            ('FX5U-32MT/DS', {'+', '-', '⏚'}, False),
        ):
            with self.subTest(model=model):
                root = self.run_body('非装着', model)
                used = root.find('.//diagram/elements/element')
                self.assertIn('fx5_body_', used.get('type'))
                sym = gen.fx5_body_symbol('test', has_service, True, True, has_service)
                self.assertTrue(power.issubset(sym.terminals))
                self.assertEqual('24V' in sym.terminals, has_service)

    def test_body_layout_is_shared_and_all_connections_are_left(self):
        empty = gen.fx5_body_symbol('minimal', False, False, False, False)
        full = gen.fx5_body_symbol('full', True, True, True, True)
        self.assertEqual((empty.width, empty.height), (full.width, full.height))
        # コネクタの絵(角丸・黒塗りの四角)は除いて、枠の四角だけを比べる
        frame = lambda kind, attrs: kind == 'rect' and not attrs.get('rx') and 'filling:black' not in attrs['style']
        empty_rects = [attrs for kind, attrs in empty.parts if frame(kind, attrs)]
        full_rects = [attrs for kind, attrs in full.parts if frame(kind, attrs)]
        self.assertTrue(all(rect in full_rects for rect in empty_rects))
        self.assertEqual(len(full_rects), 1)
        self.assertEqual(len(empty_rects), 1)
        self.assertTrue(any(kind == 'line' and 'line-weight:thin' in attrs['style'] for kind, attrs in full.parts))
        for name in ('+', '-', '⏚', 'RJ-45'):
            ac_name = {'+':'L', '-':'N'}.get(name, name)
            self.assertEqual(empty.terminals[name][2:], full.terminals[ac_name][2:])
        self.assertTrue(all(data[1] == 'w' for data in full.terminals.values()))
        self.assertEqual(sum(kind == 'circle' for kind, _ in full.parts), len(full.terminals) - 1)
        self.assertTrue({'SG', 'SDB', 'SDA', 'RDB', 'RDA', 'RJ-45'}.issubset(full.terminals))
        self.assertEqual(sorted(('RDA', 'RDB', 'SDA', 'SDB', 'SG'), key=lambda name: full.terminals[name][3]), ['RDA', 'RDB', 'SDA', 'SDB', 'SG'])
        self.assertFalse({'1 TXD+', '2 TXD-', '3 RXD+', '6 RXD-'} & full.terminals.keys())
        self.assertEqual(full.width, 350)
        for model in ('FX5S-30MR/DS', 'FX5U-32MR/ES'):
            root = self.run_body(None, model)
            diagram = root.find('.//diagram')
            unit = gen.FX5U_SPECS[model]
            symbol = gen.fx5_body_symbol('test', gen.model_power(model) == 'AC', unit['analog'], unit['rs485'], unit['service'])
            # 給電先がないレーン・行き先の決まらない線を描かず、実端子は保持する
            self.assertEqual(len(diagram.findall('./conductors/conductor')), 0)
            self.assertEqual(len(next(e for e in diagram.iter('element') if 'fx5_body_' in (e.get('type') or '')).findall('./terminals/terminal')), len(symbol.terminals))

    def test_fx5s_battery_unavailable_and_usb_present(self):
        root = self.run_body(None, 'FX5S-30MR/ES')
        infos = [x.text for x in root.findall('.//diagram/elements/element/elementInformations/elementInformation')]
        self.assertIn('バッテリ: 搭載不可', infos)
        self.assertIn('USBポート: あり', infos)
        with self.assertRaises(SystemExit): self.run_body('装着', 'FX5S-30MR/ES')

    def test_fx5u_80_has_two_service_power_terminal_pairs(self):
        full = gen.fx5_body_symbol('full', True, True, True, True, 2)
        self.assertTrue({'24V', '0V', '24V_2', '0V_2'} <= full.terminals.keys())
        root = self.run_body(None, 'FX5U-80MR/ES')
        self.assertEqual(len(root.findall('.//diagram/conductors/conductor')), 0)
        self.assertEqual(len(next(e for e in root.iter('element') if 'fx5_body_' in (e.get('type') or '')).findall('./terminals/terminal')), len(full.terminals))

    def test_fx5uc_power_connector_uses_numbered_pins(self):
        sym = gen.fx5_body_symbol('uc', False, True, True, False, power_connector=True)
        self.assertTrue({'1', '2', '3'} <= sym.terminals.keys())
        self.assertFalse({'+', '-', '⏚'} & sym.terminals.keys())
        self.assertIn('電源入力（コネクタ）', [attrs['text'] for kind, attrs in sym.parts if kind == 'text'])
        normal = gen.fx5_body_symbol('u', False, True, True, False)
        self.assertIn('電源入力', [attrs['text'] for kind, attrs in normal.parts if kind == 'text'])

    def test_expansion_board_state_and_compatibility(self):
        for value in ('', 'なし'):
            root = self.run_body(None, 'FX5U-32MR/ES', board_model=value)
            used = root.find('.//diagram/elements/element')
            names = [v.text for v in used.findall('./dynamic_texts/dynamic_elmt_text/info_name')]
            self.assertNotIn('auxiliary10', names)
            sym = gen.fx5_body_symbol('test', True, True, True, True)
            self.assertFalse(any(kind == 'rect' and attrs.get('x') == 175 for kind, attrs in sym.parts))
        for model in ('FX5S-30MR/ES', 'FX5UJ-24MR/ES', 'FX5U-32MR/ES'):
            root = self.run_body(None, model, board_model='FX5-3A-BD')
            info = [v.text for v in root.findall('.//diagram/elements/element/elementInformations/elementInformation')]
            self.assertIn('FX5-3A-BD', info)
        root = self.run_body(None, 'FX5U-32MR/ES', modules=['FX5-485-BD'])
        info = [v.text for v in root.findall('.//diagram/elements/element/elementInformations/elementInformation')]
        self.assertIn('FX5-485-BD', info)
        for model, board in [('FX5UC-32MT/D', 'FX5-3A-BD'), ('FX5U-32MR/ES', 'FX5-SDCD')]:
            with self.assertRaises(SystemExit): self.run_body(None, model, board_model=board)

    def test_board_ports_use_fixed_frame_and_right_connections(self):
        frame = None
        for model, count in [('FX5-3A-BD', 8), ('FX5-232-BD', 1), ('FX5-485-BD', 5), ('FX5-422-BD-GOT', 1), ('FX5-SDCD', 0)]:
            spec = gen.FX5_BOARDS[model]
            cpu = 'FX5S-30MR/ES' if model == 'FX5-SDCD' else 'FX5U-32MR/ES'
            features = gen.FX5U_SPECS[cpu]
            sym = gen.fx5_body_symbol('test', True, features['analog'], features['rs485'], features['service'], board_spec=spec)
            board_frame = next(attrs for kind, attrs in sym.parts if kind == 'rect' and attrs.get('x') == 175)
            frame = board_frame if frame is None else frame
            self.assertEqual(board_frame, frame)
            self.assertEqual(board_frame['x'] + board_frame['width'], 330)
            ports = [v for k, v in sym.terminals.items() if k.startswith('board:')]
            self.assertEqual(len(ports), count)
            self.assertTrue(all(port[1] == 'e' for port in ports))
            edge = {'FX5-3A-BD':330, 'FX5-485-BD':330, 'FX5-232-BD':318, 'FX5-422-BD-GOT':309}.get(model)
            self.assertTrue(all(port[2] == edge for port in ports))
            self.assertFalse(any(kind=='line' and a['y1']==a['y2']==port[3] and
                                 max(a['x1'],a['x2'])>edge for port in ports for kind,a in sym.parts))
            root = self.run_body(None, cpu, board_model=model)
            self.assertEqual(len(root.findall('.//diagram/conductors/conductor')), 0)
            self.assertEqual(len(next(e for e in root.iter('element') if 'fx5_body_' in (e.get('type') or '')).findall('./terminals/terminal')), len(sym.terminals))

    def test_rs485_board_signal_labels_match_terminals(self):
        sym = gen.fx5_body_symbol('test', True, True, True, True, board_spec=gen.FX5_BOARDS['FX5-485-BD'])
        labels = [(attrs['text'], attrs['y']) for kind, attrs in sym.parts if kind == 'text']
        self.assertNotIn('端子台', [text for text, _ in labels])
        for i, (terminal, signal) in enumerate((('RDA', 'RXD+'), ('RDB', 'RXD-'), ('SDA', 'TXD+'), ('SDB', 'TXD-'), ('SG', 'GND'))):
            self.assertIn((terminal, 159 + i * 21), labels)
            self.assertIn((signal, 159 + i * 21), labels)

    def test_analog_board_signal_labels_match_terminals(self):
        spec = gen.FX5_BOARDS['FX5-3A-BD']
        sym = gen.fx5_body_symbol('test', True, True, True, True, board_spec=spec)
        labels = [(attrs['text'], attrs['y']) for kind, attrs in sym.parts if kind == 'text']
        expected = ['CH1 電圧入力', 'CH1 電流入力', 'CH1 コモン', 'CH2 電圧入力',
                    'CH2 電流入力', 'CH2 コモン', 'CH3 電圧/電流出力', 'CH3 コモン']
        for i, (terminal, signal) in enumerate(zip(spec['ports'], expected)):
            self.assertIn((terminal, 159 + i * 21), labels)
            self.assertIn((signal, 159 + i * 21), labels)

if __name__ == '__main__': unittest.main()
