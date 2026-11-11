import contextlib
import csv
import io
import json
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET
import gen_io_page as gen
import gui_core as gui

class RemoteIoTest(unittest.TestCase):
    def test_paired_outputs_use_one_return_wire_without_dummy_bend(self):
        for model in ('AJ65SBTB2N-16R', 'AJ65SBTB2-16T1', 'NZ2GF2B2-16R'):
            with self.subTest(model=model):
                rows=[{'アドレス':f'Y{i:X}','機器番号':'','信号名':'予備'} for i in range(16)]
                pg={'kind':'output','model':model}
                symbols=gen.build_symbols()
                page=gen.build_iqr_page(rows,pg,{},symbols,gen.iqr_halves(pg,rows))
                elements={e.get('uuid'):(kind,x,y) for kind,e,x,y in page.placed}
                loads=[(e,x,y) for kind,e,x,y in page.placed if kind=='load_coil']
                self.assertEqual(len(loads),16)
                paired_pins=set(gen.IO_UNITS[model]['paired_com_pins'])
                for kind,e,_,_ in page.placed:
                    info={v.get('name'):v.text for v in e.findall('./elementInformations/elementInformation')}
                    if kind=='plc_out' and info.get('auxiliary1') in paired_pins:
                        self.assertEqual(info['comment'],'コモン')
                for load,x,y in loads:
                    wires=[c for c in page.conductors if c.get('element1')==load.get('uuid')]
                    self.assertEqual(len(wires),1)
                    wire=wires[0]
                    self.assertEqual(wire.get('terminal1'),symbols['load_coil'].terminals['e'][0])
                    self.assertEqual(elements[wire.get('element2')],('tb_terminal',x-65,y+gen.ROW_PITCH))
                    self.assertEqual(wire.get('terminal2'),symbols['tb_terminal'].terminals['e'][0])

    def test_remaining_paired_common_modules_keep_all_terminals(self):
        for model, direction in [('AJ65SBTB3-16D','input'),('AJ65SBTB2N-16R','output')]:
            with self.subTest(model=model):
                spec=gen.IO_UNITS[model]
                rows=[{'アドレス':f'{"X" if direction=="input" else "Y"}{i:X}','機器番号':'','信号名':'予備'} for i in range(16)]
                pg={'kind':direction,'model':model}
                halves=gen.iqr_halves(pg,rows)
                self.assertEqual([len(h[1]) for h in halves],[8,8])
                page=gen.build_iqr_page(rows,pg,{},gen.build_symbols(),halves)
                info=[{v.get('name'):v.text for v in e.findall('./elementInformations/elementInformation')} for k,e,_,_ in page.placed if k in ('plc_in','plc_out')]
                pins=[item['auxiliary1'] for item in info]
                self.assertEqual(len(pins),34)
                self.assertEqual(set(pins),{f'TB{i}' for i in range(8,42)})
                self.assertEqual(len(pins),len(set(pins)))
                for pin,label in zip(spec['paired_com_pins'],spec['paired_com_labels']):
                    self.assertEqual(next(item['label'] for item in info if item['auxiliary1']==pin),label)

    def test_paired_relay_load_returns_to_its_com_terminal(self):
        # 負荷は Y と隣の COM B の間につなぐ(COM B は内部で TB34 につながるので外からレーンへは配線しない)
        model='NZ2GF2B2-16R'
        rows=[{'アドレス':f'Y{i:X}','機器番号':'','信号名':'予備'} for i in range(16)]
        pg={'kind':'output','model':model}
        page=gen.build_iqr_page(rows,pg,{},gen.build_symbols(),gen.iqr_halves(pg,rows))
        kinds={e.get('uuid'):(k,e) for k,e,_,_ in page.placed}
        info=lambda e:{v.get('name'):v.text for v in e.findall('./elementInformations/elementInformation')}
        paired=set(gen.IO_UNITS[model]['paired_com_pins'])
        coms={e.get('uuid') for k,e,_,_ in page.placed if k=='plc_out' and info(e).get('auxiliary1') in paired}
        self.assertEqual(len(coms),16)
        # COM B の端子台からレーン(接続点)へ行く線はない
        com_tbs=set()
        for c in page.conductors:
            a,b=c.get('element1'),c.get('element2')
            if a in coms: com_tbs.add(b)
            if b in coms: com_tbs.add(a)
        for c in page.conductors:
            ends={c.get('element1'),c.get('element2')}
            if ends & com_tbs:
                other=(ends-com_tbs).pop()
                self.assertNotEqual(kinds[other][0],'junction')
        labels=[info(e).get('label') for k,e,_,_ in page.placed if k=='plc_out']
        self.assertIn('COM A',labels)

    def test_two_wire_output_coms_are_next_to_eight_outputs_per_half(self):
        model='AJ65SBTB2-16T1'
        spec=gen.IO_UNITS[model]
        rows=[{'アドレス':f'Y{i:X}','機器番号':'','信号名':'予備'} for i in range(16)]
        pg={'kind':'output','model':model}
        halves=gen.iqr_halves(pg,rows)
        self.assertEqual([len(h[1]) for h in halves], [8,8])
        page=gen.build_iqr_page(rows,pg,{},gen.build_symbols(),halves)
        output=[(e,x,y) for kind,e,x,y in page.placed if kind=='plc_out']
        for half, start in enumerate((0,8)):
            items=[(e,y) for e,x,y in output if x==276+half*gen.HALF_W]
            for i in range(8):
                info=lambda e: {v.get('name'):v.text for v in e.findall('./elementInformations/elementInformation')}
                signal,com=items[2*i],items[2*i+1]
                self.assertEqual(info(signal[0])['auxiliary1'],spec['pins'][start+i])
                self.assertEqual(info(com[0])['auxiliary1'],spec['paired_com_pins'][start+i])
                self.assertEqual(com[1]-signal[1],gen.ROW_PITCH)
                self.assertEqual(info(com[0])['label'],'COM')
        self.assertNotIn('extra_terminals',spec)

    def test_remote_communication_symbols_and_power_pins(self):
        for model, pin_count, rj_count in [('AJ65SBTB1-16D',7,0), ('NZ2GF2B1-16D',3,2),
                                            ('NZ2GFCE3-16D',10,2), ('NZ2GFCM1-16DE',14,2)]:
            with self.subTest(model=model):
                page=gen.build_remote_body_page({'model':model},gen.build_symbols())
                pins=[e for kind,e,_,_ in page.placed if kind=='module_pin']
                self.assertEqual(len(pins),pin_count)
                self.assertTrue(all(e.find('./dynamic_texts/dynamic_elmt_text/info_name').text=='label' for e in pins))
                self.assertEqual(sum(kind=='module_rj45' for kind,_,_,_ in page.placed),rj_count)
                self.assertEqual(sum(k.startswith('module_') for k,_,_,_ in page.placed),pin_count+rj_count)
                self.assertEqual(len(page.conductors),0)

    def test_mil_pin_polarity_and_supply_rule(self):
        for model, polarity, first in [('NZ2GFCM1-16D','positive','24G I/O'), ('NZ2GFCM1-16DE','negative','+24V I/O')]:
            spec=gen.IO_UNITS[model]
            self.assertEqual(spec['input_common'], polarity)
            self.assertEqual(spec['pins'], [f'C1-{n}' for n in list(range(20,5,-2))+list(range(19,4,-2))])
            self.assertEqual(dict(spec['power_ports'])['C1-1'], first)
            page=gen.build_remote_body_page({'model':model},gen.build_symbols())
            text=''.join(t.get('text','') for t in page.texts)   # 注記は箱の幅で折り返すので行をつなげて調べる
            self.assertIn('同時に給電しない',text)
            self.assertIn('無配線コネクタ',text)

    def test_generation_and_picker(self):
        definitions={m:s for m,s in gen.read_unit_definitions()['remote_io'].items() if 'module_role' not in s and not s.get('io_connectors')}  # 旧形式の回帰。新形式は専用テストで確認
        self.assertIn("NZ2GF2S1-16D", definitions)
        cfg=json.loads((Path(__file__).parent/'fixtures'/'project.json').read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            for model,spec in definitions.items():
                with self.subTest(model=model):
                    prefix='X' if spec['io']=='in' else 'Y'
                    with (p/'io.csv').open('w',encoding='utf-8-sig',newline='') as f:
                        w=csv.writer(f);w.writerow(['アドレス','機器番号','信号名']);w.writerows([[f'{prefix}{i:X}','','予備'] for i in range(spec['points'])])
                    cfg['pages']=[{'kind':'remotebody','model':model,'station':'3','ip':'192.168.3.3','dip':'SW1 ON','settings_visibility':{'dip':True,'ip':True}}, {'kind':'input' if spec['io']=='in' else 'output','model':model,'csv':'io.csv','title':'IO'}]
                    (p/'in.json').write_text(json.dumps(cfg,ensure_ascii=False),encoding='utf-8')
                    with contextlib.redirect_stdout(io.StringIO()):gen.main(str(p/'in.json'),str(p/'out.qet'))
                    diagrams=ET.parse(p/'out.qet').getroot().findall('.//diagram')
                    self.assertEqual(len(diagrams), 2 + ((spec["points"] + 7) // 8 if spec.get("sensor_pins") else 0) + ((len(spec["extra_terminals"]) + 15) // 16 if spec.get("extra_terminals") else 0))
                    info=[x.text for x in diagrams[1].findall('.//elementInformation')]
                    for pin in (spec['pins'][0],spec['pins'][-1]):self.assertIn(pin,info)
                    for pin in (spec['common'] if spec['io']=='in' else [spec['vplus'],spec['com']]):
                        if pin:self.assertIn(pin,info)
                    if spec.get('sensor_pins'):
                        connector_text = ' '.join(ET.tostring(d, encoding='unicode') for d in diagrams[2:])
                        for pin_label in spec['sensor_pins']: self.assertIn(pin_label, connector_text)
                        self.assertIn(f"CON{spec['points']}", connector_text)
                    if spec.get('extra_terminals'):
                        extra = [x.text for d in diagrams[2:] for x in d.findall('.//elementInformation')]
                        for pin, name in spec['extra_terminals']:
                            self.assertIn(pin,extra); self.assertIn(name,extra)
                    body=(ET.tostring(diagrams[0],encoding='unicode'))
                    tokens = ('+24V','24G','FG','DA','DB','DG','SLD','SW1 ON') if spec['network']=='CC-Link' else ('+24V','24G','FG','P1','P2','192.168.3.3','SW1 ON')
                    for token in tokens:self.assertIn(token,body)
                    category='input' if spec['io']=='in' else 'output'
                    series = 'cclink' if spec['network']=='CC-Link' else 'cclink_ie'
                    self.assertIn(model,gui.part_catalog('model',category)['mitsubishi'][series])
                    self.assertIn(model,gui.part_catalog('model','remotebody')['mitsubishi'][series])

if __name__=='__main__':unittest.main()
