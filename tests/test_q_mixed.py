import contextlib
import csv
import io
import json
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

import gen_io_page as gen
import gui


class QMixedTest(unittest.TestCase):
    def test_models_generate_correct_pages_addresses_and_pins(self):
        config = json.loads((Path(__file__).parent / 'fixtures' / 'project.json').read_text(encoding='utf-8'))
        for model, nin, nout, offset, pages in [('QH42P', 32, 32, 0, 2), ('QX41Y41P', 32, 32, 32, 2), ('QX48Y57', 8, 7, 8, 1), ('RH42C4NT2P', 32, 32, 0, 2)]:
            with self.subTest(model=model), tempfile.TemporaryDirectory() as d:
                path = Path(d)
                for direction, prefix, count, start in [('in', 'X', nin, 0x100), ('out', 'Y', nout, 0x100 + offset)]:
                    with (path / f'{direction}.csv').open('w', encoding='utf-8-sig', newline='') as f:
                        writer = csv.writer(f); writer.writerow(['アドレス', '機器番号', '信号名'])
                        writer.writerows([[f'{prefix}{start+i:X}', '', '予備'] for i in range(count)])
                spec = gen.IQR_MIXED[model] if model.startswith('R') else gen.Q_MIXED[model]
                config['pages'] = [{'kind':'iqrmixed' if model.startswith('R') else 'qmixed', 'model':model, 'start':'100', 'title':model, 'input_csv':'in.csv', 'output_csv':'out.csv'}]
                (path / 'input.json').write_text(json.dumps(config, ensure_ascii=False), encoding='utf-8')
                with contextlib.redirect_stdout(io.StringIO()): gen.main(str(path/'input.json'), str(path/'out.qet'))
                diagrams = ET.parse(path/'out.qet').getroot().findall('.//diagram')
                self.assertEqual(len(diagrams), pages)
                values = [e.text for dg in diagrams for e in dg.findall('.//elementInformation')]
                self.assertIn(f'Y{0x100+offset:X}', values)
                self.assertIn(spec['input']['pins'][0], values)
                self.assertIn(spec['output']['pins'][-1], values)
                for key in ('com', 'vplus'):
                    pins = spec['output'][key]
                    for pin in pins if isinstance(pins, list) else [pins]: self.assertIn(pin, values)
                with (path/'out_iolist.csv').open(encoding='utf-8-sig', newline='') as f:
                    rows = list(csv.DictReader(f))
                self.assertEqual(sum(r['アドレス'].startswith('X') for r in rows), nin)
                self.assertEqual(sum(r['アドレス'].startswith('Y') for r in rows), nout)
                with (path/'out.csv').open('w', encoding='utf-8-sig', newline='') as f:
                    writer = csv.writer(f); writer.writerow(['アドレス', '機器番号', '信号名']); writer.writerow(['Y0', '', ''])
                with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
                    gen.main(str(path/'input.json'), str(path/'bad.qet'))

    def test_iqr_catalog_and_body(self):
        self.assertIn('RH42C4NT2P', gui.part_catalog('model', 'iqrmixed')['mitsubishi']['iq_r'])
        self.assertIn('RH42C4NT2P', gui.part_catalog('modules', 'iqrbody')['mitsubishi']['iq_r'])
        config = json.loads((Path(__file__).parent / 'fixtures' / 'project.json').read_text(encoding='utf-8'))
        config['pages'] = [{'kind':'iqrbody', 'model':next(iter(gen.IQR_CPU)), 'power_model':next(iter(gen.IQR_POWER)), 'base_model':next(iter(gen.IQR_BASE)), 'modules':['RH42C4NT2P']}]
        with tempfile.TemporaryDirectory() as d:
            path = Path(d); (path/'input.json').write_text(json.dumps(config, ensure_ascii=False), encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()): gen.main(str(path/'input.json'), str(path/'out.qet'))
            self.assertIn('RH42C4NT2P', (path/'out.qet').read_text(encoding='utf-8'))

    def test_catalog_and_configured_body(self):
        models = {'QH42P', 'QX41Y41P', 'QX48Y57'}
        self.assertTrue(models <= set(gui.part_catalog('model', 'qmixed')['mitsubishi']['q']))
        self.assertTrue(models <= set(gui.part_catalog('modules', 'qbody')['mitsubishi']['q']))
        config = json.loads((Path(__file__).parent / 'fixtures' / 'project.json').read_text(encoding='utf-8'))
        config['pages'] = [{'kind':'qbody', 'model':next(iter(gen.Q_CPU)), 'power_model':next(iter(gen.Q_POWER)), 'base_model':next(iter(gen.Q_BASE)), 'modules':['QH42P']}]
        with tempfile.TemporaryDirectory() as d:
            path = Path(d); (path/'input.json').write_text(json.dumps(config, ensure_ascii=False), encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()): gen.main(str(path/'input.json'), str(path/'out.qet'))
            self.assertIn('QH42P', (path/'out.qet').read_text(encoding='utf-8'))


if __name__ == '__main__': unittest.main()
