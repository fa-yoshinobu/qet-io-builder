"""Information module connectors and allocations from startup manuals."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

import gen_io_page as g
import gui_core as gui

ROOT = Path(__file__).resolve().parents[1]
MODELS = {'RD81RC96': 1, 'RD81RC96-CA': 1, 'RD81MES96N': 2,
          'RD81OPC96': 2, 'RD81DL96': 1, 'RD81DC96': 1}


class IqrInformationTest(unittest.TestCase):
    def test_physical_ports_and_allocation(self):
        for model, ethernet_count in MODELS.items():
            with self.subTest(model=model):
                spec = g.IQR_COMM[model]
                self.assertEqual([i['kind'] for i in spec['interfaces']], ['rj45'] * ethernet_count + ['sd'])
                self.assertEqual(spec['slots'], 1)
                self.assertEqual(g.slot_points(model, False, 16), (32, 'X/Y'))
                self.assertFalse(spec['external_power'])
                self.assertFalse(spec['usb'])
                self.assertEqual(spec['sd_card_capacity_gb'], [2, 16])

    def test_ch1_only_constraints_are_retained(self):
        self.assertTrue(any('CH1' in note for note in g.IQR_COMM['RD81MES96N']['diagram_notes']))
        self.assertEqual(len(g.IQR_COMM['RD81OPC96']['diagram_notes']), 2)

    def test_gui_selection_and_generated_connectable_ports(self):
        picker = gui.part_catalog('left_model', 'iqrcomm')['mitsubishi']['iq_r']
        symbols = g.build_symbols()
        for model, ethernet_count in MODELS.items():
            with self.subTest(model=model):
                self.assertIn(model, picker)
                self.assertIn(model, gui.part_catalog('modules', 'iqrbody')['mitsubishi']['iq_r'])
                self.assertIn('left_ip', gui.property_fields('iqrcomm', model))
                page = g.build_q_comm_page({'kind': 'iqrcomm', 'left_model': model}, symbols)
                self.assertEqual(sum(key == 'module_rj45' for key, _, _, _ in page.placed), ethernet_count)
                self.assertEqual(sum(key == 'comm_sd' for key, _, _, _ in page.placed), 1)
                self.assertFalse(symbols['comm_sd'].terminals)

    def test_six_models_generate_project(self):
        config = json.loads((ROOT / 'tests/fixtures/project.json').read_text(encoding='utf-8'))
        config['pages'] = [{'kind': 'iqrcomm', 'left_model': model} for model in MODELS]
        with tempfile.TemporaryDirectory() as folder:
            cfg = Path(folder) / 'project.json'
            out = Path(folder) / 'result.qet'
            cfg.write_text(json.dumps(config, ensure_ascii=False), encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()):
                g.main(str(cfg), str(out))
            self.assertEqual(len(ET.parse(out).findall('.//diagram')), 6)


if __name__ == '__main__':
    unittest.main()
