import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class IqrTsnHeadTest(unittest.TestCase):
    def definition(self, model):
        data = json.loads((ROOT / 'parts/plc/mitsubishi/iq_r/network' / (model + '.json')).read_text(encoding='utf-8'))
        self.assertEqual(data['category'], 'iqr_comm')
        return data['definition']

    def test_tsn_physical_interfaces_and_occupation(self):
        # SH-082127ENG-P 1.1/1.2/2.3 and SH-082472ENG-J 4.4/5.
        expected = {
            'RJ71GN11-T2': [('P1 CC-Link IE TSN', 'rj45'), ('P2 CC-Link IE TSN', 'rj45')],
            'RJ71GN11-SX': [('P1 CC-Link IE TSN', 'optical'), ('P2 CC-Link IE TSN', 'optical')],
            'RJ71GN11-EIP': [('P1 CC-Link IE TSN', 'rj45'), ('P2 EtherNet/IP', 'rj45')],
        }
        for model, interfaces in expected.items():
            with self.subTest(model=model):
                spec = self.definition(model)
                self.assertEqual([(i['name'], i['kind']) for i in spec['interfaces']], interfaces)
                self.assertEqual(spec['occupied_io_points'], 32)
                self.assertEqual(spec['slots'], 1)
        self.assertEqual(self.definition('RJ71GN11-SX')['interfaces'][0]['connector_label'], 'Duplex LC')

    def test_remote_head_cpu_slot_and_usb(self):
        # SH-081614ENG-I 1 and 5: CPU slot, two Ethernet ports, USB Mini-B.
        spec = self.definition('RJ72GF15-T2')
        self.assertEqual(spec['mount_position'], 'cpu_slot')
        self.assertEqual(spec['module_role'], 'remote_head')
        self.assertEqual([(i['name'], i['kind']) for i in spec['interfaces']], [
            ('P1 CC-Link IE Field', 'rj45'), ('P2 CC-Link IE Field', 'rj45'), ('USB', 'usb')])
        self.assertTrue(spec['ethernet'])
        self.assertTrue(spec['usb_port'])
        self.assertEqual(spec['usb_type'], 'Mini-B')
        self.assertFalse(spec['sd_card_supported'])
