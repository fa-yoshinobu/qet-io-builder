import contextlib
import io
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import export_connector_elements, export_power_supply_elements, preview_qet

try:
    from tools import pdf_to_a3
except ModuleNotFoundError as error:
    if error.name != 'pypdf':
        raise
    pdf_to_a3 = None


class ToolArgumentsTest(unittest.TestCase):
    def test_help_and_missing_arguments_never_generate_files(self):
        tools = [(export_connector_elements, 'export'),
                 (export_power_supply_elements, 'export'), (preview_qet, 'render')]
        if pdf_to_a3 is not None:
            tools.append((pdf_to_a3, 'to_a3'))
        for module, operation in tools:
            for args, code in [(['-h'], 0), ([], 2)]:
                with self.subTest(tool=module.__name__, args=args), patch.object(module, operation) as generate:
                    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                        with self.assertRaises(SystemExit) as caught:
                            module.main(args)
                    self.assertEqual(caught.exception.code, code)
                    generate.assert_not_called()

    def test_preview_preserves_positional_pages_and_scale(self):
        with patch.object(preview_qet, 'render', return_value=[]) as render:
            preview_qet.main(['input.qet', 'png', '1,3-5', '1.2'])
            render.assert_called_once_with('input.qet', 'png', {1, 3, 4, 5}, 1.2)
            render.reset_mock()
            preview_qet.main(['input.qet', 'png', 'all'])
            render.assert_called_once_with('input.qet', 'png', None, 0.8)

    @unittest.skipIf(pdf_to_a3 is None, 'pypdf が未インストール')
    def test_pdf_preserves_drawing_option_and_multiple_files(self):
        with patch.object(pdf_to_a3, 'to_a3') as convert:
            pdf_to_a3.main(['--drawing', '1260x870', 'one.pdf', 'two.pdf'])
            self.assertEqual(convert.call_args_list,
                             [unittest.mock.call('one.pdf', (1260, 870)),
                              unittest.mock.call('two.pdf', (1260, 870))])
            convert.reset_mock()
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                pdf_to_a3.main(['--drawing', '0x870', 'one.pdf'])
            convert.assert_not_called()

    def test_exporters_use_explicit_path(self):
        for module in (export_connector_elements, export_power_supply_elements):
            with self.subTest(tool=module.__name__), patch.object(module, 'export', return_value=[]) as export:
                with contextlib.redirect_stdout(io.StringIO()):
                    module.main(['output'])
                export.assert_called_once_with(Path('output'))


if __name__ == '__main__':
    unittest.main()
