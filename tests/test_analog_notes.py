import unittest
import gen_io_page as gen


class AnalogNotesTest(unittest.TestCase):
    def test_notes_are_at_bottom_without_a_gap_below_headers(self):
        for kind, definitions in (('iqranalog',gen.IQR_ANALOG),('qanalog',gen.Q_ANALOG),('remoteanalog',gen.REMOTE_ANALOG)):
            for model,spec in definitions.items():
                if not spec.get('diagram_note'):
                    continue
                with self.subTest(model=model):
                    page=gen.build_fx_analog_page({'kind':kind,'model':model},{},gen.build_symbols(),[])
                    note=next(t for t in page.texts if t.get('text')==spec['diagram_note'])
                    self.assertEqual(float(note.get('y')),800)
                    ys=[y for key,_,_,y in page.placed if key.startswith('plc_in')]
                    self.assertEqual(min(ys),gen.ROW_Y0)
                    self.assertLessEqual(max(ys)+20,770)

    def test_dense_unit_splits_without_losing_channel_pins(self):
        model='R60ADI8-HA'
        root,_=gen.build_project(gen.project_config({'front_pages':False}),[({'kind':'iqranalog','model':model},[])])
        diagrams=root.findall('diagram')
        self.assertEqual(len(diagrams),2)
        pins=[n.text for n in root.findall(".//diagram/elements/element/elementInformations/elementInformation[@name='auxiliary1']")]
        for channel in gen.IQR_ANALOG[model]['pins_by_channel']:
            for pin in channel:
                self.assertIn(pin,pins)


if __name__=='__main__':
    unittest.main()
