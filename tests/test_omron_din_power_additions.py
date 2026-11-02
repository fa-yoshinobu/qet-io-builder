import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

import gen_io_page as gen
import gui_core
from tools import qet_collection
from tools.export_power_supply_elements import definition
from webgui.api import Api


FS = {f'S8FS-G{w:03}24'+('CD' if w<100 else 'CD-500'): (w,a) for w,a in [(15,.65),(30,1.5),(50,2.2),(100,4.5),(150,6.5),(300,14),(600,27)]}
FS.update({'S8FS-G30024CD-H': (300,14), 'S8FS-G60024CD-H': (600,27)})
AS = {f'S8AS2-{w}24-{c:02}{end}':(w,c) for w,c in [(240,6),(480,8)] for end in ['S','SN']}
MODELS = [*FS, *AS]


class OmronDinPowerAdditionsTest(unittest.TestCase):
    def test_only_24v_din_models_and_rated_currents(self):
        specs=gen.read_unit_definitions()['power_supply']
        self.assertEqual({m for m in specs if m.startswith('S8FS-G')},set(FS))
        self.assertEqual({m for m in specs if m.startswith('S8AS2-')},set(AS))
        for m in MODELS:
            s=specs[m]
            self.assertEqual(s['mounting'],'DINレール')
            self.assertEqual(s['output']['voltage_v'],24)
            self.assertNotIn('error',Api().part_options(m))
            if m in FS:
                w,a=FS[m]
                self.assertEqual((s['output']['power_w'],s['output']['current_a']),(w,a))
                self.assertEqual(s['extended_hold_time'],m.endswith('-H'))
            else:
                w,c=AS[m]
                self.assertEqual(s['output']['branches'],c)
                self.assertEqual(s['output']['current_a'],10 if w==240 else 20)
                self.assertEqual(s['output']['parameter_settings_changeable'],not m.endswith('SN'))

    def test_all_physical_ports_and_internal_common_are_distinct(self):
        specs=gen.read_unit_definitions()['power_supply']
        for m in MODELS:
            s=specs[m];root=definition(m,s);pins=root.findall('./description/terminal')
            with self.subTest(model=m):
                if m in FS:
                    self.assertEqual(len(pins),5 if FS[m][0]<=50 else 7)
                else:
                    self.assertEqual(len(pins),AS[m][1]*4+14)
                    groups={g['role']:g['terminals'] for g in s['terminal_groups']}
                    for ch in range(1,AS[m][1]+1):
                        for sign in ['+','−']:
                            self.assertEqual(sum(t.get('channel')==ch and t['polarity']==sign for t in groups['output']),2)
                    self.assertEqual([t['label'] for t in groups['signal']],['TRP','LOW','LFE','TMP','COM','TRG+','TRG-'])
                    self.assertTrue(all('signal_COM' not in common for common in s['internal_connections']))
                self.assertEqual(len({t.get('uuid') for t in pins}),len(pins))
                self.assertEqual(ET.tostring(root),ET.tostring(definition(m,s)))

    def test_branch_labels_share_a_fixed_right_edge(self):
        specs = gen.read_unit_definitions()['power_supply']
        for model in AS:
            root = definition(model, specs[model])
            labels = root.findall("./description/dynamic_text[@text_from='UserText']")
            self.assertEqual(len(labels), AS[model][1]*4)
            self.assertTrue(all(n.get('Halignment') == 'AlignRight' for n in labels))
            self.assertEqual({float(n.get('x'))+float(n.get('text_width')) for n in labels}, {246})
            self.assertEqual(len({n.get('uuid') for n in labels}), len(labels))
            self.assertTrue(any('+' in n.findtext('text') for n in labels))
            self.assertTrue(any('−' in n.findtext('text') for n in labels))

    def test_catalog_and_registration_include_both_power_series(self):
        catalog=gui_core.part_catalog('standard_model','')['omron']
        self.assertEqual(set(catalog['s8as2']),set(AS))
        self.assertEqual(set(catalog['s8fs_g']),set(FS))
        with tempfile.TemporaryDirectory() as folder,patch.object(qet_collection,'user_collection_dir',return_value=Path(folder)):
            r=qet_collection.register_all_parts(MODELS)
            self.assertTrue(r['ok'],r['errors'])
            self.assertEqual((r['models'],r['parts']),(13,13))
            self.assertEqual(len(list(Path(folder).rglob('*.elmt'))),13)
