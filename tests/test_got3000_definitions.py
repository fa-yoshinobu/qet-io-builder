"""SH-082581C/SH-082583Dに基づくGOT3000装備の回帰確認。"""
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1] / 'parts/hmi/mitsubishi/got3000/body'
MODELS = {
    'GT3715-FHCBD': 'DC', 'GT3712-WXCBD': 'DC',
    'GT3715-XRBA': 'AC', 'GT3715-XRBD': 'DC',
    'GT3712-XRBA': 'AC', 'GT3712-XRBD': 'DC',
    'GT3710-XRBA': 'AC', 'GT3710-XRBD': 'DC',
    'GT3708-XRBA': 'AC', 'GT3708-XRBD': 'DC',
}


class Got3000DefinitionsTest(unittest.TestCase):
    def definitions(self):
        return {p.stem: json.loads(p.read_text(encoding='utf-8')) for p in ROOT.glob('*.json')}

    def test_ten_models_keep_power_markings_and_two_ground_positions(self):
        definitions = self.definitions()
        self.assertEqual(set(definitions), set(MODELS))
        for model, supply in MODELS.items():
            with self.subTest(model=model):
                item = definitions[model]
                self.assertEqual(item['category'], 'got_body')
                spec = item['definition']
                self.assertEqual(spec['power']['supply'], supply)
                self.assertEqual(spec['power']['ports'],
                                 ['N', 'L', '⏚', '⏚'] if supply == 'AC' else ['−', '＋', '⏚', '⏚'])
                self.assertTrue(spec['power']['ground_position_confirmed'])

    def test_builtin_ports_and_optional_battery(self):
        for model, item in self.definitions().items():
            with self.subTest(model=model):
                spec = item['definition']
                kinds = [interface['kind'] for interface in spec['interfaces']]
                self.assertEqual(kinds, ['dsub9', 'rj45', 'rj45', 'usb_c', 'usb_a', 'hdmi', 'sd'])
                self.assertIn('共用', spec['interfaces'][0]['name'])
                self.assertTrue(spec['battery_supported'])
                self.assertEqual(spec['battery_type'], 'GT11-50BAT')
                self.assertFalse(spec['battery_included'])
                self.assertTrue(spec['sd_card_supported'])
                self.assertEqual(spec['sd_card_capacity_gb'], 32)

    def test_shared_serial_mode_pinouts_are_not_got2000_rs232(self):
        spec = self.definitions()['GT3715-XRBD']['definition']
        rs232 = spec['serial_modes']['RS-232']
        self.assertEqual([(p['pin'], p['signal']) for p in rs232], list(zip(
            [str(i) for i in range(1, 10)],
            ['RI(NC)', 'DSR(DR)', 'TXD(SD)', 'RXD(DR)', 'SG', 'DTR(ER)', 'DCD(CD)', 'RTS(RS)', 'CTS(CS)'])))
        self.assertFalse(rs232[0]['connectable'])
        self.assertEqual([p['signal'] for p in spec['serial_modes']['RS-422/485']],
                         ['TXD+(SDA)', 'RXD+(RDA)', 'RTS+(RSA)', 'CTS+(CSA)', 'SG',
                          'TXD−(SDB)', 'RXD−(RDB)', 'RTS−(RSB)', 'CTS−(CSB)'])


if __name__ == '__main__':
    unittest.main()
