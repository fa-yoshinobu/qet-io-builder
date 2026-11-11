import contextlib,io,json,tempfile,unittest
from pathlib import Path
from xml.etree import ElementTree as ET
import gen_io_page as g
import gui_core as gui

class IsolatedAnalogTest(unittest.TestCase):
 def test_special_inputs_channel_and_auxiliary_pins(self):
  cases=[('R60AD6-DG',['A1','B1','B2'],['A16','B16','B17'],['A19','B19','A20','B20']),
         ('R60ADI8-HA',['左1段','左2段','右1段','右2段'],['左15段','左16段','右15段','右16段'],['左17段','右17段','左18段','右18段','左20段']),
         ('R60TRD4-G',['TB2','TB3','TB4','TB5'],['TB14','TB15','TB16','TB17'],['TB18'])]
  cfg=json.loads((Path(__file__).parent/'fixtures'/'project.json').read_text(encoding='utf-8'))
  for model,first,last,power in cases:
   with self.subTest(model=model),tempfile.TemporaryDirectory() as d:
    spec=g.IQR_ANALOG[model];self.assertEqual(spec['pins_by_channel'][0],first);self.assertEqual(spec['pins_by_channel'][-1],last);self.assertEqual(spec['power_pins'],power)
    p=Path(d);cfg['pages']=[{'kind':'iqranalog','model':model}];(p/'in.json').write_text(json.dumps(cfg,ensure_ascii=False),encoding='utf-8')
    with contextlib.redirect_stdout(io.StringIO()):g.main(str(p/'in.json'),str(p/'out.qet'))
    vals=[e.text for e in ET.parse(p/'out.qet').getroot().findall('.//diagram//elementInformation')]
    for pin in first+last+power:self.assertIn(pin,vals)
    if model=='R60TRD4-G':self.assertIn('b/RTD-',vals)
    self.assertIn(model,gui.part_catalog('model','iqranalog')['mitsubishi']['iq_r'])

 def test_output_and_temperature_physical_pins(self):
  cases=[('R60DA8-G',8,['A1','B1'],['A16','B16'],['A19','B19','A20','B20']),
         ('R60DA16-G',16,['1A1','1B1'],['2A16','2B16'],['1A19','1B19','1A20','1B20','2A19','2B19','2A20','2B20']),
         ('R60TD8-G',8,['A1','B1'],['A15','B15'],[]),
         ('R60RD8-G',8,['A1','B1','A2'],['A19','B19','B18'],[])]
  cfg=json.loads((Path(__file__).parent/'fixtures'/'project.json').read_text(encoding='utf-8'))
  for model,count,first,last,power in cases:
   with self.subTest(model=model),tempfile.TemporaryDirectory() as d:
    p=Path(d);spec=g.IQR_ANALOG[model]
    self.assertEqual(spec['pins_by_channel'][0],first);self.assertEqual(spec['pins_by_channel'][-1],last)
    self.assertEqual(spec['power_pins'],power)
    cfg['pages']=[{'kind':'iqranalog','model':model}];(p/'in.json').write_text(json.dumps(cfg,ensure_ascii=False),encoding='utf-8')
    with contextlib.redirect_stdout(io.StringIO()):g.main(str(p/'in.json'),str(p/'out.qet'))
    diagrams=ET.parse(p/'out.qet').getroot().findall('.//diagram');self.assertEqual(len(diagrams),(count+7)//8)
    for i,diagram in enumerate(diagrams):
     vals=[e.text for e in diagram.findall('.//elementInformation')]
     for pin in (power[i*4:(i+1)*4] if spec.get('power_per_8_channels') else power):self.assertIn(pin,vals)
    self.assertIn(model,gui.part_catalog('model','iqranalog')['mitsubishi']['iq_r'])

 def test_pin_maps_pages_and_slot_constraints(self):
  cfg=json.loads((Path(__file__).parent/'fixtures'/'project.json').read_text(encoding='utf-8'))
  for model,n,slots in [('R60AD8-G',8,1),('R60AD16-G',16,2)]:
   with self.subTest(model=model),tempfile.TemporaryDirectory() as d:
    p=Path(d); spec=g.IQR_ANALOG[model]
    self.assertEqual(len(spec['pins_by_channel']),n)
    self.assertEqual(spec['pins_by_channel'][0],['1A1','1A2','1B1'] if n==16 else ['A1','A2','B1'])
    self.assertEqual(spec['pins_by_channel'][-1],['2B18','2B19','2A19'] if n==16 else ['B18','B19','A19'])
    self.assertIn(model,gui.part_catalog('model','iqranalog')['mitsubishi']['iq_r'])
    cfg['pages']=[{'kind':'iqranalog','model':model},{'kind':'iqrbody','model':'R04CPU','power_model':'R61P','base_model':'R35B','modules':[model]+([''] if slots==2 else [])}]
    (p/'in.json').write_text(json.dumps(cfg,ensure_ascii=False),encoding='utf-8')
    with contextlib.redirect_stdout(io.StringIO()):g.main(str(p/'in.json'),str(p/'out.qet'))
    diagrams=ET.parse(p/'out.qet').getroot().findall('.//diagram')
    self.assertEqual(len(diagrams),2 if n==8 else 3)
    pins=[x.text for dg in diagrams[:-1] for x in dg.findall('.//elementInformation')]
    for group in spec['pins_by_channel']:
     for pin in group:self.assertIn(pin,pins)
    if slots==2:
     cfg['pages'][1]['modules']=[model,'RX41C4']
     (p/'in.json').write_text(json.dumps(cfg,ensure_ascii=False),encoding='utf-8')
     with contextlib.redirect_stdout(io.StringIO()),self.assertRaises(SystemExit):g.main(str(p/'in.json'),str(p/'bad.qet'))

if __name__=='__main__':unittest.main()
