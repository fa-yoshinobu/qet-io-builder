import tempfile
import json
import unittest
from pathlib import Path
import gui_core as gui

class GuiPropertiesTest(unittest.TestCase):


    def test_folder_fields_and_model_specific_voltage(self):
        self.assertEqual(gui.property_fields('fx5analog'), ['kind','model','tag','unit_no','title','csv'])
        self.assertIn('left_station', gui.property_fields('qcomm'))
        self.assertNotIn('input_voltage', gui.property_fields('input', 'RX40C7'))
        self.assertIn('input_voltage', gui.property_fields('input', 'RX70C4'))
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); (p/'gui_properties.toml').write_text('[fx5analog]\nfields=["unknown"]\n', encoding='utf-8')
            with self.assertRaises(ValueError): gui.property_fields('fx5analog', root=p)

    def test_selected_model_uses_its_own_folder_settings(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for folder, model, fields in [('a', 'A1', '["model", "csv"]'), ('b', 'B1', '["model", "title"]')]:
                p = root / folder; p.mkdir()
                (p/'gui_properties.toml').write_text('[input]\nfields=' + fields + '\n', encoding='utf-8')
                (p/(model+'.json')).write_text(json.dumps({'model':model}), encoding='utf-8')
            self.assertEqual(gui.property_fields('input', 'A1', root), ['kind','model','tag','unit_no','csv'])
            self.assertEqual(gui.property_fields('input', 'B1', root), ['kind','model','tag','unit_no','title'])


if __name__=='__main__': unittest.main()
