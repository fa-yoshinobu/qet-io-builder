"""仕様・注意書きで見出しと端子行を分断しない。"""
import unittest

import gen_io_page as gen
from renderers.terminal_pages import build_pages
from renderers.remote import connector_pages


class TableCommentPlacementTest(unittest.TestCase):
    def test_all_mxf_tables_start_at_header_and_keep_specs_at_bottom(self):
        for model, spec in {**gen.MX_CPU, **gen.MX_IO}.items():
            with self.subTest(model=model):
                pages = build_pages(dict(kind='mxio', model=model), spec, gen.build_symbols())
                self.assertEqual(sum(len(p.placed) for _, p in pages), len(spec['signal_terminals']))
                for _, page in pages:
                    for x in {item[2] for item in page.placed}:
                        first = next(item for item in page.placed if item[2] == x)
                        self.assertEqual(first[3] - page.sym[first[0]].hy, 70)
                    for text in page.texts:
                        if text.get('text', '').startswith(('入力', '出力')) and '点' in text.get('text', ''):
                            self.assertEqual(float(text.get('y')), 782)

    def test_remote_connector_warning_is_at_bottom(self):
        spec = dict(io_connectors=[dict(name='CON1', pins=[('1', 'X0')])])
        pages = connector_pages(dict(model='TEST'), gen.build_symbols(), spec,
                                gen.Page, gen.Symbol, gen.page_heading)
        for _, page in pages:
            warning = next(t for t in page.texts if t.get('text', '').startswith('※'))
            self.assertEqual(float(warning.get('y')), 800)

    def test_sensor_connector_warning_is_at_bottom(self):
        for model, spec in gen.IO_UNITS.items():
            if spec.get('sensor_pins'):
                with self.subTest(model=model):
                    page = gen.build_sensor_connector_page(dict(model=model), gen.build_symbols(), 0)
                    warning = next(t for t in page.texts if t.get('text', '').startswith('※'))
                    self.assertEqual(float(warning.get('y')), 800)


if __name__ == '__main__':
    unittest.main()
