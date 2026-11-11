import contextlib,io,json,tempfile,unittest
from pathlib import Path
from xml.etree import ElementTree as ET
import gen_io_page as gen

class IqrBodyTest(unittest.TestCase):
    def communication_pages(self, page):
        root, _ = gen.build_project(gen.project_config({'front_pages': False}), [(page, None)])
        diagrams = root.findall('diagram')
        self.assertEqual(len(diagrams), sum(bool(page.get(side + '_model')) for side in ('left', 'right')))
        return diagrams

    def elements(self, page, kind):
        return [element for element in page.findall('./elements/element')
                if element.get('type', '').endswith('/' + kind + '.elmt')]

    def build(self, **updates):
        cfg=json.loads((Path(__file__).parent / 'fixtures' / 'project.json').read_text(encoding='utf-8'))
        pg={'kind':'iqrbody','model':'R04CPU','power_model':'R61P','base_model':'R35B','modules':['RX41C4','RY41NT2P'],'battery':'非装着'}
        pg.update(updates);cfg['pages']=[pg]
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'p.json').write_text(json.dumps(cfg,ensure_ascii=False),encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()): gen.main(str(p/'p.json'),str(p/'p.qet'))
            return ET.parse(p/'p.qet').getroot()
    def test_configuration_and_terminal_count(self):
        r=self.build(); syms=gen.build_symbols()
        self.assertEqual(set(syms['iqr_ac'].terminals),{'ac1','ac2','lg','fg','err1','err2'})
        # 電池・USB などは CPU の箱ではなく欄外の表(図面の文字)に書く
        texts=[i.get('text') for i in r.findall('.//diagram/inputs/input')]
        for word in ('CPUの設定/オプション','バッテリ','非装着','SDメモリカード','メモリカセット'):
            self.assertIn(word,texts)
        # USB と Ethernet は CPU の箱に絵で描く(表には書かない)
        self.assertNotIn('USBポート',texts)
        types=[e.get('type') for e in r.findall('.//diagram/elements/element')]
        self.assertTrue(any(t.endswith('/iqr_cpu_lan_usb.elmt') for t in types))
    def test_invalid_models_or_slots_fail(self):
        for bad in ({'power_model':'INVALID'},{'modules':['RX41C4']*6},{'battery':'搭載不可'}):
            with self.subTest(bad=bad),self.assertRaises(SystemExit):self.build(**bad)

    def test_q_communication_modules_are_accepted(self):
        cfg=json.loads((Path(__file__).parent / 'fixtures' / 'project.json').read_text(encoding='utf-8'))
        for model in gen.Q_COMM:
            cfg['pages']=[{'kind':'qbody','model':'Q03UDVCPU','power_model':'Q61P','base_model':'Q35B','modules':[model]}]
            with self.subTest(model=model), tempfile.TemporaryDirectory() as d:
                p=Path(d); (p/'p.json').write_text(json.dumps(cfg,ensure_ascii=False),encoding='utf-8')
                with contextlib.redirect_stdout(io.StringIO()): gen.main(str(p/'p.json'),str(p/'p.qet'))
                texts=[e.get('text') for e in ET.parse(p/'p.qet').getroot().findall('.//diagram/inputs/input')]
                self.assertIn(model,texts)

    def test_iqr_communication_modules_generate_and_reject_q_models(self):
        cfg=json.loads((Path(__file__).parent / 'fixtures' / 'project.json').read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            for model in gen.IQR_COMM:
                with self.subTest(model=model):
                    spec=gen.IQR_COMM[model]
                    head=spec.get('mount_position') == 'cpu_slot'
                    cfg['pages']=[{'kind':'iqrbody','model':model if head else 'R04CPU','power_model':'R61P','base_model':'R35B','modules':[] if head else [model]},
                                  {'kind':'iqrcomm','left_model':model}]
                    (p/'p.json').write_text(json.dumps(cfg,ensure_ascii=False),encoding='utf-8')
                    with contextlib.redirect_stdout(io.StringIO()): gen.main(str(p/'p.json'),str(p/'p.qet'))
                    diagrams=ET.parse(p/'p.qet').getroot().findall('.//diagram')
                    self.assertEqual(len(diagrams),2)
                    expected=(sum(len(iface.get('ports', [])) if iface['kind']=='terminal' else 1 for iface in spec['interfaces'])
                              if spec.get('interfaces') else len(spec['ports']) + len(spec.get('power_ports', [])))
                    # 端子・コネクタは部品として置く(行き先のない線は引かない)
                    self.assertEqual(len([e for e in diagrams[1].findall('./elements/element') if '/module_' in e.get('type') or '/comm_' in e.get('type')]),expected)
                    self.assertEqual(len(diagrams[1].findall('./conductors/conductor')),0)
            cfg['pages']=[{'kind':'iqrcomm','left_model':'QJ61BT11N'}]
            (p/'p.json').write_text(json.dumps(cfg,ensure_ascii=False),encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit): gen.main(str(p/'p.json'),str(p/'p.qet'))

    def test_communication_pages_keep_each_unit_and_its_settings_together(self):
        pg={'kind':'qcomm','left_model':'QJ61BT11N','right_model':'QJ71GF11-T2',
            'left_station':'局 3', 'right_station':'局 5', 'right_ip':'192.168.1.5', 'left_dip':'SW1 ON',
            'settings_visibility': {'right_ip': True, 'left_dip': True}}
        left, right = self.communication_pages(pg)
        elements = self.elements(left, 'module_pin')
        self.assertEqual([float(e.get('x')) for e in elements], [275]*5)
        self.assertEqual([float(e.get('x')) for e in self.elements(right, 'module_rj45')], [275]*2)
        labels=[next(v.text for v in e.findall('./elementInformations/elementInformation') if v.get('name')=='label') for e in elements]
        self.assertEqual(labels[:5],['DA','DB','DG','SLD','FG'])
        self.assertTrue(all(e.find('./dynamic_texts/dynamic_elmt_text/info_name').text == 'label' for e in elements))
        self.assertEqual(sum('/module_' in e.get('type') for d in (left, right) for e in d.findall('./elements/element')),7)
        self.assertTrue(all(not d.findall('./conductors/conductor') for d in (left, right)))
        texts=[t.get('text') for d in (left, right) for t in d.findall('./inputs/input')]
        for value in ('局番・NW No.','IP設定','機器設定','通信設定','局 3','局 5','192.168.1.5','SW1 ON','（記入）'):
            self.assertIn(value,texts)
        left_texts = [t.get('text') for t in left.findall('./inputs/input')]
        right_texts = [t.get('text') for t in right.findall('./inputs/input')]
        self.assertIn('SW1 ON', left_texts)
        self.assertNotIn('SW1 ON', right_texts)
        self.assertIn('192.168.1.5', right_texts)
        self.assertNotIn('192.168.1.5', left_texts)

    def test_q_network_connectors_and_external_power(self):
        cases = [('QJ71BR11', 'module_coax', 1, 0), ('QJ71E71-100', 'module_rj45', 1, 0),
                 ('QJ71GP21-SX', 'module_optical', 2, 0), ('QJ71GP21S-SX', 'module_optical', 2, 3),
                 ('QJ71LP21S-25', 'module_optical', 2, 3)]
        for model, kind, count, power_count in cases:
            with self.subTest(model=model):
                page, = self.communication_pages({'kind':'qcomm','right_model':model})
                self.assertEqual(len(self.elements(page, kind)), count)
                self.assertEqual(len(self.elements(page, 'module_pin')), power_count)
                self.assertTrue(all(e.find('./dynamic_texts/dynamic_elmt_text/info_name').text == 'label' for e in self.elements(page, 'module_pin')))
                self.assertEqual(sum('/module_' in e.get('type') for e in page.findall('./elements/element')), count + power_count)
                self.assertFalse(page.findall('./conductors/conductor'))

    def test_iqr_communication_connector_types_and_terminals(self):
        cases = [('RJ61BT11', 'module_pin', 5), ('RJ71BR11', 'module_coax', 1),
                 ('RJ71EN71', 'module_rj45', 2), ('RJ71GP21S-SX', 'module_optical', 2),
                 ('RJ71C24', 'module_dsub', 1), ('RJ71C24-R4', 'module_pin', 14)]
        for model, kind, count in cases:
            with self.subTest(model=model):
                page, = self.communication_pages({'kind':'iqrcomm','right_model':model})
                self.assertEqual(len(self.elements(page, kind)), count)
                self.assertTrue(all(float(e.get('x')) == 275 for e in self.elements(page, kind)))
                if model == 'RJ71C24-R4':
                    labels=[next(v.text for v in e.findall('./elementInformations/elementInformation') if v.get('name') == 'label') for e in self.elements(page, 'module_pin')]
                    self.assertEqual(labels, ['SDA','SDB','RDA','RDB','SG','SLD','FG'] * 2)

    def test_communication_page_requires_valid_model(self):
        cfg=json.loads((Path(__file__).parent / 'fixtures' / 'project.json').read_text(encoding='utf-8'))
        for pg in ({'kind':'qcomm'}, {'kind':'qcomm','right_model':'INVALID'}, {'kind':'qcomm','left_model':'QJ61BT11N','left_station':3}):
            cfg['pages']=[pg]
            with self.subTest(pg=pg), tempfile.TemporaryDirectory() as d:
                p=Path(d); (p/'p.json').write_text(json.dumps(cfg,ensure_ascii=False),encoding='utf-8')
                with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit): gen.main(str(p/'p.json'),str(p/'p.qet'))

    def test_fx_communication_units_from_both_sides_generate_separate_pages(self):
        pg = {'kind':'fxcomm', 'left_model':'FX5-232ADP', 'right_model':'FX5-485ADP'}
        left, right = self.communication_pages(pg)
        self.assertEqual([float(e.get('x')) for e in self.elements(left, 'module_dsub')], [275])
        self.assertEqual([float(e.get('x')) for e in self.elements(right, 'module_pin')], [275] * 5)
        self.assertEqual(sum('/module_' in e.get('type') for d in (left, right) for e in d.findall('./elements/element')), 6)
        self.assertTrue(all(not d.findall('./conductors/conductor') for d in (left, right)))

    def test_q_serial_interfaces_and_duplicate_fg_terminals(self):
        for model, dsub_count, terminal_count in [('QJ71C24N', 1, 7), ('QJ71C24N-R2', 2, 0), ('QJ71C24N-R4', 0, 12)]:
            with self.subTest(model=model):
                page, = self.communication_pages({'kind':'qcomm', 'right_model':model})
                self.assertEqual(len(self.elements(page, 'module_dsub')), dsub_count)
                pins = self.elements(page, 'module_pin')
                self.assertEqual(len(pins), terminal_count)
                self.assertTrue(all(float(e.get('x')) == 275 for e in pins + self.elements(page, 'module_dsub')))
                self.assertEqual(sum(next((v.text for v in e.findall('./elementInformations/elementInformation') if v.get('name') == 'label'), '') == 'FG' for e in pins), 2 if terminal_count else 0)

    def test_fx_communication_modules_and_board_compatibility(self):
        cfg=json.loads((Path(__file__).parent / 'fixtures' / 'project.json').read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            for model in gen.FX5_COMM:
                with self.subTest(model=model):
                    cfg['pages']=[{'kind':'fx5body','model':'FX5U-32MR/ES','modules':[model]},
                                  {'kind':'fxcomm','left_model':model}]
                    (p/'p.json').write_text(json.dumps(cfg,ensure_ascii=False),encoding='utf-8')
                    with contextlib.redirect_stdout(io.StringIO()): gen.main(str(p/'p.json'),str(p/'p.qet'))
                    diagrams=ET.parse(p/'p.qet').getroot().findall('.//diagram')
                    self.assertEqual(len(diagrams),2)
                    expected = 1 if model == 'FX5-232ADP' else len(gen.FX5_COMM[model]['ports'])
                    self.assertEqual(len([e for e in diagrams[1].findall('./elements/element') if '/module_' in e.get('type')]), expected)
                    self.assertEqual(len(diagrams[1].findall('./conductors/conductor')), 0)
            cfg['pages']=[{'kind':'fx5body','model':'FX5UC-32MT/D','modules':['FX5-485-BD']}]
            (p/'p.json').write_text(json.dumps(cfg,ensure_ascii=False),encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit): gen.main(str(p/'p.json'),str(p/'p.qet'))

if __name__=='__main__':unittest.main()
