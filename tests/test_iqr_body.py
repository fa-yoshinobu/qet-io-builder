import contextlib,io,json,tempfile,unittest
from pathlib import Path
from xml.etree import ElementTree as ET
import gen_io_page as gen

class IqrBodyTest(unittest.TestCase):
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

    def test_communication_page_places_modules_on_selected_halves(self):
        pg={'kind':'qcomm','left_model':'QJ61BT11N','right_model':'QJ71GF11-T2',
            'left_station':'局 3', 'right_station':'局 5', 'right_ip':'192.168.1.5', 'left_dip':'SW1 ON',
            'settings_visibility': {'right_ip': True, 'left_dip': True}}
        page=gen.build_q_comm_page(pg,gen.build_symbols())
        elements=[(e,x) for k,e,x,y in page.placed if k=='module_pin']
        self.assertEqual([x for e,x in elements], [275]*5)
        self.assertEqual([x for k,e,x,y in page.placed if k=='module_rj45'], [895]*2)
        labels=[next(v.text for v in e.findall('./elementInformations/elementInformation') if v.get('name')=='label') for e,x in elements]
        self.assertEqual(labels[:5],['DA','DB','DG','SLD','FG'])
        self.assertTrue(all(e.find('./dynamic_texts/dynamic_elmt_text/info_name').text == 'label' for e,x in elements))
        self.assertEqual(sum(k.startswith('module_') for k,_,_,_ in page.placed),7)
        self.assertEqual(len(page.conductors),0)
        texts=[t.get('text') for t in page.texts]
        for value in ('局番・NW No.','IP設定','機器設定','通信設定','局 3','局 5','192.168.1.5','SW1 ON','（記入）'):
            self.assertIn(value,texts)

    def test_q_network_connectors_and_external_power(self):
        cases = [('QJ71BR11', 'module_coax', 1, 0), ('QJ71E71-100', 'module_rj45', 1, 0),
                 ('QJ71GP21-SX', 'module_optical', 2, 0), ('QJ71GP21S-SX', 'module_optical', 2, 3),
                 ('QJ71LP21S-25', 'module_optical', 2, 3)]
        for model, kind, count, power_count in cases:
            with self.subTest(model=model):
                page=gen.build_q_comm_page({'kind':'qcomm','right_model':model}, gen.build_symbols())
                self.assertEqual(sum(k == kind for k, _, _, _ in page.placed), count)
                self.assertEqual(sum(k == 'module_pin' for k, _, _, _ in page.placed), power_count)
                self.assertTrue(all(e.find('./dynamic_texts/dynamic_elmt_text/info_name').text == 'label' for k,e,_,_ in page.placed if k == 'module_pin'))
                self.assertEqual(sum(k.startswith('module_') for k,_,_,_ in page.placed), count + power_count)
                self.assertEqual(len(page.conductors), 0)

    def test_iqr_communication_connector_types_and_terminals(self):
        cases = [('RJ61BT11', 'module_pin', 5), ('RJ71BR11', 'module_coax', 1),
                 ('RJ71EN71', 'module_rj45', 2), ('RJ71GP21S-SX', 'module_optical', 2),
                 ('RJ71C24', 'module_dsub', 1), ('RJ71C24-R4', 'module_pin', 14)]
        for model, kind, count in cases:
            with self.subTest(model=model):
                page=gen.build_q_comm_page({'kind':'iqrcomm','right_model':model}, gen.build_symbols())
                self.assertEqual(sum(k == kind for k, _, _, _ in page.placed), count)
                self.assertTrue(all(x == 895 for k, _, x, _ in page.placed if k == kind))
                if model == 'RJ71C24-R4':
                    labels=[next(v.text for v in e.findall('./elementInformations/elementInformation') if v.get('name') == 'label') for k,e,_,_ in page.placed if k == 'module_pin']
                    self.assertEqual(labels, ['SDA','SDB','RDA','RDB','SG','SLD','FG'] * 2)

    def test_communication_page_requires_valid_model(self):
        cfg=json.loads((Path(__file__).parent / 'fixtures' / 'project.json').read_text(encoding='utf-8'))
        for pg in ({'kind':'qcomm'}, {'kind':'qcomm','right_model':'INVALID'}, {'kind':'qcomm','left_model':'QJ61BT11N','left_station':3}):
            cfg['pages']=[pg]
            with self.subTest(pg=pg), tempfile.TemporaryDirectory() as d:
                p=Path(d); (p/'p.json').write_text(json.dumps(cfg,ensure_ascii=False),encoding='utf-8')
                with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit): gen.main(str(p/'p.json'),str(p/'p.qet'))

    def test_fx_communication_units_support_both_page_halves(self):
        pg = {'kind':'fxcomm', 'left_model':'FX5-232ADP', 'right_model':'FX5-485ADP'}
        page = gen.build_q_comm_page(pg, gen.build_symbols())
        self.assertEqual([x for kind, _, x, _ in page.placed if kind == 'module_dsub'], [275])
        self.assertEqual([x for kind, _, x, _ in page.placed if kind == 'module_pin'], [895] * 5)
        self.assertEqual(sum(k.startswith('module_') for k,_,_,_ in page.placed), 6)
        self.assertEqual(len(page.conductors), 0)

    def test_q_serial_interfaces_and_duplicate_fg_terminals(self):
        for model, dsub_count, terminal_count in [('QJ71C24N', 1, 7), ('QJ71C24N-R2', 2, 0), ('QJ71C24N-R4', 0, 12)]:
            with self.subTest(model=model):
                page = gen.build_q_comm_page({'kind':'qcomm', 'right_model':model}, gen.build_symbols())
                self.assertEqual(sum(kind == 'module_dsub' for kind, _, _, _ in page.placed), dsub_count)
                pins = [e for kind, e, _, _ in page.placed if kind == 'module_pin']
                self.assertEqual(len(pins), terminal_count)
                self.assertTrue(all(x == 895 for kind, _, x, _ in page.placed if kind in ('module_pin','module_dsub')))
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
