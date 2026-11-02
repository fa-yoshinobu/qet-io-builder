"""公式資料で確定したアクチュエータの配線条件を固定する。"""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'parts/control'


def definitions(folder):
    return {p.stem: json.loads(p.read_text(encoding='utf-8')) for p in (ROOT / folder).glob('*/*.json')}


class StandardActuatorDefinitionsTest(unittest.TestCase):
    def test_eleven_models_have_sources_and_only_standard_bindings(self):
        records = [d for s in ('omron/m2bj', 'mitsubishi/sf_pr', 'smc/10_sy') for d in definitions(s).values()]
        self.assertEqual(len(records), 11)
        for record in records:
            self.assertEqual(record['category'], 'standard_device')
            spec = record['definition']
            self.assertTrue(spec['source'])
            self.assertTrue(spec['symbol_bindings'])
            self.assertNotIn('drawing', spec)

    def test_buzzer_supply_is_not_sound_selection_jumper(self):
        records = definitions('omron/m2bj')
        self.assertEqual(len(records), 6)
        for model, record in records.items():
            spec = record['definition']
            self.assertEqual(spec['ratings']['polarity'], 'none')
            self.assertEqual(spec['ratings']['supply_voltage'], 'DC12–24V' if model.endswith('-D') else 'AC/DC12–24V')
            self.assertEqual(spec['symbol_bindings'][0]['terminals'], {'first': ['電源（左）'], 'second': ['電源（右）']})
            self.assertNotIn('DA', model)

    def test_motor_uses_domestic_three_lead_and_ground_symbol(self):
        for record in definitions('mitsubishi/sf_pr').values():
            spec = record['definition']
            self.assertEqual(spec['ratings']['poles'], 4)
            self.assertEqual(spec['symbol_bindings'][0]['symbol'], 'motor_3phase_pe')
            self.assertEqual(spec['symbol_bindings'][0]['terminals'], {'u': ['U'], 'v': ['V'], 'w': ['W'], 'pe': ['PE']})
            self.assertIn('メーカーの端子刻印番号ではない', spec['verification_note'])

    def test_smc_double_solenoid_has_two_independent_coils(self):
        records = definitions('smc/10_sy')
        for model, record in records.items():
            spec = record['definition']
            count = 2 if model == '10-SY3220-5G-C6' else 1
            self.assertEqual(len(spec['symbol_bindings']), count)
            self.assertEqual(spec['ratings']['coil_voltage'], 'DC24V')
            self.assertFalse(spec['ratings']['surge_suppressor'])
            self.assertFalse(spec['ratings']['indicator'])
            for coil in spec['symbol_bindings']:
                self.assertEqual(coil['symbol'], 'solenoid_coil')
                self.assertEqual(set(coil['terminals']), {'a1', 'a2'})
                self.assertIn('赤 (+)', coil['terminals']['a1'][0])
                self.assertIn('黒 (-)', coil['terminals']['a2'][0])


if __name__ == '__main__':
    unittest.main()
