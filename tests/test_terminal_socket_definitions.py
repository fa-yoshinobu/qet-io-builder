import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / 'parts/control/omron'


def spec(series, kind, model):
    return json.loads((ROOT / series / kind / (model + '.json')).read_text(encoding='utf-8'))['definition']


class TerminalSocketDefinitionsTest(unittest.TestCase):
    def test_eight_terminals_preserve_wire_ports_and_pe(self):
        files = list((ROOT / 'xw5t/terminal').glob('*.json'))
        self.assertEqual(len(files), 8)
        for path in files:
            data = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(data['category'], 'standard_device')
            s = data['definition']
            self.assertEqual(sum(len(b['terminals']) for b in s['symbol_bindings']), s['physical_wire_ports'])
            self.assertTrue(s['user_terminal_number_required'])
        pe = spec('xw5t', 'terminal', 'XW5G-P2.5-1.1-1')
        self.assertTrue(pe['conductive_din_rail_required'])
        self.assertNotIn('iec_current_a', pe['ratings'])
        common = spec('xw5t', 'terminal', 'XW5T-P2.5-2.2-1')
        self.assertEqual(common['ratings']['iec_current_a'], 24)
        self.assertEqual(len(common['internal_connections'][0]), 4)

    def test_passive_sockets_do_not_invent_coils_or_contacts(self):
        files = list((ROOT / 'relay_sockets/socket').glob('*.json'))
        self.assertTrue(files)
        for path in files:
            s = json.loads(path.read_text(encoding='utf-8'))['definition']
            self.assertEqual(len(s['terminal_map']), s['electrical_terminals'])
            self.assertTrue(all(b['symbol'] == 'terminal' for b in s['symbol_bindings']))
            self.assertNotIn('coil', s)
            self.assertNotIn('contacts', s)
            self.assertFalse(s['internal_connections'])
            self.assertEqual(len({m['relay_pin'] for m in s['terminal_map']}), s['electrical_terminals'])
            self.assertTrue(s.get('compatible_relays') or s.get('compatible_timers'))

    def test_my_and_ly_eight_pin_socket_iec_numbers_are_distinct(self):
        my = spec('relay_sockets', 'socket', 'PYF-08-PU')
        ly = spec('relay_sockets', 'socket', 'PTF-08-PU')
        mapping = lambda s: {m['socket_marking']: m['relay_pin'] for m in s['terminal_map']}
        self.assertEqual(mapping(my), {'11': '9', '14': '5', '12': '1', '41': '12', '44': '8', '42': '4', 'A1': '13', 'A2': '14'})
        self.assertEqual(mapping(ly), {'11': '5', '14': '3', '12': '1', '21': '6', '24': '4', '22': '2', 'A1': '7', 'A2': '8'})
        self.assertEqual({m['wire_entries'] for m in my['terminal_map']}, {2})

    def test_current_and_release_lever_conditions_are_retained(self):
        pu = spec('relay_sockets', 'socket', 'PYF-08-PU')
        no_lever = spec('relay_sockets', 'socket', 'PYF-08-PU-L')
        self.assertTrue(pu['release_lever'])
        self.assertFalse(no_lever['release_lever'])
        self.assertEqual(pu['ratings']['current_temperature_limits'], [{'ambient_max_c': 55, 'current_a': 10}, {'ambient_max_c': 70, 'current_a': 7}])
        screw = spec('relay_sockets', 'socket', 'PYF11A')
        self.assertEqual(screw['ratings']['continuous_current_a'], 5)


if __name__ == '__main__':
    unittest.main()
