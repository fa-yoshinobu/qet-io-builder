import contextlib,csv,io,json,tempfile,unittest
from pathlib import Path
from xml.etree import ElementTree as ET
import gen_io_page as g
import gui_core as gui

class RemoteMixedTest(unittest.TestCase):
 def test_multiline_mixed_inputs_outputs_and_commons(self):
  cfg=json.loads((Path(__file__).parent/'fixtures'/'project.json').read_text(encoding='utf-8'))
  for model in ('AJ65SBTB32-16DT2','AJ65SBTB32-16DR'):
   with self.subTest(model=model),tempfile.TemporaryDirectory() as d:
    p=Path(d);spec=g.REMOTE_MIXED[model]
    for name,prefix,offset in [('in','X',0),('out','Y',8)]:
     with (p/(name+'.csv')).open('w',encoding='utf-8-sig',newline='') as f:
      w=csv.writer(f);w.writerow(['アドレス','機器番号','信号名']);w.writerows([[f'{prefix}{i+offset:X}','','予備'] for i in range(8)])
    cfg['pages']=[{'kind':'remotebody','model':model},{'kind':'remotemixed','model':model,'input_csv':'in.csv','output_csv':'out.csv'}]
    (p/'in.json').write_text(json.dumps(cfg,ensure_ascii=False),encoding='utf-8')
    with contextlib.redirect_stdout(io.StringIO()):g.main(str(p/'in.json'),str(p/'out.qet'))
    diagrams=ET.parse(p/'out.qet').getroot().findall('.//diagram');self.assertEqual(len(diagrams),2)
    info=[x.text for x in diagrams[1].findall('.//elementInformation')]
    for pin in spec['input']['pins']+spec['output']['pins']:self.assertIn(pin,info)
    for direction in ('input','output'):
     for pin,name in spec[direction]['extra_terminals']:self.assertIn(pin,info);self.assertIn(name,info)
    terminals=diagrams[1].findall(".//elementInformation[@name='auxiliary1']")
    pins=[v.text for v in terminals if v.text and v.text.startswith('TB')]
    self.assertEqual(len(pins),34)
    self.assertEqual(set(pins),{f'TB{i}' for i in range(8,42)})
    self.assertNotIn('補助端子ページ',ET.tostring(diagrams[1],encoding='unicode'))
    if model.endswith('DR'):
     self.assertEqual(spec['output']['com'],'')
     self.assertIn('COM2A・COM3Aは別グループ',ET.tostring(diagrams[1],encoding='unicode'))
    self.assertIn(model,gui.part_catalog('model','remotemixed')['mitsubishi']['cclink'])

 def test_mixed_shared_common_and_communication(self):
  model='AJ65SBTB1-16DT2';cfg=json.loads((Path(__file__).parent/'fixtures'/'project.json').read_text(encoding='utf-8'))
  self.assertIn(model,gui.part_catalog('model','remotemixed')['mitsubishi']['cclink'])
  self.assertIn(model,gui.part_catalog('model','remotebody')['mitsubishi']['cclink'])
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)
   for name,prefix,offset in [('in','X',0),('out','Y',8)]:
    with (p/(name+'.csv')).open('w',encoding='utf-8-sig',newline='') as f:
     w=csv.writer(f);w.writerow(['アドレス','機器番号','信号名']);w.writerows([[f'{prefix}{i+offset:X}','','予備'] for i in range(8)])
   cfg['pages']=[{'kind':'remotebody','model':model,'station':'5'},{'kind':'remotemixed','model':model,'input_csv':'in.csv','output_csv':'out.csv'}]
   (p/'in.json').write_text(json.dumps(cfg,ensure_ascii=False),encoding='utf-8')
   with contextlib.redirect_stdout(io.StringIO()):g.main(str(p/'in.json'),str(p/'out.qet'))
   diagrams=ET.parse(p/'out.qet').getroot().findall('.//diagram');self.assertEqual(len(diagrams),2)
   info=[x.text for x in diagrams[1].findall('.//elementInformation')]
   for pin in ('TB8','TB15','TB16','TB23','TB24','TB25','X0','X7','Y8','YF'):self.assertIn(pin,info)
   self.assertEqual(info.count('TB24'),1)
   self.assertIn('入力COM+は出力側のTB24と共通',ET.tostring(diagrams[1],encoding='unicode'))

if __name__=='__main__':unittest.main()
